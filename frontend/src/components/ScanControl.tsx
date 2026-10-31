/** "Scan library" for the self-hosted app: start a scan and show its progress until it ends. */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { Job } from "../api/types";
import { useDataSource } from "../data/context";

export function ScanControl() {
  const source = useDataSource();
  const client = useQueryClient();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  const follow = (start: Job) => {
    setJob(start);
    return source.watchJob(start.id, (update) => {
      setJob(update);
      // New analyses change everything the UI shows.
      if (update.status !== "running") void client.invalidateQueries();
    });
  };

  // A scan started earlier (another tab, or before a reload) is still shown.
  useEffect(() => {
    let stop: (() => void) | undefined;
    let cancelled = false;
    void source.latestJob().then((latest) => {
      if (!cancelled && latest?.status === "running") stop = follow(latest);
    });
    return () => {
      cancelled = true;
      stop?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per mount
  }, [source]);

  const start = async () => {
    setError(null);
    try {
      follow(await source.startScan());
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const running = job?.status === "running";
  return (
    <span className="scan-control">
      <button type="button" onClick={() => void start()} disabled={running}>
        {running ? "Scanning…" : "Scan library"}
      </button>
      {running && job.total === 0 && <span role="status">Looking for new and changed files…</span>}
      {running && job.total > 0 && (
        <span role="status">
          <progress value={job.progress} max={job.total} aria-label="Scan progress" /> Analyzing{" "}
          <span className="num">
            {job.progress} of {job.total}
          </span>
        </span>
      )}
      {job?.status === "completed" && (
        <span role="status">
          Scan finished: {job.total === 0 ? "nothing new" : `${job.progress - job.failed} analyzed`}
          {job.failed ? `, ${job.failed} failed` : ""}.
        </span>
      )}
      {job?.status === "failed" && <span role="alert">Scan failed: {job.error}</span>}
      {error && <span role="alert">{error}</span>}
    </span>
  );
}
