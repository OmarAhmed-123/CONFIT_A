/**
 * C04 — the Outfit Builder's behavioral contract (/builder, /outfits/:id).
 *
 * First direct test suite this view has ever had. Pins the defects found by
 * the 2026-10-08 redesign pass so none of them can return:
 *
 *  1. MONEY HONESTY: every total used a hard-coded "$" while the catalog
 *     prices carry their own currency (EGP in production). Totals now format
 *     through formatMoney in the currency of the pieces themselves.
 *  2. ARABIC TRUTH: ~20 raw English strings (summary header, bag CTA,
 *     loading state, slot hints, verdict titles, formula buttons, default
 *     look name/occasion) rendered verbatim inside the Arabic UI.
 *  3. UNDOABLE REMOVE: clearing a slot must offer a working local Undo —
 *     and the restore must actually bring the piece back.
 *  4. NO FAKE SUCCESS: the save CTA may claim success only after the server
 *     resolves; applying a starter formula over an empty catalog must report
 *     failure, not success.
 *  5. SELECT TRUTH: a hydrated occasion outside the current locale's options
 *     must be preserved as a real <option>, never silently displayed as the
 *     first option while the state holds something else.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  render,
  cleanup,
  screen,
  fireEvent,
  act,
  waitFor,
  within,
} from "@testing-library/react";
import { axe } from "vitest-axe";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import i18n, { setAppLanguage } from "../../i18n/i18n";
import { formatMoney } from "../../i18n/format";
import type { Product } from "../../models";

/* ------------------------------------------------------------------ mocks */

const {
  getProductsMock,
  getProductByIdMock,
  getProductDetailMock,
  getOutfitMock,
  saveOutfitMock,
  replaceOutfitItemsMock,
  updateOutfitMock,
  previewCompositionMock,
  checkCompatibilityMock,
  showToastMock,
  addItemMock,
  openCartMock,
  getProfileMock,
  getShareStateMock,
  shareOutfitMock,
  fillInTheBlankMock,
} = vi.hoisted(() => ({
  getProductsMock: vi.fn(),
  getProductByIdMock: vi.fn(),
  getProductDetailMock: vi.fn(),
  getOutfitMock: vi.fn(),
  saveOutfitMock: vi.fn(),
  replaceOutfitItemsMock: vi.fn(),
  updateOutfitMock: vi.fn(),
  previewCompositionMock: vi.fn(),
  checkCompatibilityMock: vi.fn(),
  showToastMock: vi.fn(),
  addItemMock: vi.fn(),
  openCartMock: vi.fn(),
  getProfileMock: vi.fn(),
  getShareStateMock: vi.fn(),
  shareOutfitMock: vi.fn(),
  fillInTheBlankMock: vi.fn(),
}));

vi.mock("../../services/apiServices", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../services/apiServices")>();
  return {
    ...actual,
    catalogService: {
      ...actual.catalogService,
      getProducts: getProductsMock,
      getProductById: getProductByIdMock,
      getProductDetail: getProductDetailMock,
      getCategories: vi.fn().mockResolvedValue([]),
      getOccasions: vi.fn().mockResolvedValue([]),
    },
    stylistService: {
      ...actual.stylistService,
      getOutfit: getOutfitMock,
      saveOutfit: saveOutfitMock,
      replaceOutfitItems: replaceOutfitItemsMock,
      updateOutfit: updateOutfitMock,
      previewComposition: previewCompositionMock,
      checkCompatibility: checkCompatibilityMock,
      getShareState: getShareStateMock,
      shareOutfit: shareOutfitMock,
      fillInTheBlank: fillInTheBlankMock,
    },
    profileService: {
      ...actual.profileService,
      getProfile: getProfileMock,
      getUSP: getProfileMock,
    },
  };
});

vi.mock("../../stores/uiStore", () => ({
  useUIStore: () => ({
    showToast: showToastMock,
    openTryOn: vi.fn(),
    openRuler: vi.fn(),
  }),
}));

