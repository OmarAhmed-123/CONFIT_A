/**
 * The storefront must render the language the page is in.
 *
 * MEASURED DEFECT (2026-10-20, Arabic storefront, real browser)
 * ------------------------------------------------------------
 * All 12 production products have a populated `title_ar`, and the product page
 * already used it for the DOCUMENT title — but the visible `<h1>` and the
 * product card rendered `product.title`, so an RTL Arabic page displayed an
 * English product name under an Arabic breadcrumb. The tab and the page
 * disagreed with each other on the same screen.
 */
import { describe, it, expect } from "vitest";
import { localizedTitle, localizedDescription } from "../localizedText";

const EN = "Silk Slip Column Maxi Dress";
const AR = "فستان ماكسي حرير بتصميم عمودي";

describe("localizedTitle", () => {
  it("returns the Arabic title for an Arabic page", () => {
    expect(localizedTitle({ title: EN, title_ar: AR }, "ar")).toBe(AR);
  });

  it("returns the English title for an English page", () => {
    expect(localizedTitle({ title: EN, title_ar: AR }, "en")).toBe(EN);
  });

  it("handles regional tags (ar-EG, en-GB)", () => {
    expect(localizedTitle({ title: EN, title_ar: AR }, "ar-EG")).toBe(AR);
    expect(localizedTitle({ title: EN, title_ar: AR }, "en-GB")).toBe(EN);
  });

  it("falls back to the other language rather than rendering nothing", () => {
    expect(localizedTitle({ title: EN, title_ar: null }, "ar")).toBe(EN);
    expect(localizedTitle({ title: EN, title_ar: "" }, "ar")).toBe(EN);
    expect(localizedTitle({ title: EN, title_ar: "   " }, "ar")).toBe(EN);
  });

  it("treats a blank primary as missing, not as a valid empty heading", () => {
    // An invisible <h1> is worse than an honest English fallback.
    expect(localizedTitle({ title: "", title_ar: AR }, "en")).toBe(AR);
  });

  it("never invents a title when both are absent", () => {
    expect(localizedTitle({ title: null, title_ar: null }, "ar")).toBe("");
    expect(localizedTitle(null, "ar")).toBe("");
    expect(localizedTitle(undefined, "en")).toBe("");
  });

  it("defaults to the English field when the language is unknown", () => {
    expect(localizedTitle({ title: EN, title_ar: AR }, undefined)).toBe(EN);
  });
});

describe("localizedDescription", () => {
  it("mirrors the title rule for long-form copy", () => {
    const item = { description: "A dress.", description_ar: "فستان." };
    expect(localizedDescription(item, "ar")).toBe("فستان.");
    expect(localizedDescription(item, "en")).toBe("A dress.");
  });

  it("falls back when the Arabic body is missing", () => {
    expect(localizedDescription({ description: "A dress.", description_ar: "" }, "ar")).toBe(
      "A dress.",
    );
  });
});
