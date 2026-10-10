/**
 * Mode A photo attachments. The client refuses what the backend would refuse,
 * with a specific reason, and reduces ordinary phone photos to the per-image
 * limit the backend enforces (1 MB, JPEG/PNG/WebP, up to 3 per message).
 *
 * jsdom has no canvas or ImageBitmap, so the resize path is covered only for the
 * refusal branch here. The real resize is verified in the browser gate.
 */
import { describe, it, expect } from "vitest";
import {
  validateStylistImage,
  prepareStylistImage,
  targetDimensions,
  STYLIST_ATTACH_MAX_BYTES,
  STYLIST_ATTACH_MAX_SOURCE_BYTES,
  STYLIST_ATTACH_MAX_IMAGES,
} from "../stylistImageAttach";

describe("validateStylistImage", () => {
  it("accepts JPEG, PNG or WebP", () => {
    for (const type of ["image/jpeg", "image/png", "image/webp"]) {
      expect(validateStylistImage({ type, size: 1000 }, 0)).toBeNull();
    }
  });

  it("rejects other formats such as GIF or SVG", () => {
    expect(validateStylistImage({ type: "image/gif", size: 1000 }, 0)).toBe("type");
    expect(validateStylistImage({ type: "image/svg+xml", size: 1000 }, 0)).toBe("type");
  });

  it("accepts an ordinary phone photo above 1 MB (it is reduced before sending)", () => {
    expect(validateStylistImage({ type: "image/jpeg", size: 4 * 1024 * 1024 }, 0)).toBeNull();
  });

  it("refuses a source file above the browser's reduction ceiling", () => {
    expect(validateStylistImage({ type: "image/jpeg", size: STYLIST_ATTACH_MAX_SOURCE_BYTES + 1 }, 0)).toBe("source_size");
  });

  it("refuses a fourth photo in one message", () => {
    expect(validateStylistImage({ type: "image/png", size: 10 }, STYLIST_ATTACH_MAX_IMAGES)).toBe("count");
    expect(validateStylistImage({ type: "image/png", size: 10 }, STYLIST_ATTACH_MAX_IMAGES - 1)).toBeNull();
  });
});

describe("prepareStylistImage", () => {
  it("sends a photo that is already within 1 MB exactly as chosen", async () => {
    const file = new Blob([new Uint8Array(1200)], { type: "image/png" });
    const out = await prepareStylistImage(file);
    expect("dataUrl" in out && out.dataUrl.startsWith("data:")).toBe(true);
  });

  it("refuses a large photo it cannot decode, rather than sending it anyway", async () => {
    const big = new Blob([new Uint8Array(STYLIST_ATTACH_MAX_BYTES + 10)], { type: "image/jpeg" });
    expect(await prepareStylistImage(big)).toEqual({ error: "size" });
  });
});

describe("targetDimensions", () => {
  it("scales the longer side down and keeps the aspect ratio", () => {
    expect(targetDimensions(4000, 3000, 1600)).toEqual({ width: 1600, height: 1200 });
    expect(targetDimensions(3000, 4000, 1600)).toEqual({ width: 1200, height: 1600 });
  });

  it("never enlarges a small image", () => {
    expect(targetDimensions(800, 600, 1600)).toEqual({ width: 800, height: 600 });
  });

  it("returns zero for an invalid size", () => {
    expect(targetDimensions(0, 600, 1600)).toEqual({ width: 0, height: 0 });
  });
});
