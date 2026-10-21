/**
 * A brand tile must survive a failed logo, and must not invent copy.
 *
 * MEASURED DEFECTS (2026-10-20)
 * -----------------------------
 * 1. `BrandCard` rendered a bare <img src={brand.logo_url}> with no error
 *    handler. The live catalogue serves `images.unsplash.com` for all four
 *    brands, so any 404 / rate-limit / proxy block left the browser's
 *    broken-image glyph in a 56px tile — indistinguishable from a bug.
 * 2. The tile's subtitle was `brand.description || 'Curated European fashion
 *    house'`, printed in the same type as real copy. A brand that never wrote
 *    a description had one written for it. Honest-UI rule: an absent field
 *    renders nothing, it does not render a plausible sentence.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import React from "react";
import i18n from "../../../i18n/i18n";
import type { CustomerBrand } from "../../../models";
import { BrandCard } from "../BrandCard";

const BRAND = (over: Partial<CustomerBrand> = {}): CustomerBrand =>
  ({
    id: 3,
    brand_name: "Riven Studio",
    slug: "riven-studio",
    logo_url: "https://images.unsplash.com/photo-1441984904996.jpg",
    description: null,
    is_verified: true,
    return_rate_benchmark: 30,
    current_return_rate: 7,
    total_products: 5,
    stores_count: 2,
    cities: ["Cairo"],
    categories: ["Dresses"],
    active_promotions_count: 0,
    promotions: [],
    sample_products: [],
    ...over,
  }) as unknown as CustomerBrand;

function renderCard(brand = BRAND()) {
  return render(
    <I18nextProvider i18n={i18n}>
      <BrandCard brand={brand} onSelect={() => {}} />
    </I18nextProvider>,
  );
}

describe("BrandCard — asset honesty", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the logo when one is served", () => {
    renderCard();

    expect(screen.getByTestId("brand-logo")).toBeInTheDocument();
    expect(screen.queryByTestId("brand-monogram")).toBeNull();
  });

  it("never captions an unverifiable image as an official logo", () => {
    /*
     * `logo_url` is free text and nothing in the schema proves it is a brand
     * mark. Measured 2026-10-20: all four live values are Unsplash photographs.
     * The tile must therefore make NO claim that the image is a logo — the
     * brand name is already the adjacent <h3>, so the image is decorative.
     */
    renderCard();

    const img = screen.getByTestId("brand-logo");
    expect(img.getAttribute("alt")).toBe("");
    expect(img.getAttribute("aria-hidden")).toBe("true");
    expect(screen.queryByAltText(/logo/i)).toBeNull();
  });

  it("falls back to the monogram when the logo fails to load", () => {
    renderCard();

    fireEvent.error(screen.getByTestId("brand-logo"));

    expect(screen.queryByTestId("brand-logo")).toBeNull();
    const monogram = screen.getByTestId("brand-monogram");
    expect(monogram.textContent).toBe("RI");
  });

  it("uses the monogram when the brand has no logo at all", () => {
    renderCard(BRAND({ logo_url: null }));

    expect(screen.queryByTestId("brand-logo")).toBeNull();
    expect(screen.getByTestId("brand-monogram").textContent).toBe("RI");
  });

  it("never writes a description the brand did not supply", () => {
    renderCard(BRAND({ description: null }));

    expect(screen.queryByText(/Curated European fashion house/i)).toBeNull();
  });

  it("shows a real description verbatim", () => {
    renderCard(BRAND({ description: "Cairo atelier, since 2019." }));

    expect(
      screen.getByText("Cairo atelier, since 2019."),
    ).toBeInTheDocument();
  });
});
