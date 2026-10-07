/**
 * C01 goal tests — the guided first-look panel and the occasion portals.
 *
 * Goal: a VISITOR (no account) tells the home page their occasion, budget,
 * palette and fit comfort, presses one button, and the stylist opens with a
 * STRUCTURED, machine-usable brief — English catalogue tokens, a numeric
 * budget, and mapped constraint values — regardless of UI language.
 *
 * These are behaviour tests against the REAL ui store (no mock): the
 * assertion target is the exact prefill contract the stylist drawer will
 * send to POST /stylist/chat, because that is what decides whether the
 * recommendation is grounded or garbage.
 *
 * Counter-goals pinned here:
 *  - "No preference" must mean ABSENT constraints (undefined), never a
 *    literal "No preference" string leaking into the API.
 *  - An Arabic UI must still emit English tokens (occasion/palette/fit are
 *    contract values, not copy).
 *  - The occasion PORTAL cards open the stylist too — they must never be
 *    dead decorative tiles.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  render,
  cleanup,
  screen,
  act,
  fireEvent,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";
import React from "react";
import i18n from "../../i18n/i18n";

/* ------------------------------------------------------------------ mocks */

const { vmState, newestMock, capState } = vi.hoisted(() => ({
  vmState: {
    products: [] as unknown[],
    categories: [] as unknown[],
    isLoading: false,
    error: null as string | null,
  },
  newestMock: vi.fn(),
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
    setSelectedCategory: vi.fn(),
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

import { HomeView } from "../consumer/HomeView";
import { useUIStore } from "../../stores/uiStore";

/* --------------------------------------------------------------- helpers */

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

const prefill = () =>
  useUIStore.getState().stylistPrefillOccasion as Record<string, any> | null;

async function setAppLanguage(lang: string) {
  await act(async () => {
    await i18n.changeLanguage(lang);
  });
}

beforeEach(() => {
  cleanup();
  vmState.products = [];
  vmState.categories = [];
  vmState.isLoading = false;
  vmState.error = null;
  newestMock.mockReset().mockResolvedValue([]);
  // Real store, deterministic start per test.
  useUIStore.setState({ isStylistDrawerOpen: false, stylistPrefillOccasion: null });
});
afterEach(async () => {
  await setAppLanguage("en");
  cleanup();
});

/* ------------------------------------------------------------------ tests */

describe("Goal: a visitor gets a structured first-look brief from one button", () => {
  it("defaults produce a complete, structured stylist prefill", () => {
    renderHome();
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("home.ask_stylist_cta") }),
    );
    const p = prefill();
    expect(useUIStore.getState().isStylistDrawerOpen).toBe(true);
    expect(p).not.toBeNull();
    // English contract tokens + numeric budget — the machine half of the brief.
    expect(p!.occasion).toBe("Work");
    expect(p!.budget).toBe(450);
    expect(p!.recommendation_constraints).toEqual({
      palette: "navy",
      preferred_fit: undefined,
    });
    expect(typeof p!.prompt).toBe("string");
    expect(p!.prompt).toContain("occasion=Work");
  });

  it("every selection the visitor changes lands mapped in the brief", () => {
    renderHome();
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("home.guide_occasion_wedding") }),
    );
    fireEvent.change(
      screen.getByLabelText(i18n.t("home.budget_guide")),
      { target: { value: "900" } },
    );
    fireEvent.change(
      screen.getByLabelText(i18n.t("home.palette_preference")),
      { target: { value: "Black / metallic" } },
    );
    fireEvent.change(
      screen.getByLabelText(i18n.t("home.fit_preference")),
      { target: { value: "Tailored" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("home.ask_stylist_cta") }),
    );
    const p = prefill()!;
    expect(p.occasion).toBe("Wedding");
    expect(p.budget).toBe(900);
    expect(p.recommendation_constraints.palette).toBe("black");
    expect(p.recommendation_constraints.preferred_fit).toBe("slim");
  });

  it('counter-goal: "No preference" sends ABSENT constraints, never the literal string', () => {
    renderHome();
    fireEvent.change(
      screen.getByLabelText(i18n.t("home.palette_preference")),
      { target: { value: "No preference" } },
    );
    fireEvent.change(
      screen.getByLabelText(i18n.t("home.fit_preference")),
      { target: { value: "No preference" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("home.ask_stylist_cta") }),
    );
    const c = prefill()!.recommendation_constraints;
    expect(c.palette).toBeUndefined();
    expect(c.preferred_fit).toBeUndefined();
    // The free-text brief must mirror the structured half: no leaked UI
    // literal, and no invented currency symbol (budget is unitless in the
    // stylist contract; the catalogue presents EGP/AED, never "$").
    expect(JSON.stringify(prefill())).not.toContain("No preference");
    expect(prefill()!.prompt).not.toContain("$");
  });

  it("counter-goal: an Arabic UI still emits English contract tokens", async () => {
    await setAppLanguage("ar");
    renderHome();
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("home.guide_occasion_travel") }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("home.ask_stylist_cta") }),
    );
    const p = prefill()!;
    expect(p.occasion).toBe("Travel"); // token, not الترحال
    expect(/[\u0600-\u06FF]/.test(p.occasion)).toBe(false);
  });

  it("the aria-pressed state tracks the chosen occasion pill", () => {
    renderHome();
    const wedding = screen.getByRole("button", {
      name: i18n.t("home.guide_occasion_wedding"),
    });
    expect(wedding.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(wedding);
    expect(wedding.getAttribute("aria-pressed")).toBe("true");
    expect(
      screen
        .getByRole("button", { name: i18n.t("home.guide_occasion_work") })
        .getAttribute("aria-pressed"),
    ).toBe("false");
  });
});

describe("Goal: occasion portals are live stylist entries, not decorative tiles", () => {
  it("clicking a portal opens the stylist drawer with that occasion's visible title", () => {
    renderHome();
    fireEvent.click(
      screen.getByRole("button", {
        name: new RegExp(i18n.t("home.occasion_wedding") as string),
      }),
    );
    expect(useUIStore.getState().isStylistDrawerOpen).toBe(true);
    expect(useUIStore.getState().stylistPrefillOccasion).toBe(
      i18n.t("home.occasion_wedding"),
    );
  });
});
