// GitHub App authentication for the scheduler Worker.
//
// Dispatching as a GitHub App (instead of a personal access token) makes runs
// show the App as the actor and avoids a token that expires. The flow is:
// sign a short-lived JWT with the App's private key, look up the App's
// installation on the repo, then exchange the JWT for an installation token
// scoped to that repo with Actions write access.

const GITHUB_API = "https://api.github.com";

function base64url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64urlJson(value) {
  return base64url(new TextEncoder().encode(JSON.stringify(value)));
}

async function importPrivateKey(pem) {
  if (!pem.includes("BEGIN PRIVATE KEY")) {
    throw new Error(
      "GITHUB_APP_PRIVATE_KEY must be a PKCS#8 PEM (BEGIN PRIVATE KEY). Convert GitHub's " +
        "key with: openssl pkcs8 -topk8 -nocrypt -in app.pem -out app-pkcs8.pem",
    );
  }
  const body = pem
    .replace(/-----(BEGIN|END) PRIVATE KEY-----/g, "")
    .replace(/\s+/g, "");
  const der = Uint8Array.from(atob(body), (char) => char.charCodeAt(0));
  return crypto.subtle.importKey(
    "pkcs8",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

export async function createAppJwt(appId, privateKeyPem, nowMs = Date.now()) {
  const now = Math.floor(nowMs / 1000);
  // Backdate iat for clock drift; GitHub caps exp at 10 minutes.
  const header = base64urlJson({ alg: "RS256", typ: "JWT" });
  const payload = base64urlJson({ iat: now - 60, exp: now + 540, iss: String(appId) });
  const signingInput = `${header}.${payload}`;
  const key = await importPrivateKey(privateKeyPem);
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(signingInput),
  );
  return `${signingInput}.${base64url(new Uint8Array(signature))}`;
}

export function githubHeaders(token) {
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${token}`,
    "User-Agent": "lifetime-reservation-scheduler",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

async function expectOk(response, action) {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${action} failed: ${response.status} ${detail}`);
  }
  return response.json();
}

export async function getInstallationToken(env, fetchImpl = fetch) {
  const jwt = await createAppJwt(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);

  const installation = await expectOk(
    await fetchImpl(`${GITHUB_API}/repos/${env.GITHUB_REPO}/installation`, {
      headers: githubHeaders(jwt),
    }),
    "GitHub App installation lookup",
  );

  const repoName = env.GITHUB_REPO.split("/")[1];
  const { token } = await expectOk(
    await fetchImpl(`${GITHUB_API}/app/installations/${installation.id}/access_tokens`, {
      method: "POST",
      headers: { ...githubHeaders(jwt), "Content-Type": "application/json" },
      body: JSON.stringify({ repositories: [repoName], permissions: { actions: "write" } }),
    }),
    "GitHub App installation token",
  );
  return token;
}
