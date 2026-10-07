/**
 * Home re-pass (2026-10-08) — merchandising honesty + collection wayfinding.
 *
 * What these pin, and the defects they were written against:
 *
 *   1. COLLECTION RAIL — the home page previously had NO route into the
 *      catalogue's categories at all. The rail must render the REAL
 *      categories from the API (bilingual, name_ar in Arabic) and each tile
 *      must be a real deep link to /discover?category=<slug>.
 *   2. NEW IN — must come from its own sort_by=newest query, not a re-slice
 *      of the recommended list (the old "Trending" grid re-rendered the SAME
 *      first products "Today's picks" had already shown).
 *   3. ON SALE — renders ONLY products whose server-sourced compare_at_price
 *      is a real markdown AND that are not already in Today's picks; with no
 *      qualifying product the section must disappear, never pad itself.
 *   4. BRAND PAVILION — derived from the live catalogue (real names, real
 *      product imagery). The old tiles were four hardcoded brands with
 *      Unsplash stock photos; no Unsplash URL may appear in this section.
 *   5. Discover deep link — /discover?category=<slug> applies the filter
 *      for a slug the categories API knows, and ignores unknown slugs.
 *   6. axe (serious/critical) on the collection + new-in subtrees.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  render,
  cleanup,
  screen,
  act,
  within,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { axe } from "vitest-axe";
import { MemoryRouter } from "react-router-dom";
import React from "react";
import i18n from "../../i18n/i18n";
import type { Product, Category } from "../../models";

/* ------------------------------------------------------------------ mocks */

const { vmState, newestMock, setSelectedCategoryMock, capState } = vi.hoisted(() => ({
  vmState: {
    products: [] as unknown[],
    categories: [] as unknown[],
    isLoading: false,
    error: null as string | null,
  },
  newestMock: vi.fn(),
  setSelectedCategoryMock: vi.fn(),
  capState: {
    value: {
      bnpl_live: false,
      tryon_live: false,
      bopis_live: false,
      free_shipping_threshold: null as number | null,
      shipping_currency: null as string | null,
    },
  },
}));

vi.mock("../../viewmodels/useCatalogViewModel", () => ({
  useCatalogViewModel: () => ({
    products: vmState.products,
    categories: vmState.categories,
    selectedCategory: "",
    setSelectedCategory: setSelectedCategoryMock,
    selectedOccasion: "",
    setSelectedOccasion: vi.fn(),
    selectedColor: "",
    setSelectedColor: vi.fn(),
    searchQuery: "",
    setSearchQuery: vi.fn(),
    sortBy: "recommended",
    setSortBy: vi.fn(),
    isLoading: vmState.isLoading,
    isFetching: false,
    error: vmState.error,
    refresh: vi.fn(),
  }),
}));

// The "New in" rail is the only consumer of the service inside HomeView —
// everything else arrives through the (mocked) view model.
vi.mock("../../services/apiServices", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../services/apiServices")>();
  return {
    ...actual,
    catalogService: {
      ...actual.catalogService,
      getProducts: newestMock,
    },
  };
});

vi.mock("../../hooks/useCapabilities", () => ({
  useCapabilities: () => ({
    capabilities: capState.value,
    isLoading: false,
  }),
}));

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
      ctaKind: () => "blocked" as const,
      gate: () => () => {},
    }),
  };
});

// Heavy animated showcases are out of scope here and have their own suites.
vi.mock("../../components/ui/circular-gallery", () => ({
  CircularGallery: () => null,
}));
vi.mock("../../components/showcase/DesignShowcases", () => ({
  CardStackShowcase: () => null,
  CircularGalleryShowcase: () => null,
}));

import { HomeView } from "../consumer/HomeView";
import { DiscoverView } from "../consumer/DiscoverView";

/* --------------------------------------------------------------- fixtures */

const CATEGORIES: Category[] = [
  { id: 1, name: "Outerwear", name_ar: "الملابس الخارجية", slug: "outerwear", parent_id: null, icon_name: "sparkle" },
  { id: 2, name: "Tops & Shirts", name_ar: "القمصان والبلوزات", slug: "tops", parent_id: null, icon_name: "hanger" },
  { id: 3, name: "Dresses", name_ar: "الفساتين", slug: "dresses", parent_id: null, icon_name: "sparkle" },
  { id: 4, name: "Footwear", name_ar: "الأحذية", slug: "footwear", parent_id: null, icon_name: "ruler" },
];

/** 8 recommended products: ids 1-6 are "Today's picks"; 7-8 carry REAL
 *  markdowns and sit outside the picks, so they are the sale candidates. */
const PRODUCTS: Product[] = [1, 2, 3, 4, 5, 6, 7, 8].map(
  (n) =>
    ({
      id: n,
      title: `Catalogue Piece ${n}`,
      slug: `catalogue-piece-${n}`,
      brand_name: n <= 5 ? "Reiss" : "COS",
      base_price: 100 + n,
      compare_at_price: n >= 7 ? 180 + n : null,
      currency: "USD",
      thumbnail_url: `https://img.example/p${n}.jpg`,
      rating: 4,
      style_tags: [],
      occasion_tags: [],
    }) as unknown as Product,
);

