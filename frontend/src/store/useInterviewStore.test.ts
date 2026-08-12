import { beforeEach, describe, expect, it } from "vitest";

import { useInterviewStore } from "@/store/useInterviewStore";

beforeEach(() => {
  useInterviewStore.getState().reset();
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

  it("limits retained errors and clears them", () => {
    const store = useInterviewStore.getState();
    for (let i = 0; i < 8; i += 1) store.pushError(`error-${i}`);

    expect(useInterviewStore.getState().errors).toHaveLength(5);
    expect(useInterviewStore.getState().errors[0]).toBe("error-3");
    store.clearErrors();
    expect(useInterviewStore.getState().errors).toEqual([]);
  });
});
