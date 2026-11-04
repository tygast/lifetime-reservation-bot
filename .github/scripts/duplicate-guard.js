// Decides whether a scheduled (Cloudflare-dispatched) run should book, given
// earlier scheduled runs of bot.yml on the same Chicago day. Called from the
// check-schedule job via actions/github-script; returns true to run the bot.
//
// For each earlier run, in order:
// - run-bot succeeded            -> skip; today is already handled.
// - run-bot failed or cancelled  -> look at the next earlier run.
// - run-bot running              -> wait for it to finish. run-bot's 50-minute
//                                   timeout keeps this shorter than waitMs.
// - run-bot queued or not visible past queueGraceMs -> it never got a runner,
//   so cancel that run and take over. Cancelling (rather than just ignoring
//   it) keeps it from starting later and booking alongside this run.
//
// Listing runs fails open (run the bot): missing a class is worse than a
// duplicate attempt. Errors while polling a known run keep its last state.

const NOT_STARTED = new Set(["queued", "waiting", "pending", "requested"]);

function chicagoDate(value) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

function describe(job) {
  if (!job) return "not visible yet";
  return job.conclusion ? `${job.status}/${job.conclusion}` : job.status;
}

module.exports = async function duplicateGuard({
  github,
  context,
  core,
  currentLocalDate,
  refName,
  pollMs = 30 * 1000,
  queueGraceMs = 2 * 60 * 1000,
  waitMs = 60 * 60 * 1000,
  now = () => Date.now(),
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
}) {
  const { owner, repo } = context.repo;

  let workflowRuns;
  try {
    const response = await github.rest.actions.listWorkflowRuns({
      owner,
      repo,
      workflow_id: "bot.yml",
      per_page: 100,
    });
    workflowRuns = Array.isArray(response.data.workflow_runs)
      ? response.data.workflow_runs
      : [];
  } catch (error) {
    core.warning(`Duplicate guard could not list workflow runs: ${error.message}`);
    return true;
  }

  // Only earlier runs on this branch count, so two runs checking at the same
  // moment never wait on each other.
  const candidates = workflowRuns
    .filter(
      (run) =>
        run &&
        typeof run.id === "number" &&
        typeof run.run_number === "number" &&
        typeof run.created_at === "string" &&
        typeof run.display_title === "string" &&
        run.display_title.startsWith("Scheduled") &&
        run.run_number < context.runNumber &&
        run.head_branch === refName &&
        chicagoDate(run.created_at) === currentLocalDate,
    )
    .sort((left, right) => left.run_number - right.run_number);

  const fetchRunBotJob = async (runId, previous) => {
    try {
      const response = await github.rest.actions.listJobsForWorkflowRun({
        owner,
        repo,
        run_id: runId,
        per_page: 100,
      });
      const jobs = Array.isArray(response.data.jobs) ? response.data.jobs : [];
      return { job: jobs.find((job) => job && job.name === "run-bot"), ok: true };
    } catch (error) {
      core.warning(`Could not read jobs for run #${runId}, retrying: ${error.message}`);
      return { job: previous, ok: false };
    }
  };

  const cancelAndWait = async (run) => {
    try {
      await github.rest.actions.cancelWorkflowRun({ owner, repo, run_id: run.id });
    } catch (error) {
      // 409 means it already finished; anything else, re-check before acting.
      core.warning(`Cancelling run #${run.id} returned: ${error.message}`);
    }
    const cancelDeadline = now() + queueGraceMs;
    while (now() < cancelDeadline) {
      try {
        const { data } = await github.rest.actions.getWorkflowRun({ owner, repo, run_id: run.id });
        if (data.status === "completed") return true;
      } catch (error) {
        core.warning(`Could not read run #${run.id} after cancel: ${error.message}`);
      }
      await sleep(pollMs);
    }
    return false;
  };

  for (const run of candidates) {
    const label = `${run.display_title} (#${run.id})`;
    const deadline = now() + waitMs;
    const graceEnds = now() + queueGraceMs;
    let { job } = await fetchRunBotJob(run.id);
    let cancelled = false;

    while (!job || job.status !== "completed") {
      const notStarted = !job || NOT_STARTED.has(job.status);

      if (notStarted && !cancelled && now() >= graceEnds) {
        core.warning(`${label} never started run-bot (${describe(job)}); cancelling it.`);
        cancelled = true;
        if (await cancelAndWait(run)) {
          // The run is finished, so run-bot is either completed or was never
          // created (the run was cancelled before reaching it).
          const latest = await fetchRunBotJob(run.id, job);
          job =
            latest.ok && latest.job && latest.job.status === "completed"
              ? latest.job
              : { status: "completed", conclusion: "cancelled" };
          continue;
        }
        // Still not completed: it may have just started. Keep watching it.
      }

      if (now() >= deadline) {
        core.warning(
          `${label} still has run-bot ${describe(job)} after waiting; ` +
            "skipping to avoid booking twice.",
        );
        return false;
      }

      core.info(`Waiting on ${label}: run-bot ${describe(job)}.`);
      await sleep(pollMs);
      ({ job } = await fetchRunBotJob(run.id, job));
    }

    if (job.conclusion === "success") {
      core.notice(
        `Skipping duplicate scheduled run because ${label} has run-bot ` +
          `${describe(job)} for ${currentLocalDate}.`,
      );
      return false;
    }
    core.info(`${label} ended with run-bot ${describe(job)}; not blocking this run.`);
  }

  return true;
};
