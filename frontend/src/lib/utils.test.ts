import { describe, expect, it } from "vitest";

import { classificationColor, formatDuration } from "@/lib/utils";

describe("formatDuration", () => {
  it("formats minutes and seconds", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(65)).toBe("01:05");
    expect(formatDuration(null)).toBe("—");
  });
});

describe("classificationColor", () => {
  it("returns distinct styles for allowed classifications", () => {
    expect(classificationColor("Correct")).toContain("emerald");
    expect(classificationColor("Incorrect")).toContain("red");
    expect(classificationColor("Partially Correct")).toContain("amber");
    expect(classificationColor("Not Confirmed")).toContain("slate");
  });
});
