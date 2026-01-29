import { describe, it, expect } from "vitest";

// Example utility function (would be in src/lib/example.ts)
function add(a: number, b: number): number {
  return a + b;
}

describe("Example Test Suite", () => {
  describe("add function", () => {
    it("should add two positive numbers", () => {
      expect(add(2, 3)).toBe(5);
    });

    it("should handle negative numbers", () => {
      expect(add(-1, 1)).toBe(0);
    });

    it("should handle zero", () => {
      expect(add(0, 5)).toBe(5);
    });
  });
});
