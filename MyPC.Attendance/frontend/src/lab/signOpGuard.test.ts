import { describe, expect, it, vi } from "vitest";
import { isSignOpLive, runFencedSignWorkflow, type SignSelection } from "./signOpGuard";

describe("signOpGuard", () => {
  const started: SignSelection = { epoch: 1, cameraId: 10, kind: "CAMERA_LAB" };

  it("is live only for matching epoch/camera/kind", () => {
    expect(isSignOpLive(started, { epoch: 1, cameraId: 10, kind: "CAMERA_LAB" })).toBe(true);
    expect(isSignOpLive(started, { epoch: 2, cameraId: 10, kind: "CAMERA_LAB" })).toBe(false);
    expect(isSignOpLive(started, { epoch: 1, cameraId: 11, kind: "CAMERA_LAB" })).toBe(false);
    expect(isSignOpLive(started, { epoch: 1, cameraId: 10, kind: "FACE_PILOT" })).toBe(false);
    expect(isSignOpLive(started, { epoch: 1, cameraId: null, kind: "CAMERA_LAB" })).toBe(false);
  });

  it("applies result when camera unchanged through deferred POST+GET", async () => {
    let live = { epoch: 1, cameraId: 10 as number | null, kind: "CAMERA_LAB" };
    const onResult = vi.fn();
    const onStale = vi.fn();
    let resolvePost!: (v: { approval_id: string }) => void;
    const post = new Promise<{ approval_id: string }>((r) => {
      resolvePost = r;
    });
    const work = async () => {
      const posted = await post;
      const health = await Promise.resolve({ signed_camera_lab: true });
      return { posted, health };
    };
    const done = runFencedSignWorkflow({
      started,
      getLive: () => live,
      work,
      onResult,
      onStale,
    });
    resolvePost({ approval_id: "a1" });
    await expect(done).resolves.toBe("applied");
    expect(onResult).toHaveBeenCalledWith({
      posted: { approval_id: "a1" },
      health: { signed_camera_lab: true },
    });
    expect(onStale).not.toHaveBeenCalled();
  });

  it("discards UI update when camera switches during deferred POST", async () => {
    let live = { epoch: 1, cameraId: 10 as number | null, kind: "CAMERA_LAB" };
    const onResult = vi.fn();
    const onStale = vi.fn();
    let resolvePost!: (v: string) => void;
    const post = new Promise<string>((r) => {
      resolvePost = r;
    });
    const done = runFencedSignWorkflow({
      started,
      getLive: () => live,
      work: () => post,
      onResult,
      onStale,
    });
    live = { epoch: 2, cameraId: 99, kind: "CAMERA_LAB" };
    resolvePost("approval-from-A");
    await expect(done).resolves.toBe("stale");
    expect(onResult).not.toHaveBeenCalled();
    expect(onStale).toHaveBeenCalledTimes(1);
  });

  it("discards UI update when camera switches during deferred GET after POST", async () => {
    let live = { epoch: 1, cameraId: 10 as number | null, kind: "CAMERA_LAB" };
    const onResult = vi.fn();
    let resolveGet!: (v: { signed: boolean }) => void;
    const getHealth = new Promise<{ signed: boolean }>((r) => {
      resolveGet = r;
    });
    const done = runFencedSignWorkflow({
      started,
      getLive: () => live,
      work: async () => {
        const posted = await Promise.resolve({ approval_id: "a-post" });
        // Switch after POST resolves, before GET settles
        live = { epoch: 2, cameraId: 20, kind: "CAMERA_LAB" };
        const health = await getHealth;
        return { posted, health };
      },
      onResult,
    });
    resolveGet({ signed: true });
    await expect(done).resolves.toBe("stale");
    expect(onResult).not.toHaveBeenCalled();
  });
});
