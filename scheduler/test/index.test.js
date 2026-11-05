import assert from "node:assert/strict";
import { test } from "node:test";

import { createAppJwt } from "../src/github-app.js";
import worker, { dispatchSlot, dispatchWorkflow, shouldDispatch } from "../src/index.js";

const keyPair = await crypto.subtle.generateKey(
  {
    name: "RSASSA-PKCS1-v1_5",
    modulusLength: 2048,
    publicExponent: new Uint8Array([1, 0, 1]),
    hash: "SHA-256",
  },
  true,
  ["sign", "verify"],
);
const pkcs8 = Buffer.from(await crypto.subtle.exportKey("pkcs8", keyPair.privateKey));
const privateKeyPem =
  "-----BEGIN PRIVATE KEY-----\n" +
  pkcs8.toString("base64").match(/.{1,64}/g).join("\n") +
  "\n-----END PRIVATE KEY-----\n";

const env = {
  GITHUB_REPO: "tygast/lifetime-reservation-bot",
  GITHUB_WORKFLOW: "bot.yml",
  GITHUB_REF: "main",
  GITHUB_APP_ID: "12345",
  GITHUB_APP_PRIVATE_KEY: privateKeyPem,
};

// Answers the installation lookup and token exchange, records every request,
// and returns `dispatchResponse` for the workflow_dispatch call.
function fakeGitHub(dispatchResponse = () => new Response(null, { status: 204 })) {
  const requests = [];
  const fetchImpl = async (url, init = {}) => {
    requests.push({ url, init });
    if (url.endsWith("/repos/tygast/lifetime-reservation-bot/installation")) {
      return Response.json({ id: 777 });
    }
    if (url.endsWith("/app/installations/777/access_tokens")) {
      return Response.json({ token: "installation-token" }, { status: 201 });
    }
    return dispatchResponse();
  };
  return { fetchImpl, requests };
}

function decodeSegment(segment) {
  return JSON.parse(Buffer.from(segment, "base64url").toString("utf8"));
}

test("dispatches the CDT slot and skips the CST slot in summer", () => {
  assert.equal(shouldDispatch(new Date("2026-09-30T14:30:00Z")), true);
  assert.equal(shouldDispatch(new Date("2026-09-30T15:30:00Z")), false);
});

test("dispatches the CST slot and skips the CDT slot in winter", () => {
  assert.equal(shouldDispatch(new Date("2026-12-02T15:30:00Z")), true);
  assert.equal(shouldDispatch(new Date("2026-12-02T14:30:00Z")), false);
});

test("labels the 9:30 slot primary and the 9:45 slot backup in both CDT and CST", () => {
  assert.equal(dispatchSlot(new Date("2026-09-30T14:30:00Z")), "primary");
  assert.equal(dispatchSlot(new Date("2026-09-30T14:45:00Z")), "backup");
  assert.equal(dispatchSlot(new Date("2026-12-02T15:30:00Z")), "primary");
  assert.equal(dispatchSlot(new Date("2026-12-02T15:45:00Z")), "backup");
});

test("createAppJwt signs an RS256 JWT that verifies with the App key", async () => {
  const nowMs = Date.parse("2026-11-04T15:30:00Z");
  const jwt = await createAppJwt("12345", privateKeyPem, nowMs);
  const [header, payload, signature] = jwt.split(".");

  assert.deepEqual(decodeSegment(header), { alg: "RS256", typ: "JWT" });
  const now = nowMs / 1000;
  assert.deepEqual(decodeSegment(payload), { iat: now - 60, exp: now + 540, iss: "12345" });
  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    keyPair.publicKey,
    Buffer.from(signature, "base64url"),
    new TextEncoder().encode(`${header}.${payload}`),
  );
  assert.equal(valid, true);
});

test("createAppJwt rejects GitHub's PKCS#1 key with a conversion hint", async () => {
  const pkcs1 = "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n";
  await assert.rejects(createAppJwt("12345", pkcs1), /openssl pkcs8 -topk8/);
});

test("dispatchWorkflow exchanges the App JWT for a scoped installation token", async () => {
  const { fetchImpl, requests } = fakeGitHub();

  await dispatchWorkflow(env, "primary", fetchImpl);

  const [lookup, exchange, dispatch] = requests;
  assert.match(lookup.init.headers.Authorization, /^Bearer [\w-]+\.[\w-]+\.[\w-]+$/);
  assert.equal(exchange.init.method, "POST");
  assert.equal(exchange.init.headers.Authorization, lookup.init.headers.Authorization);
  assert.deepEqual(JSON.parse(exchange.init.body), {
    repositories: ["lifetime-reservation-bot"],
    permissions: { actions: "write" },
  });
  assert.equal(
    dispatch.url,
    "https://api.github.com/repos/tygast/lifetime-reservation-bot/actions/workflows/bot.yml/dispatches",
  );
  assert.equal(dispatch.init.method, "POST");
  assert.equal(dispatch.init.headers.Authorization, "Bearer installation-token");
  assert.deepEqual(JSON.parse(dispatch.init.body), {
    ref: "main",
    inputs: { env: "prod", runner: "ubuntu-latest", scheduled: "true", slot: "primary" },
  });
});

test("dispatchWorkflow throws when the App is not installed on the repo", async () => {
  const fetchImpl = async () => new Response("Not Found", { status: 404 });

  await assert.rejects(
    dispatchWorkflow(env, "primary", fetchImpl),
    /installation lookup failed: 404 Not Found/,
  );
});

test("dispatchWorkflow throws on a non-2xx dispatch response", async () => {
  const { fetchImpl } = fakeGitHub(() => new Response("Bad credentials", { status: 401 }));

  await assert.rejects(dispatchWorkflow(env, "primary", fetchImpl), /workflow_dispatch failed: 401 Bad credentials/);
});

test("scheduled handler does not call GitHub outside the dispatch hour", async () => {
  const originalFetch = globalThis.fetch;
  let called = false;
  globalThis.fetch = async () => {
    called = true;
    return new Response(null, { status: 204 });
  };
  try {
    await worker.scheduled(
      { cron: "30 15 * * SUN-THU", scheduledTime: Date.parse("2026-09-30T15:30:00Z") },
      env,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(called, false);
});
