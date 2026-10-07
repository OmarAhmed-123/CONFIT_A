/**
 * C02 — the ProductCard detail-entry LINK contract.
 *
 * THE DEFECT THIS PINS (found by the 2026-10-07 Discover goal pass)
 * -----------------------------------------------------------------
 * Every detail entry on the card — the image, the title, the "View
 * details" footer action — navigated ONLY through a JS onClick. No real
 * `<a href>` existed anywhere on the card, so middle-click / new-tab /
 * copy-link were impossible, crawlers saw no product URLs, and the `<h3>`
 * title had a bare onClick with no role or tabindex (mouse-only).
 *
 * THE CONTRACT
 * ------------
 *  1. With NO `onOpenDetails` override (every production call site today),
 *     the image, the title and the footer action are REAL links whose
 *     href is `/product/<slug>` — the user agent owns the navigation.
 *  2. With an `onOpenDetails` override (a modal/drawer consumer), the same
 *     entries are buttons that call the override — a link that pretends to
 *     navigate but opens a drawer would be the opposite lie.
 *  3. Side actions (wishlist, try-on/fit-check, add-to-bag) stay BUTTONS
 *     in both modes: they mutate state, they do not navigate.
 *  4. No interactive element nests inside another (a11y: nested
 *     interactives are unreachable for AT users).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from "react";
import i18n from "../../i18n/i18n";
import type { Product } from "../../models";

/* ------------------------------------------------------------------ mocks */

vi.mock("../../hooks/useTryOnAvailability", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../hooks/useTryOnAvailability")>();
  return {
    ...actual,
    useTryOnAvailability: () => ({
      engineState: "offline",
      renderAvailable: false,
      isProbing: false,
      retryAfterSeconds: 0,
      errorCode: null,
      userMessage: null,
      upstreamDetail: null,
      ctaKind: () => "fit_check" as const,
      gate: () => () => {},
    }),
  };
});

import { ProductCard } from "../product/ProductCard";

/* --------------------------------------------------------------- fixtures */

const PRODUCT = {
  id: 7,
  title: "Midnight Wool Blazer",
  slug: "midnight-wool-blazer",
  brand_name: "Reiss",
  base_price: 240,
  thumbnail_url: "https://img.example/blazer.jpg",
} as unknown as Product;

function renderCard(props: Partial<React.ComponentProps<typeof ProductCard>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={["/discover"]}>
          <Routes>
            <Route
              path="/discover"
              element={<ProductCard product={PRODUCT} {...props} />}
            />
            <Route
              path="/product/:slug"
              element={<div data-testid="pdp-stub">PDP</div>}
            />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

const HREF = "/product/midnight-wool-blazer";

/* ------------------------------------------------------------------ tests */

describe("ProductCard — detail entries are real links (C02 contract)", () => {
  beforeEach(() => {
    cleanup();
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("image, title and footer action all expose href=/product/<slug> when the card navigates", () => {
    renderCard({ onAddToBag: vi.fn() });
    const links = screen.getAllByRole("link");
    // Exactly the three detail entries — nothing else may masquerade as
    // navigation.
    expect(links).toHaveLength(3);
    for (const link of links) {
      expect(link).toHaveAttribute("href", HREF);
    }
    // The title link carries the product name so SR users hear a
    // meaningful destination, not "link".
    expect(
      screen.getAllByRole("link", { name: /midnight wool blazer/i }).length,
    ).toBeGreaterThan(0);
  });

  it("clicking the title link performs a real route navigation", () => {
    renderCard();
    const title = screen.getByRole("heading", { level: 3 });
    fireEvent.click(within(title).getByRole("link"));
    expect(screen.getByTestId("pdp-stub")).toBeInTheDocument();
  });

  it("with an onOpenDetails override the same entries are buttons that call it — never fake links", () => {
    const onOpenDetails = vi.fn();
    renderCard({ onOpenDetails, onAddToBag: vi.fn() });
    // No navigation claim anywhere on the card in override mode.
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    const title = screen.getByRole("heading", { level: 3 });
    fireEvent.click(within(title).getByRole("button"));
    expect(onOpenDetails).toHaveBeenCalledTimes(1);
    expect(onOpenDetails).toHaveBeenCalledWith(PRODUCT);
  });

  it("side actions stay buttons and never nest inside a link", () => {
    renderCard({
      onAddToBag: vi.fn(),
      isWishlisted: false,
      onToggleWishlist: vi.fn(),
    });
    const wishlist = screen.getByRole("button", {
      name: i18n.t("a11y.toggle_wishlist"),
    });
    expect(wishlist).toBeInTheDocument();
    // No interactive element may live inside another interactive element.
    for (const el of [
      ...screen.getAllByRole("link"),
      ...screen.getAllByRole("button"),
    ]) {
      expect(
        el.parentElement?.closest("a, button"),
        `${el.tagName} "${el.getAttribute("aria-label") ?? el.textContent}" is nested inside another interactive element`,
      ).toBeNull();
    }
  });
});