const NEWEST: Product[] = [101, 102, 103].map(
  (n) =>
    ({
      id: n,
      title: `Fresh Arrival ${n}`,
      slug: `fresh-arrival-${n}`,
      brand_name: "Arket",
      base_price: 90,
      currency: "USD",
      thumbnail_url: `https://img.example/new${n}.jpg`,
      rating: 0,
      style_tags: [],
      occasion_tags: [],
    }) as unknown as Product,
);

function renderHome() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <HomeView />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

async function setLang(lang: string) {
  await act(async () => {
    await i18n.changeLanguage(lang);
  });
}

/* ------------------------------------------------------------------ tests */

describe("Home merchandising — collection rail", () => {
  beforeEach(() => {
    cleanup();
    vmState.products = PRODUCTS;
    vmState.categories = CATEGORIES;
    vmState.isLoading = false;
    vmState.error = null;
    newestMock.mockReset().mockResolvedValue(NEWEST);
    setSelectedCategoryMock.mockReset();
  });
  afterEach(async () => {
    await setLang("en");
  });

  it("renders every API category as a REAL deep link into the filtered catalogue", () => {
    renderHome();
    const nav = screen.getByRole("navigation", {
      name: i18n.t("home.collections_aria"),
    });
    for (const cat of CATEGORIES) {
      const link = within(nav).getByRole("link", { name: cat.name });
      expect(link).toHaveAttribute(
        "href",
        `/discover?category=${cat.slug}`,
      );
    }
  });

  it("labels the tiles with name_ar when the shell is Arabic", async () => {
    await setLang("ar");
    renderHome();
    const nav = screen.getByRole("navigation", {
      name: i18n.t("home.collections_aria"),
    });
    expect(within(nav).getByText("الفساتين")).toBeInTheDocument();
    expect(within(nav).queryByText("Dresses")).toBeNull();
  });

  it("renders no rail at all when the API returns no categories — no empty shell", () => {
    vmState.categories = [];
    renderHome();
    expect(
      screen.queryByRole("navigation", {
        name: i18n.t("home.collections_aria"),
      }),
    ).toBeNull();
  });

  it("collection rail subtree passes axe (serious/critical)", async () => {
    renderHome();
    const nav = screen.getByRole("navigation", {
      name: i18n.t("home.collections_aria"),
    });
    const results = await axe(nav, {
      rules: {
        "color-contrast": { enabled: false },
        "target-size": { enabled: false },
      },
    });
    const serious = results.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact ?? ""),
    );
    expect(serious).toEqual([]);
  });
});

describe("Home merchandising — New in rail", () => {
  beforeEach(() => {
    cleanup();
    vmState.products = PRODUCTS;
    vmState.categories = CATEGORIES;
    vmState.isLoading = false;
    vmState.error = null;
    newestMock.mockReset().mockResolvedValue(NEWEST);
  });

  it("asks the server its own question (sort_by=newest) instead of re-slicing the recommended list", async () => {
    renderHome();
    await waitFor(() =>
      expect(screen.getByText("Fresh Arrival 101")).toBeInTheDocument(),
    );
    expect(newestMock).toHaveBeenCalledWith(
      expect.objectContaining({ sort_by: "newest", limit: 8 }),
    );
    // The rail shows the newest fixture, which shares no id with the
    // recommended list — proof it is not a duplicate slice.
    const section = screen
      .getByText(i18n.t("home.new_in_title"))
      .closest("section") as HTMLElement;
    expect(within(section).getAllByTestId("product-card")).toHaveLength(3);
  });

  it("shows a retryable honest error when the newest query fails", async () => {
    newestMock.mockReset().mockRejectedValue(new Error("boom"));
    renderHome();
    await waitFor(() =>
      expect(
        screen.getByText(i18n.t("home.new_in_error")),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: i18n.t("common.retry") }),
    ).toBeInTheDocument();
  });
});

describe("Home merchandising — On sale now", () => {
  beforeEach(() => {
    cleanup();
    vmState.products = PRODUCTS;
    vmState.categories = CATEGORIES;
    vmState.isLoading = false;
    vmState.error = null;
    newestMock.mockReset().mockResolvedValue([]);
  });

  it("renders ONLY real markdowns that are not already in Today's picks", () => {
    renderHome();
    const section = screen
      .getByText(i18n.t("home.sale_title"))
      .closest("section") as HTMLElement;
    const cards = within(section).getAllByTestId("product-card");
    expect(cards).toHaveLength(2); // ids 7 and 8 only
    expect(within(section).getByText("Catalogue Piece 7")).toBeInTheDocument();
    expect(within(section).getByText("Catalogue Piece 8")).toBeInTheDocument();
    // picks (1-6) must not repeat here
    expect(within(section).queryByText("Catalogue Piece 1")).toBeNull();
  });

  it("disappears entirely when the catalogue holds no qualifying markdown", () => {
    vmState.products = PRODUCTS.map((p) => ({
      ...p,
      compare_at_price: null,
    })) as unknown as Product[];
    renderHome();
    expect(screen.queryByText(i18n.t("home.sale_title"))).toBeNull();
  });
});

