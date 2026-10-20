import { describe, expect, it } from "vitest";
import { safeNextPath } from "./redirect";

describe("safeNextPath", () => {
  it("acepta rutas internas", () => {
    expect(safeNextPath("/es/history?x=1")).toBe("/es/history?x=1");
  });

  it.each([null, undefined, "", "https://evil.com", "//evil.com", "/\\evil.com", "es", "/a\nb"])(
    "rechaza %j",
    (value) => {
      expect(safeNextPath(value, "/es")).toBe("/es");
    },
  );
});
