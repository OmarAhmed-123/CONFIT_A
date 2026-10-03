/**
 * Spec 01 finalisation — wardrobe garment actions as a REAL state machine.
 *
 * Pinned here (each was a live violation before this pass):
 *   · delete/favorite are ALWAYS visible controls (the old ones were
 *     opacity-0 until hover — unreachable on touch), 44px targets, real
 *     accessible names (not title tooltips), aria-busy while in flight;
 *   · one in-flight op per garment: double-click issues ONE request and
 *     a second op on the same card is swallowed until settlement;
 *   · retry-analysis keeps its translated pending label and never fakes
 *     success (the toast is the viewmodel's, asserted not called here);
 *   · favorite reflects state via aria-pressed (not colour alone);
 *   · every string that was hardcoded English now resolves from the
 *     catalogue in BOTH locales (worn count, badges, retry, CTA…);
 *   · axe-clean EN + AR/RTL.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "vitest-axe";

import i18n, { setAppLanguage } from "../../i18n/i18n";
import en from "../../i18n/en.json";
import ar from "../../i18n/ar.json";

/* ------------------------------------------------------------------ */
/* Deferred-promise viewmodel fake                                     */
/* ------------------------------------------------------------------ */
const deleteItem = vi.fn<() => Promise<void>>();
const toggleFavorite = vi.fn<() => Promise<void>>();
const retryAnalysis = vi.fn<() => Promise<void>>();
const fetchOutfitSuggestion = vi.fn<() => Promise<void>>();

const baseItem = {
  id: 7,
  title: "Silk Shirt",
  category: "Tops",
  color_name: "Ivory",
  image_url: "https://example.com/i.jpg",
  is_favorite: false,
  wear_count: 3,
  wear_frequency: "regular",
  processing_status: "ready",
  ai_tags: [],
};

let vmOverrides: Record<string, unknown> = {};
vi.mock("../../viewmodels/useWardrobeViewModel", () => ({
  useWardrobeViewModel: () => ({
    items: [baseItem, { ...baseItem, id: 8, title: "Worn Denim", processing_status: "failed" }],
    activeCategory: "All",
    setActiveCategory: vi.fn(),
    isLoading: false,
    isClosetError: false,
    fetchWardrobe: vi.fn(),
    gapAnalyses: [],
    isGapLoading: false,
    isGapError: false,
    hasLoadedGaps: false,
    fetchGaps: vi.fn(),
    moodBoards: [],
    isBoardsLoading: false,
    isBoardsError: false,
    hasLoadedBoards: false,
    fetchMoodBoards: vi.fn(),
    createMoodBoard: vi.fn(),
    renameMoodBoard: vi.fn(),
    deleteMoodBoard: vi.fn(),
    addMoodBoardTile: vi.fn(),
    removeMoodBoardTile: vi.fn(),
    uploadMoodBoardTile: vi.fn(),
    isAutoTagging: false,
    autoTagResult: null,
    autoTagUpload: vi.fn(),
    addNewItem: vi.fn(),
    deleteItem,
    uploadFiles: vi.fn(),
    isUploading: false,
    uploadReport: null,
    retryAnalysis,
    retryingItemId: null,
    toggleFavorite,
    setWearFrequency: vi.fn(),
    outfitSuggestion: null,
    isOutfitLoading: false,
    fetchOutfitSuggestion,
    ...vmOverrides,
  }),
}));
vi.mock("../../stores/authStore", () => ({
  useAuthStore: () => ({ isAuthenticated: true, user: { id: 1 } }),
}));
const showToast = vi.fn();
vi.mock("../../stores/uiStore", () => ({
  useUIStore: () => ({ showToast }),
}));
vi.mock("../../hooks/useCapabilities", () => ({
  useCapabilities: () => ({
    capabilities: { photo_upload_available: true, tryon_available: true },
    isLoading: false,
  }),
}));
vi.mock("../../privacy/usePhotoConsent", () => ({
  usePhotoConsent: () => ({ consent: "granted", grant: vi.fn(), revoke: vi.fn() }),
}));
// Showcase carousels have their own suites; stub to keep this one focused.
vi.mock("../../components/showcase/DesignShowcases", () => ({
  CardStackShowcase: () => null,
  CircularGalleryShowcase: () => null,
}));
vi.mock("../../services/apiServices", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/apiServices")>();
  return {
    ...actual,
    stylistService: { ...actual.stylistService, getSavedLooks: vi.fn(async () => []) },
  };
});

import { WardrobeView } from "../consumer/WardrobeView";

const ui = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/wardrobe"]}>
          <WardrobeView />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
};

const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { (resolve = res), (reject = rej); });
  return { promise, resolve, reject };
};