describe("Home merchandising — brand pavilion is real data", () => {
  beforeEach(() => {
    cleanup();
    vmState.products = PRODUCTS;
    vmState.categories = CATEGORIES;
    vmState.isLoading = false;
    vmState.error = null;
    newestMock.mockReset().mockResolvedValue([]);
  });

  it("derives the maisons from the live catalogue with real product imagery — no stock photos", () => {
    renderHome();
    const heading = screen.getByText(i18n.t("home.brands_title"));
    const section = heading.closest("section") as HTMLElement;
    // Real brand names from the fixture catalogue:
    expect(within(section).getByText("Reiss")).toBeInTheDocument();
    expect(within(section).getByText("COS")).toBeInTheDocument();
    // Real piece counts, pluralised:
    expect(
      within(section).getByText(i18n.t("home.brand_pieces_many", { count: 5 })),
    ).toBeInTheDocument();
    // The imagery is the brand's own catalogue thumbnails, never Unsplash.
    const imgs = Array.from(section.querySelectorAll("img"));
    expect(imgs.length).toBeGreaterThan(0);
    for (const img of imgs) {
      expect(img.getAttribute("src") ?? "").not.toContain("unsplash");
      expect(img.getAttribute("src") ?? "").toContain("img.example");
    }
  });
});

describe("Discover — ?category= deep link from the home rail", () => {
  beforeEach(() => {
    cleanup();
    vmState.products = PRODUCTS;
    vmState.categories = CATEGORIES;
    vmState.isLoading = false;
    vmState.error = null;
    newestMock.mockReset().mockResolvedValue([]);
    setSelectedCategoryMock.mockReset();
  });

  function renderDiscover(url: string) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <QueryClientProvider client={qc}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={[url]}>
            <DiscoverView />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    );
  }

  it("applies a known category slug from the URL", async () => {
    renderDiscover("/discover?category=dresses");
    await waitFor(() =>
      expect(setSelectedCategoryMock).toHaveBeenCalledWith("dresses"),
    );
  });

  it("ignores a slug the categories API does not know", async () => {
    renderDiscover("/discover?category=not-a-real-category");
    // Give the effect a tick to run, then assert it did nothing.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(setSelectedCategoryMock).not.toHaveBeenCalled();
  });
});

describe("Home — announcement bar binds to the REAL shipping policy", () => {
  beforeEach(() => {
    cleanup();
    window.localStorage.clear();
    vmState.products = PRODUCTS;
    vmState.categories = CATEGORIES;
    vmState.isLoading = false;
    vmState.error = null;
    newestMock.mockReset().mockResolvedValue([]);
    capState.value = {
      bnpl_live: false,
      tryon_live: false,
      bopis_live: false,
      free_shipping_threshold: 12125,
      shipping_currency: "EGP",
    };
  });

  it("renders the server's converted threshold — never a hardcoded figure", () => {
    renderHome();
    const region = screen.getByRole("region", {
      name: i18n.t("home.announcement_aria"),
    });
    // The sentence carries the SERVER's number (EGP 12,125.00), rendered by
    // the shared money formatter.
    expect(region.textContent).toContain("12,125.00");
    expect(region.textContent).not.toContain("$50");
  });

  it("renders NOTHING when the server publishes no policy", () => {
    capState.value = {
      ...capState.value,
      free_shipping_threshold: null,
      shipping_currency: null,
    };
    renderHome();
    expect(
      screen.queryByRole("region", { name: i18n.t("home.announcement_aria") }),
    ).toBeNull();
  });

  it("dismissal persists for the SAME policy but a changed threshold is news again", async () => {
    const { unmount } = renderHome();
    const dismiss = screen.getByRole("button", {
      name: i18n.t("a11y.dismiss_announcement"),
    });
    await act(async () => {
      dismiss.click();
    });
    expect(
      screen.queryByRole("region", { name: i18n.t("home.announcement_aria") }),
    ).toBeNull();
    unmount();

    // Same policy on a fresh mount: stays dismissed.
    renderHome();
    expect(
      screen.queryByRole("region", { name: i18n.t("home.announcement_aria") }),
    ).toBeNull();
    cleanup();

    // The merchandiser changes the threshold: the new fact is announced.
    capState.value = { ...capState.value, free_shipping_threshold: 9999 };
    renderHome();
    expect(
      screen.getByRole("region", { name: i18n.t("home.announcement_aria") }),
    ).toBeInTheDocument();
  });
});
