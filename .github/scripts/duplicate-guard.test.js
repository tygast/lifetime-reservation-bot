// Run with: node --test .github/scripts/duplicate-guard.test.js
const assert = require("node:assert/strict");
const { test } = require("node:test");

const duplicateGuard = require("./duplicate-guard.js");

const TODAY = "2026-11-04";
const PRIMARY = {
  id: 1,
  run_number: 9,
  created_at: "2026-11-04T15:30:15Z",
  display_title: "Scheduled (Cloudflare dispatch)",
  head_branch: "main",
};
const job = (status, conclusion = null) => ({ name: "run-bot", status, conclusion });

// `jobs` is the sequence of run-bot states returned by successive polls (the
// last one repeats); an Error entry makes that poll throw. The fake clock only
// advances when the guard sleeps.
function harness({ runs = [PRIMARY], jobs = [], listRunsError, runAfterCancel = "completed" }) {
  let clock = 0;
  let poll = 0;
  const calls = { cancel: 0 };
  const logs = [];
  const github = {
    rest: {
      actions: {
        listWorkflowRuns: async () => {
          if (listRunsError) throw listRunsError;
          return { data: { workflow_runs: runs } };
        },
        listJobsForWorkflowRun: async () => {
          const next = jobs[Math.min(poll++, jobs.length - 1)];
          if (next instanceof Error) throw next;
          return { data: { jobs: next ? [next] : [] } };
        },
        cancelWorkflowRun: async () => {
          calls.cancel++;
        },
        getWorkflowRun: async () => ({ data: { status: runAfterCancel } }),
      },
    },
  };
  const core = {
    info: () => {},
    notice: (message) => logs.push(`notice: ${message}`),
    warning: (message) => logs.push(`warning: ${message}`),
  };
  const run = () =>
    duplicateGuard({
      github,
      core,
      context: { repo: { owner: "tygast", repo: "lifetime-reservation-bot" }, runNumber: 10 },
      currentLocalDate: TODAY,
      refName: "main",
      now: () => clock,
      sleep: async (ms) => {
        clock += ms;
      },
    });
  return { run, calls, logs, elapsedMinutes: () => clock / 60000 };
}

test("runs when there is no earlier scheduled run today", async () => {
  const h = harness({ runs: [] });
  assert.equal(await h.run(), true);
});

test("skips when the earlier run already booked", async () => {
  const h = harness({ jobs: [job("completed", "success")] });
  assert.equal(await h.run(), false);
  assert.equal(h.calls.cancel, 0);
});

test("runs when the earlier run already failed", async () => {
  const h = harness({ jobs: [job("completed", "failure")] });
  assert.equal(await h.run(), true);
});

test("waits for a running earlier run and skips if it succeeds", async () => {
  const h = harness({ jobs: [job("in_progress"), job("in_progress"), job("completed", "success")] });
  assert.equal(await h.run(), false);
  assert.equal(h.calls.cancel, 0);
});

test("waits for a running earlier run and runs if it fails", async () => {
  const h = harness({ jobs: [job("in_progress"), job("completed", "failure")] });
  assert.equal(await h.run(), true);
});

test("Nov 4 case: queued run is cancelled within the grace period, then this run books", async () => {
  const h = harness({ jobs: [job("queued")] });
  assert.equal(await h.run(), true);
  assert.equal(h.calls.cancel, 1);
  assert.ok(h.elapsedMinutes() <= 3, `took ${h.elapsedMinutes()} minutes`);
});

test("queued run that got cancelled on its own before the grace period ends", async () => {
  const h = harness({ jobs: [job("queued"), job("completed", "cancelled")] });
  assert.equal(await h.run(), true);
  assert.equal(h.calls.cancel, 0);
});

test("earlier run whose run-bot job never appears is cancelled and taken over", async () => {
  const h = harness({ jobs: [undefined] });
  assert.equal(await h.run(), true);
  assert.equal(h.calls.cancel, 1);
});

test("a polling error keeps waiting on a known running run instead of booking", async () => {
  const h = harness({
    jobs: [job("in_progress"), new Error("503 Service Unavailable"), job("completed", "success")],
  });
  assert.equal(await h.run(), false);
  assert.ok(h.logs.some((line) => line.includes("503")));
});

test("queued run that starts right as it is cancelled is still watched", async () => {
  // Cancel is requested but the run keeps going; it then books successfully.
  const h = harness({
    jobs: [job("queued"), job("queued"), job("queued"), job("queued"), job("queued"),
      job("in_progress"), job("completed", "success")],
    runAfterCancel: "in_progress",
  });
  assert.equal(await h.run(), false);
});

test("a run still going after the full wait is not doubled up on", async () => {
  const h = harness({ jobs: [job("in_progress")] });
  assert.equal(await h.run(), false);
  assert.ok(h.elapsedMinutes() >= 60);
});

test("fails open when the run list cannot be read", async () => {
  const h = harness({ listRunsError: new Error("502 Bad Gateway") });
  assert.equal(await h.run(), true);
});

test("ignores runs from other days, branches, manual runs, and later runs", async () => {
  const h = harness({
    runs: [
      { ...PRIMARY, id: 2, created_at: "2026-11-03T15:30:15Z" },
      { ...PRIMARY, id: 3, head_branch: "feature" },
      { ...PRIMARY, id: 4, display_title: "Manual (prod, ubuntu-latest)" },
      { ...PRIMARY, id: 5, run_number: 11 },
    ],
    jobs: [job("completed", "success")],
  });
  assert.equal(await h.run(), true);
});