vi.mock("../../stores/cartStore", () => ({
  useCartStore: () => ({
    addItem: addItemMock,
    openCart: openCartMock,
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
      ctaKind: () => "fit_check" as const,
      gate: ({ fitCheck }: { fitCheck: () => void }) => fitCheck,
    }),
  };
});

import { OutfitBuilderView } from "../consumer/OutfitBuilderView";
import { useAuthStore } from "../../stores/authStore";

/* --------------------------------------------------------------- fixtures */

const sku = (id: number, size = "M") => ({
  id,
  size,
  color: "Navy",
  price_override: null,
  stock_level: 5,
  is_in_stock: true,
});

const product = (
  id: number,
  overrides: Partial<Product> & { category_name?: string } = {},
): Product =>
  ({
    id,
    slug: `piece-${id}`,
    title: `Piece ${id}`,
    brand_name: "Atelier",
    thumbnail_url: `https://img.example/p${id}.jpg`,
    base_price: 120,
    currency: "EGP",
    category_name: "Tops",
    color_family: "Navy",
    skus: [sku(id * 10)],
    ...overrides,
  }) as unknown as Product;

const CATALOG: Product[] = [
  product(1, { category_name: "Outerwear & Blazers", title: "Navy Blazer" }),
  product(2, { category_name: "Tops", title: "Silk Shirt" }),
  product(3, { category_name: "Trousers", title: "Wool Trousers", base_price: 210 }),
  product(4, { category_name: "Shoes", title: "Leather Loafers" }),
  product(5, { category_name: "Accessories", title: "Gold Watch" }),
];

const VALID_VERDICT = { is_valid: true, violations: [], warnings: [] };
const COMPAT = {
  compatibility_score: 82,
  color_harmony_type: "Analogous",
  color_harmony_verdict: "Harmonious palette.",
  aesthetic_consistency_verdict: "Cohesive silhouette.",
};

function renderBuilder(route = "/builder") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path="/builder" element={<OutfitBuilderView />} />
            <Route path="/outfits/:id" element={<OutfitBuilderView />} />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

const en = i18n.getFixedT("en");
const ar = i18n.getFixedT("ar");

beforeEach(() => {
  vi.clearAllMocks();
  getProductsMock.mockResolvedValue(CATALOG);
  getProductDetailMock.mockResolvedValue(CATALOG[0]);
  previewCompositionMock.mockResolvedValue(VALID_VERDICT);
  checkCompatibilityMock.mockResolvedValue(COMPAT);
  saveOutfitMock.mockResolvedValue({ id: 99 });
  getShareStateMock.mockResolvedValue({
    outfit_id: 7, share_token: null, share_url: null,
    expires_at: null, is_active: false, view_count: 0,
  });
  addItemMock.mockResolvedValue({ merged: false, quantity: 1 });
});

afterEach(async () => {
  cleanup();
  act(() => {
    useAuthStore.setState({ isAuthenticated: false, user: null });
  });
  await act(async () => {
    await setAppLanguage("en");
  });
});

const addByName = async (title: string) => {
  const btn = await screen.findByRole("button", {
    name: en("outfit_builder.add_to_outfit", { name: title }),
  });
  await act(async () => {
    fireEvent.click(btn);
  });
};

/* ------------------------------------------------------------------ tests */

