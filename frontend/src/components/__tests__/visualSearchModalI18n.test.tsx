/**
 * C02 — the visual-search modal speaks BOTH product languages.
 *
 * THE DEFECT THIS PINS (2026-10-08 Discover re-pass)
 * --------------------------------------------------
 * Visual search is an advertised Discover feature, yet roughly a dozen of
 * its strings were hardcoded English: the step label, "Analyzing…" /
 * "Search Style", the empty-state hint, the detection banner, "Try again",
 * the "% Match" badge, the raw backend match_type token, the sample
 * labels and the detail-load error. An Arabic shopper got a half-English
 * dialog. The ✕ close button also had no accessible name at all.
 *
 * THE CONTRACT
 * ------------
 *  1. In Arabic, every modal string the USER reads is Arabic (the known
 *     set above), and the close button exposes the translated
 *     `a11y.close_dialog` name.
 *  2. The backend's EN match-type display strings map to translated
 *     labels; an UNKNOWN future value still renders raw (readable, never
 *     blank) — same fallback philosophy as occasionLabel on Discover.
 *  3. Source guard: the literals that were removed never come back.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup, screen, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import React from "react";
import i18n from "../../i18n/i18n";

/* ------------------------------------------------------------------ mocks */

const { vmState } = vi.hoisted(() => ({
  vmState: {
    visualSearchLoading: false,
    visualSearchResult: null as unknown,
    visualSearchError: null as string | null,
  },
}));

vi.mock("../../viewmodels/useTryOnViewModel", () => ({
  useTryOnViewModel: () => ({
    visualSearchLoading: vmState.visualSearchLoading,
    visualSearchResult: vmState.visualSearchResult,
    visualSearchError: vmState.visualSearchError,
    runVisualSearch: vi.fn(),
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
      gate: () => () => {},
    }),
  };
});

import { VisualSearchModal } from "../tryon/VisualSearchModal";
import { useUIStore } from "../../stores/uiStore";

/* -------------------------------------------------------------- fixtures */

const MATCH = (id: number, matchType: string) => ({
  product_id: id,
  title: `Match ${id}`,
  brand_name: "Reiss",
  price: 120,
  currency: "USD",
  image_url: `https://img.example/m${id}.jpg`,
  similarity_score: 90,
  match_type: matchType,
});

function renderModal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <VisualSearchModal />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

async function setAppLanguage(lang: string) {
  await act(async () => {
    await i18n.changeLanguage(lang);
  });
}

/* ------------------------------------------------------------------ tests */

describe("VisualSearchModal — i18n + accessible-name contract", () => {
  beforeEach(() => {
    cleanup();
    vmState.visualSearchLoading = false;
    vmState.visualSearchResult = null;
    vmState.visualSearchError = null;
    act(() => {
      useUIStore.getState().openVisualSearch();
    });
  });
  afterEach(async () => {
    act(() => {
      useUIStore.getState().closeVisualSearch();
    });
    await setAppLanguage("en");
    vi.clearAllMocks();
  });

  it("renders the full Arabic surface: step label, CTA, empty hint, samples, named close button", async () => {
    await setAppLanguage("ar");
    renderModal();
    // Step label + CTA + empty-state hint come from ar.json, not EN source.
    expect(
      screen.getByText(i18n.t("tryon.vs_step1_label")),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: i18n.t("tryon.vs_search_style") }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        i18n.t("tryon.vs_empty_hint", { cta: i18n.t("tryon.vs_search_style") }),
      ),
    ).toBeInTheDocument();
    // A sample label — previously hardcoded "Navy Wool Blazer".
    expect(
      screen.getByRole("button", { name: new RegExp(i18n.t("tryon.vs_sample_blazer")) }),
    ).toBeInTheDocument();
    // The ✕ button now has a real accessible name.
    expect(
      screen.getByRole("button", { name: i18n.t("a11y.close_dialog") }),
    ).toBeInTheDocument();
    // Nothing of the old EN surface leaks into the Arabic dialog.
    expect(screen.queryByText(/Search Style/)).toBeNull();
    expect(screen.queryByText(/Upload Your Own Photo/)).toBeNull();
  });

  it("translates known backend match types and score badge; unknown types render raw, never blank", async () => {
    await setAppLanguage("ar");
    vmState.visualSearchResult = {
      analysis_available: false,
      matches: [MATCH(1, "Exact Match"), MATCH(2, "Weird Future Type")],
    };
    renderModal();
    // Honest degrade banner is Arabic.
    expect(
      screen.getByText(i18n.t("tryon.vs_analysis_unavailable")),
    ).toBeInTheDocument();
    // Known EN display string → Arabic label.
    expect(
      screen.getByText(i18n.t("tryon.vs_match_type_exact")),
    ).toBeInTheDocument();
    expect(screen.queryByText("Exact Match")).toBeNull();
    // Unknown value falls back to the raw token (readable, not hidden).
    expect(screen.getByText("Weird Future Type")).toBeInTheDocument();
    // Score badge is the translated template, twice (one per match).
    expect(
      screen.getAllByText(i18n.t("tryon.vs_match_score", { score: 90 })),
    ).toHaveLength(2);
  });

  it("loading state shows the translated analyzing label", async () => {
    await setAppLanguage("ar");
    vmState.visualSearchLoading = true;
    renderModal();
    expect(
      screen.getByText(i18n.t("tryon.vs_analyzing")),
    ).toBeInTheDocument();
  });

  it("source guard: the removed hardcoded literals never return", () => {
    const src = readFileSync(
      join(__dirname, "..", "tryon", "VisualSearchModal.tsx"),
      "utf8",
    );
    for (const literal of [
      '"Analyzing..."',
      '"Search Style"',
      "Upload Your Own Photo, Choose a Sample",
      "Searching with your photo…",
      '"Try again"',
      "% Match",
      "matches without image detection.\n",
      'alt="Your uploaded query"',
      '"Could not load the matched product detail."',
    ]) {
      expect(src, `hardcoded EN literal came back: ${literal}`).not.toContain(
        literal,
      );
    }
    // The raw backend token must pass through the translation map.
    expect(src).toContain("matchTypeLabel(match.match_type)");
  });
});
