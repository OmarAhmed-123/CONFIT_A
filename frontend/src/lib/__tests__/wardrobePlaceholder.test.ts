/**
 * The manual-wardrobe frame must decode to real colours.
 *
 * MEASURED DEFECT (2026-10-20): the data URI was built by putting pre-escaped
 * `%23F8FAFC` literals inside `encodeURIComponent`. That escapes the `%` a
 * second time (`%2523`), so a browser decoded `fill="%23F8FAFC"` — not a CSS
 * colour — dropped both fills and painted SVG's initial fill, solid black.
 * Every manually-added wardrobe item rendered as a black tile.
 *
 * The test decodes the payload the way a browser does and asserts the markup
 * a renderer would actually receive. It fails on the old value (colours came
 * out as the literal string `%23F8FAFC`).
 */
import { describe, expect, it } from "vitest";
import { MANUAL_WARDROBE_IMAGE } from "../wardrobePlaceholder";

const CSS_HEX = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

function decodePayload(dataUri: string): string {
  const comma = dataUri.indexOf(",");
  expect(comma).toBeGreaterThan(-1);
  return decodeURIComponent(dataUri.slice(comma + 1));
}

describe("MANUAL_WARDROBE_IMAGE", () => {
  it("is a locally-rendered svg data URI (no network, CSP-safe)", () => {
    expect(MANUAL_WARDROBE_IMAGE.startsWith("data:image/svg+xml;utf8,")).toBe(
      true,
    );
  });

  it("decodes to colours a browser accepts", () => {
    const markup = decodePayload(MANUAL_WARDROBE_IMAGE);
    const fills = [...markup.matchAll(/(?:fill|stroke)="([^"]+)"/g)].map(
      (m) => m[1],
    );

    expect(fills.length).toBeGreaterThanOrEqual(3);
    for (const value of fills) {
      expect(value, `"${value}" is not a CSS hex colour`).toMatch(CSS_HEX);
    }
  });

  it("has no double-encoded escape left in the payload", () => {
    const markup = decodePayload(MANUAL_WARDROBE_IMAGE);

    expect(markup).not.toContain("%23");
    expect(MANUAL_WARDROBE_IMAGE).not.toContain("%2523");
  });

  it("bakes in no text (a string in an image cannot be translated)", () => {
    const markup = decodePayload(MANUAL_WARDROBE_IMAGE);

    expect(markup).not.toMatch(/<text[\s>]/i);
  });
});
