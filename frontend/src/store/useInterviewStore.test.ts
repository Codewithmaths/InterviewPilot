import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useInterviewStore } from "@/store/useInterviewStore";

beforeEach(() => {
  vi.useFakeTimers();
  useInterviewStore.getState().reset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useInterviewStore", () => {
  it("keeps interview pipeline state transitions observable", () => {
    const store = useInterviewStore.getState();
    store.setState("WAITING_FOR_ANSWER");
    store.setPipelineStatus("recording");
    store.setTranscript("candidate answer");

    expect(useInterviewStore.getState().state).toBe("WAITING_FOR_ANSWER");
    expect(useInterviewStore.getState().pipelineStatus).toBe("recording");
    expect(useInterviewStore.getState().transcript).toBe("candidate answer");
  });

  it("limits retained errors, clears them, and auto-dismisses after 5s", () => {
    const store = useInterviewStore.getState();
    for (let i = 0; i < 8; i += 1) store.pushError(`error-${i}`);

    expect(useInterviewStore.getState().errors).toHaveLength(5);
    expect(useInterviewStore.getState().errors[0].message).toBe("error-3");

    vi.advanceTimersByTime(5000);
    expect(useInterviewStore.getState().errors).toHaveLength(0);

    store.pushError("transient");
    expect(useInterviewStore.getState().errors[0].message).toBe("transient");
    store.clearErrors();
    expect(useInterviewStore.getState().errors).toEqual([]);
  });
});
