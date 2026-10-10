/**
 * Mode A photo attachments: the client refuses what the backend would refuse,
 * with a specific reason, before any bytes are sent.
 */
import { describe, it, expect } from "vitest";
import { validateStylistImage, STYLIST_ATTACH_MAX_BYTES } from "../stylistImageAttach";

describe("validateStylistImage", () => {
  it("accepts a small JPEG, PNG or WebP", () => {
    for (const type of ["image/jpeg", "image/png", "image/webp"]) {
      expect(validateStylistImage({ type, size: 1000 }, 0)).toBeNull();
    }
  });

  it("rejects other formats such as GIF or SVG", () => {
    expect(validateStylistImage({ type: "image/gif", size: 1000 }, 0)).toBe("type");
    expect(validateStylistImage({ type: "image/svg+xml", size: 1000 }, 0)).toBe("type");
  });

  it("rejects an image over 1 MB", () => {
    expect(validateStylistImage({ type: "image/png", size: STYLIST_ATTACH_MAX_BYTES + 1 }, 0)).toBe("size");
    expect(validateStylistImage({ type: "image/png", size: STYLIST_ATTACH_MAX_BYTES }, 0)).toBeNull();
  });

  it("refuses a fourth photo in one message", () => {
    expect(validateStylistImage({ type: "image/png", size: 10 }, 3)).toBe("count");
    expect(validateStylistImage({ type: "image/png", size: 10 }, 2)).toBeNull();
  });
});
