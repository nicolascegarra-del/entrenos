import { describe, expect, it } from "vitest";

import { timeAgo } from "./time-ago";

describe("timeAgo", () => {
  const now = new Date("2026-10-23T12:00:00Z");
  it("formatea en español", () => {
    expect(timeAgo(null, now)).toBe("nunca");
    expect(timeAgo("2026-10-23T11:59:30Z", now)).toBe("ahora");
    expect(timeAgo("2026-10-23T11:48:00Z", now)).toBe("hace 12 min");
    expect(timeAgo("2026-10-23T09:00:00Z", now)).toBe("hace 3 h");
    expect(timeAgo("2026-10-22T10:00:00Z", now)).toBe("hace 1 día");
    expect(timeAgo("2026-10-20T10:00:00Z", now)).toBe("hace 3 días");
  });
});
