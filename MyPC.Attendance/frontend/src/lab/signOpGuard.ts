/**
 * PR16-HF3: fence async HMAC signing / evidence reload against camera/kind switches.
 * Backend approval remains scoped to the authorized request; UI must not paint A's
 * result onto B after an await.
 */

export type SignSelection = {
  epoch: number;
  cameraId: number;
  kind: string;
};

export type LiveSelection = {
  epoch: number;
  cameraId: number | null;
  kind: string;
};

export function isSignOpLive(started: SignSelection, live: LiveSelection): boolean {
  return (
    started.epoch === live.epoch &&
    live.cameraId != null &&
    started.cameraId === live.cameraId &&
    started.kind === live.kind
  );
}

/** Run an async workflow; skip onResult if selection changed mid-flight. */
export async function runFencedSignWorkflow<T>(opts: {
  started: SignSelection;
  getLive: () => LiveSelection;
  work: () => Promise<T>;
  onResult: (value: T) => void;
  onStale?: () => void;
}): Promise<"applied" | "stale"> {
  const value = await opts.work();
  if (!isSignOpLive(opts.started, opts.getLive())) {
    opts.onStale?.();
    return "stale";
  }
  opts.onResult(value);
  return "applied";
}