describe("OutfitBuilderView — behavioral contract (C04)", () => {
  it("GOAL compose: clicking a catalog piece fills its natural slot and the running total shows the catalog currency, never a hard-coded $", async () => {
    renderBuilder();
    await addByName("Navy Blazer");
    await addByName("Wool Trousers");

    expect(within(screen.getByTestId("slot-outerwear")).getByText("Navy Blazer")).toBeTruthy();
    expect(within(screen.getByTestId("slot-bottom")).getByText("Wool Trousers")).toBeTruthy();

    const total = screen.getByTestId("builder-running-total");
    expect(total.textContent).toBe(formatMoney(33000, "EGP", "en"));
    expect(total.textContent).not.toContain("$");
    // The bag CTA quotes the same honest figure.
    expect(
      screen.getByTestId("builder-add-all").textContent,
    ).toContain(formatMoney(33000, "EGP", "en"));
  });

  it("GOAL compose (dev-fluff removed): the builder never renders the showcase demo block", async () => {
    renderBuilder();
    await screen.findByRole("heading", { name: en("outfit_builder.title") });
    expect(screen.queryByText(/Inspiration Stack/i)).toBeNull();
    expect(screen.queryByText(/premium starting point/i)).toBeNull();
  });

  it("GOAL undoable remove: clearing a slot offers Undo and the restore really brings the piece back", async () => {
    renderBuilder();
    await addByName("Silk Shirt");
    expect(within(screen.getByTestId("slot-top")).getByText("Silk Shirt")).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", {
        name: en("outfit_builder.remove_item_aria", {
          item: "Silk Shirt",
          slot: en("outfit_builder.slot_top"),
        }),
      }),
    );
    expect(within(screen.getByTestId("slot-top")).queryByText("Silk Shirt")).toBeNull();

    const undoCall = showToastMock.mock.calls.find(
      (c) => c[2]?.i18nLabel === "a11y.undo_remove",
    );
    expect(undoCall, "removal must offer an a11y.undo_remove action").toBeTruthy();
    await act(async () => {
      undoCall![2].onAction();
    });
    expect(within(screen.getByTestId("slot-top")).getByText("Silk Shirt")).toBeTruthy();
  });

  it("COUNTER-GOAL no fake success: the save CTA shows pending until the server resolves, then success — and sends the real SKU ids", async () => {
    act(() => {
      useAuthStore.setState({ isAuthenticated: true } as any);
    });
    let resolveSave!: (v: unknown) => void;
    saveOutfitMock.mockImplementation(
      () => new Promise((res) => (resolveSave = res)),
    );
    renderBuilder();
    await addByName("Navy Blazer");
    await waitFor(() => expect(previewCompositionMock).toHaveBeenCalled());

    const cta = screen.getByTestId("save-look-cta");
    await act(async () => {
      fireEvent.click(cta);
    });
    // ActionButton stacks every label for stable sizing; the STATE is the
    // honest signal (aria-busy while in flight, success only after resolve).
    await waitFor(() => expect(cta.getAttribute("aria-busy")).toBe("true"));
    expect(cta.getAttribute("data-state")).toBe("pending");

    await act(async () => {
      resolveSave({ id: 7 });
    });
    await waitFor(() => expect(cta.getAttribute("data-state")).toBe("success"));
    expect(cta.getAttribute("aria-busy")).toBe("false");
    expect(saveOutfitMock).toHaveBeenCalledWith(
      expect.objectContaining({ product_sku_ids: [10] }),
    );
  });

  it("COUNTER-GOAL formula honesty: applying a starter formula over an empty catalog reports failure, not success", async () => {
    getProductsMock.mockResolvedValue([]);
    renderBuilder();
    await screen.findByText(en("outfit_builder.palette_empty"));

    fireEvent.click(
      screen.getByRole("button", {
        name: en("outfit_builder.use_formula", {
          name: en("outfit_builder.formula_tailored"),
        }),
      }),
    );
    expect(showToastMock).toHaveBeenCalledWith(
      en("outfit_builder.formula_nothing_added"),
      "error",
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      en("outfit_builder.formula_added"),
      "success",
    );
  });

  it("GOAL guided start: a formula fills the slots from the catalog and announces success", async () => {
    renderBuilder();
    await screen.findByText("Navy Blazer");
    fireEvent.click(
      screen.getByRole("button", {
        name: en("outfit_builder.use_formula", {
          name: en("outfit_builder.formula_evening"),
        }),
      }),
    );
    await waitFor(() =>
      expect(showToastMock).toHaveBeenCalledWith(
        en("outfit_builder.formula_added"),
        "success",
      ),
    );
    expect(within(screen.getByTestId("slot-footwear")).getByText("Leather Loafers")).toBeTruthy();
    // The look name follows the formula — in the app language, keyed.
    expect(
      screen.getByRole("textbox", { name: en("outfit_builder.name_label") }),
    ).toHaveProperty(
      "value",
      en("outfit_builder.formula_title", {
        name: en("outfit_builder.formula_evening"),
      }),
    );
  });

  it("GOAL budget honesty: over-budget state flips the badge and the progressbar reports real values", async () => {
    renderBuilder();
    await addByName("Navy Blazer"); // 120
    await addByName("Silk Shirt"); // 120
    await addByName("Wool Trousers"); // 210 → 450 total (not over)
    expect(screen.getByText(en("outfit_builder.under_budget"))).toBeTruthy();
    await addByName("Leather Loafers"); // 570 → over
    expect(screen.getByText(en("outfit_builder.over_budget"))).toBeTruthy();

    const bar = screen.getByRole("progressbar", {
      name: en("outfit_builder.budget_status"),
    });
    expect(bar.getAttribute("aria-valuemax")).toBe("450");
    expect(bar.getAttribute("aria-valuenow")).toBe("450"); // capped at max
    expect(bar.getAttribute("aria-valuetext")).toBe(formatMoney(57000, "EGP", "en"));
  });

  it("GOAL remaining allocation: within budget the tracker shows the real residual in catalog money; over budget the line disappears (the badge owns that case)", async () => {
    renderBuilder();
    await addByName("Navy Blazer"); // 120 of 450 → 330 remaining
    const remaining = await screen.findByTestId("builder-budget-remaining");
    expect(remaining.textContent).toBe(formatMoney(33000, "EGP", "en"));
    await addByName("Silk Shirt"); // 240 → 210 remaining
    expect(screen.getByTestId("builder-budget-remaining").textContent).toBe(
      formatMoney(21000, "EGP", "en"),
    );
    await addByName("Wool Trousers"); // 450 (at limit, not over)
    await addByName("Leather Loafers"); // 570 → over: no fake "remaining"
    expect(screen.queryByTestId("builder-budget-remaining")).toBeNull();
  });

  it("GOAL real outfit budget: a signed-in user's budget_per_outfit_max drives the tracker instead of the hard-coded 450", async () => {
    act(() => {
      useAuthStore.setState({
        isAuthenticated: true,
        user: { id: 1, email: "x@y.z", has_profile: true } as never,
      });
    });
    getProfileMock.mockResolvedValue({
      onboarding_completed: true,
      budget_per_outfit_max: 20000,
    });
    renderBuilder();
    // The allocated-budget row shows the PROFILE figure in catalog currency.
    // textContent comparison: Intl money strings contain NBSP, which the
    // testing-library text normalizer would silently rewrite.
    await waitFor(() =>
      expect(screen.getByTestId("builder-budget-limit").textContent).toBe(
        formatMoney(2000000, "EGP", "en"),
      ),
    );
    await addByName("Navy Blazer"); // 120 — far below 20,000: honest 'under'
    expect(screen.getByText(en("outfit_builder.under_budget"))).toBeTruthy();
    const bar = screen.getByRole("progressbar", {
      name: en("outfit_builder.budget_status"),
    });
    expect(bar.getAttribute("aria-valuemax")).toBe("20000");
  });

  it("COUNTER-GOAL add-to-bag gating: a piece still resolving its size blocks the batch — no partial silent cart writes", async () => {
    // A product without inline SKUs enters 'pending' while the detail fetch
    // (never resolving here) looks for a real SKU.
    getProductDetailMock.mockImplementation(() => new Promise(() => {}));
    const noSku = product(6, { category_name: "Tops", title: "Linen Tee", skus: [] });
    getProductsMock.mockResolvedValue([...CATALOG, noSku]);
    renderBuilder();
    await addByName("Linen Tee");
    expect(
      within(screen.getByTestId("slot-top")).getByText(en("outfit_builder.checking_size")),
    ).toBeTruthy();

    fireEvent.click(screen.getByTestId("builder-add-all"));
    await waitFor(() =>
      expect(showToastMock).toHaveBeenCalledWith(
        expect.objectContaining({ key: "toast.confirming_sizes" }),
        "error",
      ),
    );
    expect(addItemMock).not.toHaveBeenCalled();
  });

  it("GOAL add-to-bag: ready pieces are added one by one, the drawer opens, and the toast is keyed (no raw English)", async () => {
    renderBuilder();
    await addByName("Navy Blazer");
    await addByName("Gold Watch");
    await act(async () => {
      fireEvent.click(screen.getByTestId("builder-add-all"));
    });
    await waitFor(() => expect(addItemMock).toHaveBeenCalledTimes(2));
    expect(openCartMock).toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      expect.objectContaining({
        key: "toast.builder_added_to_bag",
        params: { count: 2 },
      }),
      "success",
    );
  });

  it("COUNTER-GOAL no double submit: double-clicking add-to-bag issues each piece exactly once", async () => {
    let resolvers: Array<(v: unknown) => void> = [];
    addItemMock.mockImplementation(
      () => new Promise((res) => resolvers.push(res)),
    );
    renderBuilder();
    await addByName("Navy Blazer");
    await addByName("Gold Watch");

    const addAll = screen.getByTestId("builder-add-all") as HTMLButtonElement;
    await act(async () => {
      fireEvent.click(addAll);
      fireEvent.click(addAll); // second click while the first is in flight
    });
    expect(addAll.getAttribute("aria-busy")).toBe("true");
    expect(addAll.disabled).toBe(true);

    await act(async () => {
      resolvers.forEach((r) => r({ merged: false, quantity: 1 }));
      // drain the sequential loop (second addItem starts after the first)
      await Promise.resolve();
      resolvers.forEach((r) => r({ merged: false, quantity: 1 }));
    });
    await waitFor(() => expect(openCartMock).toHaveBeenCalledTimes(1));
    expect(addItemMock).toHaveBeenCalledTimes(2); // two pieces, once each
    await waitFor(() => expect(addAll.getAttribute("aria-busy")).toBe("false"));
  });

  it("GOAL compatibility suggestions: a signed-in shopper asks an empty slot for ideas — the server's ranked REAL pieces appear and one click composes it", async () => {
    act(() => {
      useAuthStore.setState({ isAuthenticated: true } as any);
    });
    fillInTheBlankMock.mockResolvedValue({
      fitb_available: true, engine: "rules_heuristic", reason: null,
      target_slot: null, target_category_used: null, outfit_product_ids: [1],
      ranked: [
        { product_id: 4, rank: 1, similarity: 0.91, title: "Leather Loafers", image_url: null, price: 120, currency: "EGP" },
        { product_id: 2, rank: 2, similarity: 0.80, title: "Silk Shirt", image_url: null, price: 120, currency: "EGP" },
      ],
      method_note: null,
    });
    renderBuilder();
    await addByName("Navy Blazer");
    const suggestBtn = await screen.findByRole("button", {
      name: en("outfit_builder.suggest_for_slot", { slot: en("outfit_builder.slot_footwear") }),
    });
    await act(async () => {
      fireEvent.click(suggestBtn);
    });
    const rail = await screen.findByTestId("builder-suggestions");
    // honest engine label: rules fallback is never presented as the model
    expect(within(rail).getByText(en("outfit_builder.suggestions_engine_rules"))).toBeTruthy();
    // only slot-valid pieces offered: the Silk Shirt (top) is filtered out of a footwear rail
    expect(within(rail).queryByText("Silk Shirt")).toBeNull();
    const addSug = within(rail).getByRole("button", {
      name: en("outfit_builder.add_suggestion", { name: "Leather Loafers" }),
    });
    await act(async () => {
      fireEvent.click(addSug);
    });
    expect(
      within(screen.getByTestId("slot-footwear")).getByText("Leather Loafers"),
    ).toBeTruthy();
    expect(fillInTheBlankMock).toHaveBeenCalledWith({ product_ids: [1], top_k: 10 });
  });

  it("COUNTER-GOAL suggestion honesty: when the server declares fitb unavailable, the rail says so with the real reason — no fabricated taste", async () => {
    act(() => {
      useAuthStore.setState({ isAuthenticated: true } as any);
    });
    fillInTheBlankMock.mockResolvedValue({
      fitb_available: false, engine: null, reason: "complementary model offline",
      target_slot: null, target_category_used: null, outfit_product_ids: [1],
      ranked: [], method_note: null,
    });
    renderBuilder();
    await addByName("Navy Blazer");
    fireEvent.click(await screen.findByRole("button", {
      name: en("outfit_builder.suggest_for_slot", { slot: en("outfit_builder.slot_footwear") }),
    }));
    const rail = await screen.findByTestId("builder-suggestions");
    await within(rail).findByText(en("outfit_builder.suggestions_unavailable"));
    expect(within(rail).getByText("complementary model offline")).toBeTruthy();
    expect(within(rail).queryByRole("button", { name: /Add suggestion/ })).toBeNull();
  });

  it("COUNTER-GOAL guest suggestions: a guest never sees the suggest affordance (the endpoint requires an account)", async () => {
    renderBuilder();
    await addByName("Navy Blazer");
    expect(
      screen.queryByRole("button", {
        name: en("outfit_builder.suggest_for_slot", { slot: en("outfit_builder.slot_footwear") }),
      }),
    ).toBeNull();
    expect(fillInTheBlankMock).not.toHaveBeenCalled();
  });

  it("GUEST honesty: composing as a guest fires NO verdict/compatibility calls (no 401 -> login modal) and the cohesion card says sign-in is needed", async () => {
    renderBuilder();
    await addByName("Navy Blazer");
    await screen.findByRole("button", {
      name: en("outfit_builder.remove_item_aria", { item: "Navy Blazer", slot: en("outfit_builder.slot_outerwear") }),
    });
    // The defect observed on production: these background calls returned 401
    // for guests and the global session-expired handler opened the login
    // modal mid-composition. The contract is now: guests never trigger them.
    expect(previewCompositionMock).not.toHaveBeenCalled();
    expect(checkCompatibilityMock).not.toHaveBeenCalled();
    expect(
      screen.getAllByText(en("outfit_builder.sign_in_to_evaluate")).length,
    ).toBeGreaterThan(0);
  });

  it("BLOCKED verdict: an invalid composition shows the translated alert title and disables save", async () => {
    act(() => {
      useAuthStore.setState({ isAuthenticated: true } as any);
    });
    previewCompositionMock.mockResolvedValue({
      is_valid: false,
      violations: [{ code: "DUP_SLOT", positions: [1], message: "Two footwear pieces." }],
      warnings: [],
    });
    renderBuilder();
    await addByName("Navy Blazer");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(en("outfit_builder.verdict_blocked_title"));
    expect(alert.textContent).toContain("Two footwear pieces.");
    await waitFor(() =>
      expect(
        (screen.getByTestId("save-look-cta") as HTMLButtonElement).disabled,
      ).toBe(true),
    );
  });

  it("GOAL share a saved look: edit mode offers the Spec-06 surface — mint only reports success AFTER the server returns a live link, which is then shown verbatim", async () => {
    act(() => {
      useAuthStore.setState({ isAuthenticated: true } as any);
    });
    getOutfitMock.mockResolvedValue({
      id: 7,
      title: "Client Dinner",
      occasion: "Smart Casual Work",
      items: [{ product_id: 1, sku_id: 10, position: "outerwear" }],
    });
    getProductByIdMock.mockResolvedValue(CATALOG[0]);
    let resolveMint!: (v: unknown) => void;
    shareOutfitMock.mockImplementation(() => new Promise((res) => (resolveMint = res)));

    renderBuilder("/outfits/7");
    const card = await screen.findByTestId("builder-share-card");
    // not live yet → honest private note + publish CTA, no URL shown
    expect(within(card).getByText(en("my_looks.private_note"))).toBeTruthy();
    const cta = within(card).getByTestId("builder-publish-link");
    await act(async () => {
      fireEvent.click(cta);
    });
    await waitFor(() => expect(cta.getAttribute("aria-busy")).toBe("true"));
    expect(within(card).queryByDisplayValue(/\/shared\//)).toBeNull(); // no fake link mid-flight
    await act(async () => {
      resolveMint({
        outfit_id: 7, share_token: "tok_abc123", share_url: "/shared/tok_abc123",
        expires_at: "2027-01-01T00:00:00Z", is_active: true, view_count: 0,
      });
    });
    const url = await within(card).findByDisplayValue(
      `${window.location.origin}/shared/tok_abc123`,
    );
    expect(url).toBeTruthy();
    expect(shareOutfitMock).toHaveBeenCalledWith(7);
  });

  it("COUNTER-GOAL currency honesty under outage: with no catalog and an empty canvas the tracker shows an em-dash, never a fabricated $", async () => {
    getProductsMock.mockRejectedValue(new Error("network down"));
    renderBuilder();
    await screen.findByText(en("outfit_builder.palette_error"));
    const total = screen.getByTestId("builder-running-total");
    const budget = screen.getByTestId("builder-budget-limit");
    expect(total.textContent).toBe("—");
    expect(budget.textContent).toBe("—");
    expect(total.textContent).not.toContain("$");
    expect(screen.getByTestId("builder-add-all").textContent).not.toContain("$");
  });

  it("COUNTER-GOAL palette honesty: a catalog outage shows a calm translated error with a REAL retry — never the 'empty catalog' lie", async () => {
    getProductsMock.mockRejectedValue(new Error("network down"));
    renderBuilder();
    const alertEl = await screen.findByText(en("outfit_builder.palette_error"));
    expect(alertEl).toBeTruthy();
    expect(screen.queryByText(en("outfit_builder.palette_empty"))).toBeNull();
    getProductsMock.mockResolvedValue(CATALOG);
    const retryBtn = screen.getByRole("button", { name: en("common.retry") });
    await act(async () => {
      fireEvent.click(retryBtn);
    });
    // recovery is real: the palette renders the catalog pieces
    await screen.findByRole("button", {
      name: en("outfit_builder.add_to_outfit", { name: "Navy Blazer" }),
    });
  });

  it("EDIT loading: while the saved look loads, a geometry-matched skeleton with a translated status replaces the bare English sentence", async () => {
    getOutfitMock.mockImplementation(() => new Promise(() => {}));
    renderBuilder("/outfits/7");
    const status = screen.getByRole("status", {
      name: en("outfit_builder.loading_look"),
    });
    expect(status).toBeTruthy();
    expect(screen.getByTestId("builder-skeleton")).toBeTruthy();
    expect(screen.queryByText("Loading this look…")).toBeTruthy(); // sr-only EN copy via key
  });

  it("EDIT hydrate: a saved occasion outside the current locale's options is preserved as a real <option> — the select never lies", async () => {
    getOutfitMock.mockResolvedValue({
      id: 7,
      title: "Client Dinner",
      occasion: "Boardroom & Business",
      items: [{ product_id: 1, sku_id: 10, position: "outerwear" }],
    });
    getProductByIdMock.mockResolvedValue(CATALOG[0]);
    await act(async () => {
      await setAppLanguage("ar");
    });
    renderBuilder("/outfits/7");

    const select = (await screen.findByRole("combobox", {
      name: ar("outfit_builder.target_occasion"),
    })) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe("Boardroom & Business"));
    const legacy = within(select).getByRole("option", {
      name: "Boardroom & Business",
    }) as HTMLOptionElement;
    expect(legacy.selected).toBe(true);
    expect(
      screen.getByRole("textbox", { name: ar("outfit_builder.name_label") }),
    ).toHaveProperty("value", "Client Dinner");
  });

  it("EDIT 404: an unknown look shows the translated not-found message with a working way back", async () => {
    getOutfitMock.mockRejectedValue({ status: 404 });
    renderBuilder("/outfits/9999");
    await screen.findByText(en("outfit_builder.look_not_found"));
    const back = screen.getByRole("link", {
      name: en("outfit_builder.back_to_my_looks"),
    });
    expect(back.getAttribute("href")).toBe("/my-looks");
  });

  it("ARABIC truth: the Arabic page carries no hard-coded English surfaces and opens with an Arabic look name and occasion", async () => {
    await act(async () => {
      await setAppLanguage("ar");
    });
    renderBuilder();
    await screen.findByText(ar("outfit_builder.look_summary"));

    for (const leak of [
      "Sticky Look Summary",
      "Add Complete Look to Bag",
      "Profile Target Allocation",
      "Drop a piece here",
      "Use Tailored Power",
      "Avoid the blank-canvas problem",
      "Drag Pieces from the Multi-Brand Catalog",
      "Awaiting items",
      "My Custom Tailored Ensemble",
    ]) {
      expect(screen.queryByText(new RegExp(leak, "i")), leak).toBeNull();
    }

    // Defaults initialise in the mount language, and the select holds a
    // value that IS one of its options.
    expect(
      screen.getByRole("textbox", { name: ar("outfit_builder.name_label") }),
    ).toHaveProperty("value", ar("outfit_builder.default_look_name"));
    const select = screen.getByRole("combobox", {
      name: ar("outfit_builder.target_occasion"),
    }) as HTMLSelectElement;
    expect(select.value).toBe(ar("outfit_builder.occasion_smart_casual"));

    // Money renders through formatMoney, never "$x.xx". The add control's
    // accessible name is Arabic here — the page IS in Arabic.
    const btn = await screen.findByRole("button", {
      name: ar("outfit_builder.add_to_outfit", { name: "Navy Blazer" }),
    });
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(
      screen.getByTestId("builder-running-total").textContent,
    ).toBe(formatMoney(12000, "EGP", "ar"));
  });

  it("TOUCH TARGETS: slot removal and try-on overlays reserve a ≥44px hit area", async () => {
    renderBuilder();
    await addByName("Silk Shirt");
    const remove = screen.getByRole("button", {
      name: en("outfit_builder.remove_item_aria", {
        item: "Silk Shirt",
        slot: en("outfit_builder.slot_top"),
      }),
    });
    expect(remove.className).toContain("h-11");
    expect(remove.className).toContain("w-11");
    const tryOnButtons = screen.getAllByRole("button", {
      name: en("tryon.cta_fit_check"),
    });
    expect(tryOnButtons.length).toBeGreaterThan(0);
    for (const b of tryOnButtons) {
      expect(b.className).toContain("h-11");
      expect(b.className).toContain("w-11");
    }
  });

  it("A11Y: the composed builder page has no serious/critical axe violations", async () => {
    const { container } = renderBuilder();
    await screen.findByText("Navy Blazer");
    const results = await axe(container, {
      rules: {
        "color-contrast": { enabled: false },
        "target-size": { enabled: false },
      },
    });
    const serious = results.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact ?? ""),
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });
});
