import assert from "node:assert/strict";
import { test } from "node:test";

import worker, { dispatchWorkflow, shouldDispatch } from "../src/index.js";

const env = {
  GITHUB_REPO: "tygast/lifetime-reservation-bot",
  GITHUB_WORKFLOW: "bot.yml",
  GITHUB_REF: "main",
  GITHUB_DISPATCH_TOKEN: "test-token",
};

test("dispatches the CDT slot and skips the CST slot in summer", () => {
  assert.equal(shouldDispatch(new Date("2026-09-30T14:30:00Z")), true);
  assert.equal(shouldDispatch(new Date("2026-09-30T15:30:00Z")), false);
});

test("dispatches the CST slot and skips the CDT slot in winter", () => {
  assert.equal(shouldDispatch(new Date("2026-12-02T15:30:00Z")), true);
  assert.equal(shouldDispatch(new Date("2026-12-02T14:30:00Z")), false);
});

test("dispatchWorkflow posts scheduled prod inputs to the workflow", async () => {
  let request;
  const fetchImpl = async (url, init) => {
    request = { url, init };
    return new Response(null, { status: 204 });
  };

  await dispatchWorkflow(env, fetchImpl);

  assert.equal(
    request.url,
    "https://api.github.com/repos/tygast/lifetime-reservation-bot/actions/workflows/bot.yml/dispatches",
  );
  assert.equal(request.init.method, "POST");
  assert.equal(request.init.headers.Authorization, "Bearer test-token");
  assert.deepEqual(JSON.parse(request.init.body), {
    ref: "main",
    inputs: { env: "prod", runner: "macos-latest", scheduled: "true" },
  });
});

test("dispatchWorkflow throws on a non-2xx response", async () => {
  const fetchImpl = async () => new Response("Bad credentials", { status: 401 });

  await assert.rejects(dispatchWorkflow(env, fetchImpl), /401 Bad credentials/);
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
