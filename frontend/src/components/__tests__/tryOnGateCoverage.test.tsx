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
