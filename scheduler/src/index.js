// Cloudflare Worker that dispatches the reservation workflow on time.
//
// GitHub Actions `schedule` triggers are best-effort and routinely start hours
// late, so this Worker calls the workflow_dispatch API from a Cron Trigger
// instead. Cron Triggers run in UTC, so wrangler.toml fires in both the CDT and
// CST hours and `shouldDispatch` keeps only the ones that land in DISPATCH_HOUR
// Chicago time.

const DISPATCH_TIMEZONE = "America/Chicago";
const DISPATCH_HOUR = 9;

const chicagoParts = new Intl.DateTimeFormat("en-US", {
  timeZone: DISPATCH_TIMEZONE,
  hourCycle: "h23",
  hour: "2-digit",
  minute: "2-digit",
});

export function chicagoTime(date) {
  const parts = Object.fromEntries(
    chicagoParts.formatToParts(date).map((part) => [part.type, part.value]),
  );
  return { hour: Number(parts.hour), minute: Number(parts.minute) };
}

export function shouldDispatch(date) {
  return chicagoTime(date).hour === DISPATCH_HOUR;
}

export async function dispatchWorkflow(env, fetchImpl = fetch) {
  const url =
    `https://api.github.com/repos/${env.GITHUB_REPO}` +
    `/actions/workflows/${env.GITHUB_WORKFLOW}/dispatches`;
  const response = await fetchImpl(url, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "lifetime-reservation-scheduler",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      ref: env.GITHUB_REF,
      inputs: { env: "prod", runner: "macos-latest", scheduled: "true" },
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`workflow_dispatch failed: ${response.status} ${detail}`);
  }
}

export default {
  async scheduled(controller, env) {
    const firedAt = new Date(controller.scheduledTime);
    const { hour, minute } = chicagoTime(firedAt);
    const local = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

    if (!shouldDispatch(firedAt)) {
      console.log(`Cron ${controller.cron} fired at ${local} CT; outside dispatch hour, skipping.`);
      return;
    }

    await dispatchWorkflow(env);
    console.log(`Cron ${controller.cron} fired at ${local} CT; dispatched ${env.GITHUB_WORKFLOW}.`);
  },
};
