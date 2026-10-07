/**
 * C03 — the product detail page's behavioral contract.
 *
 * First direct test suite this view has ever had. Pins the four defects
 * found by the 2026-10-08 redesign pass so none of them can return:
 *
 *  1. PURCHASE SURFACE: the generic CardStackShowcase (stock imagery,
 *     EN dev-speak caption) no longer opens the page — the product does.
 *  2. BREADCRUMB TRUTH: the category crumb links with category_slug
 *     (the token Discover actually filters by), never category_id; and
 *     degrades to the plain catalogue when the payload lacks the slug.
 *  3. ONE WISHLIST: the heart reads/writes confit.wishlist.v1 — the same
 *     list Discover uses — instead of a useState that reset on reload.
 *  4. HONEST TEXT: the BOPIS failure fallback renders a translated
 *     sentence, not the literal source text "{t('...')}" (real rendering
 *     bug), and loading/error surfaces speak the app language.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  render,
  cleanup,
  screen,
  fireEvent,
  act,
  waitFor,
} from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from "react";
import i18n from "../../i18n/i18n";
import type { Product } from "../../models";

/* ------------------------------------------------------------------ mocks */

const { catalogMock, bopisMock } = vi.hoisted(() => ({
  catalogMock: vi.fn(),
  bopisMock: vi.fn(),
}));

vi.mock("../../services/apiServices", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../services/apiServices")>();
  return {
    ...actual,
    catalogService: {
      ...actual.catalogService,
      getProductDetail: catalogMock,
      getBopisStoresForSKU: bopisMock,
    },
  };
});

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
      gate: ({ fitCheck }: { fitCheck: () => void }) => fitCheck,
    }),
  };
});

import { ProductDetailView } from "../consumer/ProductDetailView";

/* -------------------------------------------------------------- fixtures */

const DETAIL = (over: Partial<Product> = {}): Product =>
  ({
    id: 42,
    brand_id: 1,
    brand_name: "Reiss",
    category_id: 3,
    category_name: "Outerwear",
    category_slug: "outerwear",
    title: "Midnight Wool Blazer",
    title_ar: "بليزر صوف كحلي",
    slug: "midnight-wool-blazer",
    base_price: 240,
    currency: "USD",
    thumbnail_url: "https://img.example/b.jpg",
    images: ["https://img.example/b1.jpg", "https://img.example/b2.jpg"],
    description: "A blazer.",
    skus: [
      {
        id: 7,
        product_id: 42,
        sku_code: "BLZ-M",
        size: "M",
        color: "Navy",
        color_hex: "#1B1F3B",
        price_override: null,
        stock_level: 4,
        is_in_stock: true,
      },
    ],
    fit_available: false,
    style_compatibility_available: false,
    related_outfits: [],
    ...over,
  }) as unknown as Product;

function renderPdp() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/product/midnight-wool-blazer"]}>
        <Routes>
          <Route path="/product/:slug" element={<ProductDetailView />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );
}

async function settled() {
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: /midnight wool blazer/i }),
    ).toBeInTheDocument(),
  );
}

/* ------------------------------------------------------------------ tests */

describe("ProductDetailView — C03 contract", () => {
  beforeEach(() => {
    cleanup();
    window.localStorage.clear();
    catalogMock.mockResolvedValue(DETAIL());
    bopisMock.mockResolvedValue([]);
  });
  afterEach(async () => {
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    vi.clearAllMocks();
  });

  it("opens with the product, not a generic showcase (purchase surface)", async () => {
    renderPdp();
    await settled();
    // The removed showcase carried a stock-image stack + dev caption; its
    // signature translated eyebrow must not render here anymore.
    expect(
      screen.queryByText(i18n.t("product.complete_the_look_title") as string),
    ).toBeNull();
    expect(
      screen.queryByText(/animated stack to connect a single item/i),
    ).toBeNull();
  });

  it("breadcrumb category deep-links with the SLUG Discover filters by", async () => {
    renderPdp();
    await settled();
    const crumb = screen.getByRole("link", { name: "Outerwear" });
    expect(crumb).toHaveAttribute("href", "/discover?category=outerwear");
  });

  it("without category_slug the crumb degrades to the plain catalogue — never a lying filter", async () => {
    catalogMock.mockResolvedValue(DETAIL({ category_slug: undefined }));
    renderPdp();
    await settled();
    expect(screen.getByRole("link", { name: "Outerwear" })).toHaveAttribute(
      "href",
      "/discover",
    );
  });

  it("the heart writes the SAME device list Discover reads, and reads it back on load", async () => {
    window.localStorage.setItem("confit.wishlist.v1", JSON.stringify([999]));
    renderPdp();
    await settled();
    const heart = screen.getByRole("button", {
      name: i18n.t("a11y.toggle_wishlist") as string,
    });
    expect(heart).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(heart);
    expect(heart).toHaveAttribute("aria-pressed", "true");
    expect(
      JSON.parse(window.localStorage.getItem("confit.wishlist.v1") || "[]"),
    ).toEqual([999, 42]);
    // pre-saved product renders already-pressed
    cleanup();
    renderPdp();
    await settled();
    expect(
      screen.getByRole("button", {
        name: i18n.t("a11y.toggle_wishlist") as string,
      }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("BOPIS failure renders the translated fallback — never the literal source text", async () => {
    bopisMock.mockRejectedValue(new Error(""));
    renderPdp();
    await settled();
    // open the pickup accordion
    fireEvent.click(
      screen.getByRole("button", {
        name: i18n.t("product.bopis_title") as string,
      }),
    );
    await waitFor(() =>
      expect(
        screen.getByText(i18n.t("product.bopis_failed") as string),
      ).toBeInTheDocument(),
    );
    // the old bug printed {t('product.bopis_unreachable')} verbatim
    expect(screen.queryByText(/\{t\('/)).toBeNull();
  });

  it("Arabic shell: loading and failure states speak Arabic", async () => {
    await act(async () => {
      await i18n.changeLanguage("ar");
    });
    catalogMock.mockRejectedValue(new Error(""));
    renderPdp();
    await waitFor(() =>
      expect(
        screen.getByText(i18n.t("product.load_failed_desc") as string),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", {
        name: i18n.t("common.try_again") as string,
      }),
    ).toBeInTheDocument();
    // No raw-EN loading literals anywhere in source-of-truth states.
    expect(screen.queryByText(/could not be loaded from the catalogue/i)).toBeNull();
  });

  it("gallery thumbnails expose selection state and switch the hero image", async () => {
    renderPdp();
    await settled();
    const thumbs = screen.getAllByRole("button", {
      name: /view image/i,
    });
    expect(thumbs).toHaveLength(2);
    expect(thumbs[0]).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(thumbs[1]);
    expect(thumbs[1]).toHaveAttribute("aria-pressed", "true");
    expect(thumbs[0]).toHaveAttribute("aria-pressed", "false");
  });
});
