import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/**
 * Every Try-On entry point must pass through `useTryOnAvailability`.
 *
 * WHY THIS IS A LINT-STYLE TEST RATHER THAN A RENDER TEST
 * -------------------------------------------------------
 * The rule being protected is "no surface may decide for itself whether
 * try-on works". That is a property of the whole component tree, not of any
 * one component, so rendering one component can never establish it. A new
 * view added next month is exactly the case a render test would miss.
 *
 * THE DEFECT THIS PREVENTS
 * ------------------------
 * `useTryOnAvailability` was introduced because eight consumer entry points
 * each opened the try-on flow unconditionally: a shopper uploaded a photo and
 * waited for a render the backend had already reported it could not produce.
 * The hook fixed the rule, but three call sites were never migrated and kept
 * the old behaviour until 2026-09-27:
 *
 *   - components/stylist/VirtualStylistDrawer.tsx  ("Try this item")
 *   - components/tryon/VisualSearchModal.tsx       ("Try On This Match")
 *   - views/consumer/WardrobeView.tsx
 *
 * Fixing them without pinning the rule would simply wait for the fourth.
 */

const SRC = join(__dirname, "..", "..");

/** Files allowed to call `openTryOn` without consulting the hook. */
const EXEMPT = new Set<string>([
  // The store defines the action; it cannot depend on a hook that reads it.
  "stores/uiStore.ts",
  // The modal is the DESTINATION of a gated call, not an entry point: by the
  // time it renders, the decision to try on has already been made and gated.
  "components/tryon/VirtualTryOnModal.tsx",
]);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "__tests__") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

describe("Try-On availability gate coverage", () => {
  const offenders: string[] = [];

  for (const file of walk(SRC)) {
    const rel = relative(SRC, file).split(/[\\/]/).join("/");
    if (EXEMPT.has(rel)) continue;

    const source = readFileSync(file, "utf8");
    // Only care about files that actually OPEN the flow, not ones that merely
    // name it in a type or a comment.
    if (!/\bopenTryOn\s*[({]/.test(source)) continue;
    if (!source.includes("useTryOnAvailability")) offenders.push(rel);
  }

  it("no surface opens try-on without consulting useTryOnAvailability", () => {
    expect(
      offenders,
      `These files call openTryOn() but never read the availability gate, so ` +
        `they promise a render the engine may have already refused:\n` +
        offenders.map((f) => `  - ${f}`).join("\n") +
        `\n\nUse useTryOnAvailability().gate({ render, fitCheck }) instead, or ` +
        `add the file to EXEMPT with a reason.`,
    ).toEqual([]);
  });
});

/**
 * The gap the test above could not see.
 *
 * `tryOnGateCoverage` asks "if a file OPENS try-on, does it consult the
 * gate?". That is necessary and it is not sufficient: a surface that shows a
 * garment and offers NO try-on at all passes it trivially, because it never
 * calls openTryOn.
 *
 * That blind spot is exactly what shipped. WardrobeView's gap
 * recommendations and MyLooksView's saved-look items both render catalogue
 * garments, and neither had a control — not because anyone decided against
 * it, but because those tiles are not ProductCards and adding one meant
 * copying the whole gate by hand. TryOnButton removed that cost; this test
 * stops the omission recurring.
 */
describe("Try-On reach across consumer garment surfaces", () => {
  /** Consumer surfaces that render a garment a shopper could wear. */
  const GARMENT_SURFACES = [
    "views/consumer/HomeView.tsx",
    "views/consumer/DiscoverView.tsx",
    "views/consumer/ProductDetailView.tsx",
    "views/consumer/WardrobeView.tsx",
    "views/consumer/MyLooksView.tsx",
    "views/consumer/OutfitBuilderView.tsx",
  ];

  /** Any of these means the surface offers try-on. */
  const OFFERS = ["TryOnButton", "ProductCard", "useTryOnAvailability"];

  /** Comments are prose, not behaviour. A file that merely MENTIONS
   *  TryOnButton in a note must still fail — verified by deleting the control
   *  and leaving the comment, which is exactly how the first version of this
   *  test was fooled. */
  const stripComments = (src: string) =>
    src.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/.*$/gm, "$1");

  it.each(GARMENT_SURFACES)("%s offers a try-on control", (rel) => {
    const source = stripComments(readFileSync(join(SRC, rel), "utf8"));
    const offered = OFFERS.some((token) => source.includes(token));
    expect(
      offered,
      `${rel} renders garments but offers no try-on. Render <TryOnButton /> ` +
        `— it carries the availability gate, so there is nothing to re-derive.`,
    ).toBe(true);
  });

  it("the try-on control itself is defined exactly once", () => {
    const definitions = walk(SRC).filter((file) => {
      const src = readFileSync(file, "utf8");
      return /export const TryOnButton|export function TryOnButton/.test(src);
    });
    expect(
      definitions.map((f) => relative(SRC, f)),
      "a second definition would let the two drift apart",
    ).toHaveLength(1);
  });
});