beforeEach(() => {
  vi.clearAllMocks();
  vmOverrides = {};
});
afterEach(async () => {
  cleanup();
  await setAppLanguage("en");
});

describe("delete — visible, named, pending, single-flight", () => {
  it("is ALWAYS visible (no hover-only opacity) with a 44px target and a real name", () => {
    ui();
    const dels = screen.getAllByRole("button", { name: en.wardrobe.delete_aria });
    expect(dels.length).toBeGreaterThan(0);
    for (const d of dels) {
      expect(d.className).not.toContain("opacity-0");
      expect(d.className).toContain("w-11");
      expect(d.className).toContain("h-11");
      expect(d).not.toHaveAttribute("title"); // name is aria-label, not tooltip
    }
  });

  it("pending: aria-busy spinner; double-click sends exactly ONE request", async () => {
    const d = deferred<void>();
    deleteItem.mockReturnValue(d.promise);
    ui();
    const del = screen.getAllByRole("button", { name: en.wardrobe.delete_aria })[0];
    fireEvent.click(del);
    fireEvent.click(del);
    expect(deleteItem).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(del).toHaveAttribute("aria-busy", "true"));
    d.resolve();
    await waitFor(() => expect(del).toHaveAttribute("aria-busy", "false"));
  });

  it("while a delete is in flight, favorite on the SAME card is swallowed too", async () => {
    const d = deferred<void>();
    deleteItem.mockReturnValue(d.promise);
    ui();
    fireEvent.click(screen.getAllByRole("button", { name: en.wardrobe.delete_aria })[0]);
    fireEvent.click(screen.getAllByRole("button", { name: en.wardrobe.fav_mark })[0]);
    expect(toggleFavorite).not.toHaveBeenCalled();
    d.resolve();
  });
});

describe("favorite — aria-pressed state, pending, honest failure", () => {
  it("exposes the toggle state via aria-pressed, not colour alone", () => {
    ui();
    const fav = screen.getAllByRole("button", { name: en.wardrobe.fav_mark })[0];
    expect(fav).toHaveAttribute("aria-pressed", "false");
  });

  it("a rejected toggle settles back without any success claim", async () => {
    toggleFavorite.mockRejectedValue(new Error("500"));
    ui();
    const fav = screen.getAllByRole("button", { name: en.wardrobe.fav_mark })[0];
    fireEvent.click(fav);
    await waitFor(() => expect(fav).toHaveAttribute("aria-busy", "false"));
    // The UI layer claims nothing; error surfacing belongs to the viewmodel.
    expect(showToast).not.toHaveBeenCalledWith(expect.anything(), "success");
  });
});

describe("retry analysis — translated, pending-aware, retryable", () => {
  it("failed items show the translated retry CTA and fire exactly once", async () => {
    retryAnalysis.mockResolvedValue(undefined);
    ui();
    const retry = screen.getByRole("button", { name: en.wardrobe.retry_analysis });
    fireEvent.click(retry);
    expect(retryAnalysis).toHaveBeenCalledTimes(1);
    expect(retryAnalysis).toHaveBeenCalledWith(8);
  });

  it("while retrying (viewmodel state) the button is busy with the pending label", () => {
    vmOverrides = { retryingItemId: 8 };
    ui();
    const retry = screen.getByRole("button", { name: new RegExp(en.wardrobe.retrying) });
    expect(retry).toHaveAttribute("aria-busy", "true");
    expect(retry).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(retry);
    expect(retryAnalysis).not.toHaveBeenCalled(); // guarded while in flight
  });
});

describe("the Arabic page is Arabic", () => {
  it("renders the previously-hardcoded strings from ar.json", async () => {
    await setAppLanguage("ar");
    ui();
    expect(screen.getAllByRole("button", { name: ar.wardrobe.delete_aria }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: ar.wardrobe.fav_mark }).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: ar.wardrobe.retry_analysis })).toBeInTheDocument();
    // Worn-count badge comes from the catalogue, with the count interpolated.
    expect(screen.getAllByText(ar.wardrobe.worn_count.replace("{{count}}", "3")).length).toBeGreaterThan(0);
    for (const key of ["delete_aria", "fav_mark", "retry_analysis", "worn_count"] as const) {
      expect(ar.wardrobe[key]).not.toBe(en.wardrobe[key]);
      expect(ar.wardrobe[key]).toMatch(/[\u0600-\u06FF]/);
    }
  });
});

describe("accessibility", () => {
  it("axe: closet grid has no violations in EN or AR", async () => {
    const { container, unmount } = ui();
    expect((await axe(container)).violations).toEqual([]);
    unmount();
    await setAppLanguage("ar");
    const { container: arC } = ui();
    expect((await axe(arC)).violations).toEqual([]);
  });
});
