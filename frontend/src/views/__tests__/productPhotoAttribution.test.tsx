/**
 * Whose photograph is on screen — the disclosure the PDP used to drop.
 *
 * MEASURED DEFECT (2026-10-20, production, read-only)
 * ---------------------------------------------------
 * ``GET /api/v1/catalog/products/silk-slip-column-maxi-dress`` served ten
 * assets and every one of them carried::
 *
 *     "source_type": "stock",
 *     "attribution": "Photo: Unsplash"
 *
 * The page rendered the picture and nothing else. ``Product`` did not even
 * declare ``media``, so the field was dropped on parse: licensed editorial
 * imagery was presented exactly like the boutique's own studio shot. The
 * constitution's rule is "evidence before appearance" — if the server knows
 * the photograph is licensed stock, the shopper is entitled to know it too.
 *
 * These tests pin the contract:
 *
 *  A. stock photography is disclosed, using the credit string the SERVER sent;
 *  B. one credit is shown once, no matter how many ratios repeat it;
 *  C. first-party photography ("own") is not labelled as stock;
 *  D. a payload without media renders no claim at all — nothing is invented;
 *  E. the disclosure is translated in Arabic rather than leaking English.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup, screen, waitFor, act } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from "react";
import i18n from "../../i18n/i18n";
import type { Product, ProductMedia } from "../../models";

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

const media = (over: Partial<ProductMedia> = {}): ProductMedia => ({
  ratio: "4x5",
  url: "/api/v1/media/products/5/5-4x5.jpg",
  width: 1200,
  height: 1500,
  format: "jpeg",
  source_type: "stock",
  attribution: "Photo: Unsplash",
  is_primary: true,
  ...over,
});

const DETAIL = (over: Partial<Product> = {}): Product =>
  ({
    id: 42,
    brand_id: 1,
    brand_name: "Riven Studio",
    category_id: 3,
    category_name: "Dresses",
    category_slug: "dresses",
    title: "Silk Slip Column Maxi Dress",
    title_ar: "فستان ساتان طويل",
    slug: "silk-slip-column-maxi-dress",
    base_price: 240,
    currency: "USD",
    thumbnail_url: "/api/v1/media/products/5/5-4x5.jpg",
    images: ["/api/v1/media/products/5/5-4x5.jpg"],
    description: "A dress.",
    skus: [
      {
        id: 7,
        product_id: 42,
        sku_code: "DRS-M",
        size: "M",
        color: "Gold",
        color_hex: "#C8A45C",
        price_override: null,
        stock_level: 4,
        is_in_stock: true,
      },
    ],
    fit_available: false,
    style_compatibility_available: false,
    related_outfits: [],
    media: [media()],
    ...over,
  }) as unknown as Product;

function renderPdp() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/product/silk-slip-column-maxi-dress"]}>
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
      screen.getByRole("heading", { name: /silk slip column maxi dress/i }),
    ).toBeInTheDocument(),
  );
}

const note = () => screen.queryByTestId("product-photo-attribution");

describe("ProductDetailView — photo attribution", () => {
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

  it("discloses licensed stock photography and names the credit", async () => {
    renderPdp();
    await settled();

    expect(note()).not.toBeNull();
    expect(note()!.textContent).toContain("Photo: Unsplash");
    expect(note()!.textContent?.toLowerCase()).toContain("stock");
  });

  it("shows one credit once even though every ratio repeats it", async () => {
    catalogMock.mockResolvedValue(
      DETAIL({
        media: [
          media({ ratio: "4x5" }),
          media({ ratio: "4x5", url: "/x.webp", format: "webp" }),
          media({ ratio: "1x1" }),
          media({ ratio: "3x2" }),
          media({ ratio: "16x9" }),
        ],
      }),
    );
    renderPdp();
    await settled();

    const occurrences = (note()!.textContent?.match(/Photo: Unsplash/g) ?? [])
      .length;
    expect(occurrences).toBe(1);
  });

  it("does not call first-party photography stock", async () => {
    catalogMock.mockResolvedValue(
      DETAIL({
        media: [
          media({ source_type: "own", attribution: null }),
          media({ ratio: "1x1", source_type: "own", attribution: null }),
        ],
      }),
    );
    renderPdp();
    await settled();

    expect(note()).toBeNull();
  });

  it("makes no claim at all when the payload carries no media", async () => {
    catalogMock.mockResolvedValue(DETAIL({ media: undefined }));
    renderPdp();
    await settled();

    expect(note()).toBeNull();
  });

  it("translates the disclosure in Arabic", async () => {
    await act(async () => {
      await i18n.changeLanguage("ar");
    });
    renderPdp();
    await settled();

    expect(note()).not.toBeNull();
    expect(note()!.textContent).toContain("مرخّصة");
  });
});
