/**
 * IBM Granite stylist panel — contract tests.
 *
 * Pins the honesty + state behaviour the backend contract promises:
 *   · the request carries the user's occasion / time / season / location
 *     and preference lists (comma-split), never fabricated defaults;
 *   · an `ai_generated: false` result renders the FALLBACK badge and never
 *     the "Styled by <model>" copy (Scenario J);
 *   · an `ai_generated: true` result names the model id;
 *   · missing categories are shown as a limitation, not invented;
 *   · PROVIDER_ERROR shows a retry; FEATURE_NOT_CONFIGURED shows the
 *     actionable configuration message without a retry button;
 *   · "Another outfit" sends previous_item_ids; "Swap out" excludes the id;
 *   · signed-out visitors see the sign-in state, no request is made;
 *   · axe-clean in EN and AR/RTL.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor, within } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "vitest-axe";

import i18n, { setAppLanguage } from "../../../i18n/i18n";
import en from "../../../i18n/en.json";
import ar from "../../../i18n/ar.json";
import { ApiError } from "../../../services/apiClient";

const recommendOutfit = vi.fn();
const getStylistStatus = vi.fn();
const saveOutfit = vi.fn();
vi.mock("../../../services/apiServices", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../../../services/apiServices")>();
  return {
    ...mod,
    wardrobeService: {
      ...mod.wardrobeService,
      recommendOutfit: (...a: unknown[]) => recommendOutfit(...a),
      getStylistStatus: (...a: unknown[]) => getStylistStatus(...a),
      saveOutfit: (...a: unknown[]) => saveOutfit(...a),
    },
  };
});

import { WardrobeStylistPanel } from "../WardrobeStylistPanel";

const modelResult = {
  outfit_id: "wx_1",
  occasion: "Casual",
  title: "Relaxed autumn park look",
  summary: "Earthy, layer-friendly pieces.",
  items: [
    { wardrobe_item_id: 1, role: "top", category: "Tops", title: "Blue Plaid Shirt", subcategory: "Shirt",
      color_name: "Blue", color_hex: "#224", image_url: "https://example.com/1.jpg",
      reason: "Plaid flannel suits a cool morning.", analysis_source: "meta-llama/llama-4-maverick-17b-128e-instruct-fp8", ai_confidence: 0.9 },
    { wardrobe_item_id: 2, role: "bottom", category: "Bottoms", title: "Khaki Chinos", subcategory: "Chinos",
      color_name: "Beige", color_hex: "#ccb", image_url: "https://example.com/2.jpg",
      reason: "Khaki balances the plaid.", analysis_source: "manual", ai_confidence: null },
  ],
  styling_notes: ["Roll the sleeves once."],
  limitations: [],
  missing_categories: ["Footwear"],
  assumptions: ["Mild weather assumed."],
  is_complete: false,
  source: "watsonx" as const,
  ai_generated: true,
  model_id: "ibm/granite-4-h-small",
  prompt_version: "wx-stylist-1.0",
  fallback_reason: null,
  latency_seconds: 2.3,
  rejected_references: [],
  context: {},
};

const fallbackResult = {
  ...modelResult,
  outfit_id: "det_1",
  source: "deterministic_fallback" as const,
  ai_generated: false,
  model_id: null,
  prompt_version: null,
  fallback_reason: "watsonx_not_configured",
  latency_seconds: null,
  limitations: ["This outfit was assembled by CONFIT's rule-based matcher, not by the AI stylist."],
};

function renderPanel(props: Partial<React.ComponentProps<typeof WardrobeStylistPanel>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <WardrobeStylistPanel
          isAuthenticated
          readyItemCount={3}
          onOpenUpload={vi.fn()}
          onSignIn={vi.fn()}
          {...props}
        />
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(async () => {
  await setAppLanguage("en");
  recommendOutfit.mockReset();
  getStylistStatus.mockReset();
  saveOutfit.mockReset();
  getStylistStatus.mockResolvedValue({
    watsonx_configured: true, reasoning_model_id: "ibm/granite-4-h-small", vision_model_id: "x",
    vision_provider_mode: "auto", stylist_provider_mode: "auto", legacy_vision_configured: false,
    ready_items: 3, categories_present: ["Tops", "Bottoms"], prompt_version: "wx-stylist-1.0",
  });
});
afterEach(() => cleanup());

describe("WardrobeStylistPanel", () => {
  it("sends the user's context and comma-split preferences", async () => {
    recommendOutfit.mockResolvedValue(modelResult);
    renderPanel();
    fireEvent.change(screen.getByLabelText(en.wardrobe_stylist.occasion), { target: { value: "Casual" } });
    fireEvent.change(screen.getByLabelText(en.wardrobe_stylist.time_of_day), { target: { value: "morning" } });
    fireEvent.change(screen.getByLabelText(en.wardrobe_stylist.season), { target: { value: "autumn" } });
    fireEvent.change(screen.getByLabelText(en.wardrobe_stylist.location), { target: { value: "  park " } });
    fireEvent.click(screen.getByText(en.wardrobe_stylist.more_prefs));
    fireEvent.change(screen.getByLabelText(en.wardrobe_stylist.style_prefs), { target: { value: "relaxed, layered,, " } });
    fireEvent.change(screen.getByLabelText(en.wardrobe_stylist.color_prefs), { target: { value: "navy، earth tones" } });
    fireEvent.change(screen.getByLabelText(en.wardrobe_stylist.excluded_colors), { target: { value: "black, red " } });
    fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.generate }));

    await waitFor(() => expect(recommendOutfit).toHaveBeenCalledTimes(1));
    expect(recommendOutfit).toHaveBeenCalledWith({
      occasion: "Casual", time_of_day: "morning", season: "autumn", location: "park",
      style_preferences: ["relaxed", "layered"], color_preferences: ["navy", "earth tones"], excluded_colors: ["black", "red"],
      comfort_needs: undefined, exclusions: undefined, excluded_item_ids: [], previous_item_ids: [], language: "en",
    });
    const result = await screen.findByTestId("stylist-result");
    expect(result.getAttribute("data-source")).toBe("watsonx");
    expect(screen.getByTestId("stylist-source-badge").textContent).toContain("ibm/granite-4-h-small");
    expect(screen.getByText("Plaid flannel suits a cool morning.")).toBeTruthy();
    // Images come from the trusted rows the server resolved
    const imgs = within(result).getAllByRole("img");
    expect(imgs.map((i) => i.getAttribute("src"))).toEqual(["https://example.com/1.jpg", "https://example.com/2.jpg"]);
    // Missing footwear is disclosed, not invented
    expect(screen.getByText(/no Footwear to complete this look/i)).toBeTruthy();
    expect(screen.getByText(en.wardrobe_stylist.partial)).toBeTruthy();
    // Per-item provenance
    expect(screen.getByText(en.wardrobe_stylist.tagged_manually)).toBeTruthy();
  });

  it("labels a deterministic fallback honestly and never as AI (Scenario J)", async () => {
    recommendOutfit.mockResolvedValue(fallbackResult);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.generate }));
    const result = await screen.findByTestId("stylist-result");
    expect(result.getAttribute("data-source")).toBe("deterministic_fallback");
    expect(screen.getByTestId("stylist-source-badge").textContent).toBe(en.wardrobe_stylist.source_fallback);
    expect(screen.queryByText(/Styled by/)).toBeNull();
    expect(screen.getByText(en.wardrobe_stylist.footer_fallback)).toBeTruthy();
  });

  it("'Another outfit' passes previous ids; 'Swap out' excludes an item", async () => {
    recommendOutfit.mockResolvedValue(modelResult);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.generate }));
    await screen.findByTestId("stylist-result");
    fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.another }));
    await waitFor(() => expect(recommendOutfit).toHaveBeenCalledTimes(2));
    expect(recommendOutfit.mock.calls[1][0].previous_item_ids).toEqual([1, 2]);

    await screen.findByTestId("stylist-result");
    fireEvent.click(screen.getByRole("button", { name: "Swap out Blue Plaid Shirt" }));
    fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.another }));
    await waitFor(() => expect(recommendOutfit).toHaveBeenCalledTimes(3));
    expect(recommendOutfit.mock.calls[2][0].excluded_item_ids).toEqual([1]);
  });

  it("provider failure offers retry; missing configuration is actionable without retry (Scenarios E/F)", async () => {
    recommendOutfit.mockRejectedValueOnce(new ApiError("Provider 'watsonx' error: watsonx_timeout", "PROVIDER_ERROR", 502, { retryable: true }));
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.generate }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(en.wardrobe_stylist.error_provider);
    expect(within(alert).getByRole("button", { name: en.common.try_again })).toBeTruthy();

    recommendOutfit.mockRejectedValueOnce(new ApiError("Feature 'watsonx_stylist' is not configured", "FEATURE_NOT_CONFIGURED", 501, {}));
    fireEvent.click(within(alert).getByRole("button", { name: en.common.try_again }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("WATSONX_APIKEY"));
    expect(within(screen.getByRole("alert")).queryByRole("button", { name: en.common.try_again })).toBeNull();
  });

  it("empty wardrobe shows guidance and the upload CTA", () => {
    const onOpenUpload = vi.fn();
    renderPanel({ readyItemCount: 0, onOpenUpload });
    expect(screen.getByText(en.wardrobe_stylist.empty_title)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.wardrobe.upload_piece }));
    expect(onOpenUpload).toHaveBeenCalled();
  });

  it("signed-out visitors get the sign-in state and no request", () => {
    const onSignIn = vi.fn();
    renderPanel({ isAuthenticated: false, onSignIn });
    fireEvent.click(screen.getByRole("button", { name: en.auth.sign_in }));
    expect(onSignIn).toHaveBeenCalled();
    expect(recommendOutfit).not.toHaveBeenCalled();
    expect(getStylistStatus).not.toHaveBeenCalled();
  });

  it("is axe-clean in EN and in AR/RTL with a result rendered", async () => {
    recommendOutfit.mockResolvedValue(modelResult);
    const { container, unmount } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.generate }));
    await screen.findByTestId("stylist-result");
    expect((await axe(container)).violations).toEqual([]);
    unmount();

    await setAppLanguage("ar");
    const r2 = renderPanel();
    expect(screen.getByText(ar.wardrobe_stylist.prefs_title)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: ar.wardrobe_stylist.generate }));
    await screen.findByTestId("stylist-result");
    expect(screen.getByTestId("stylist-source-badge").textContent).toContain("ibm/granite-4-h-small");
    expect((await axe(r2.container)).violations).toEqual([]);
  });

  describe("Save this look", () => {
    async function generate(result: typeof modelResult) {
      recommendOutfit.mockResolvedValue(result);
      renderPanel();
      fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.generate }));
      await screen.findByTestId("stylist-result");
    }

    it("sends ids + provenance to POST /wardrobe/outfits and reports success only after a 201 with an id", async () => {
      await generate(modelResult);
      saveOutfit.mockResolvedValue({ id: 42, items: modelResult.items, rejected_references: [], dropped_item_count: 0 });
      const btn = screen.getByTestId("stylist-save-look");
      expect(btn).toHaveTextContent(en.wardrobe_stylist.save_look);
      fireEvent.click(btn);
      await waitFor(() => expect(saveOutfit).toHaveBeenCalledTimes(1));
      const payload = saveOutfit.mock.calls[0][0];
      expect(payload.items).toEqual([
        { wardrobe_item_id: 1, reason: modelResult.items[0].reason },
        { wardrobe_item_id: 2, reason: modelResult.items[1].reason },
      ]);
      expect(payload.source).toBe("watsonx");
      expect(payload.ai_generated).toBe(true);
      expect(payload.model_id).toBe(modelResult.model_id);
      // No role/image/category travels — the server derives them from stored rows.
      expect(Object.keys(payload.items[0])).toEqual(["wardrobe_item_id", "reason"]);
      await waitFor(() => expect(screen.getByTestId("stylist-save-look")).toHaveAttribute("data-save-state", "saved"));
      expect(screen.getByTestId("stylist-save-status")).toHaveTextContent("#42");
      expect(screen.getByTestId("stylist-save-look")).toBeDisabled();
    });

    it("never claims a save that failed, and re-enables the button", async () => {
      await generate(modelResult);
      saveOutfit.mockRejectedValue(new ApiError("boom", "HTTP_ERROR", 500, {}));
      fireEvent.click(screen.getByTestId("stylist-save-look"));
      await waitFor(() => expect(screen.getByTestId("stylist-save-look")).toHaveAttribute("data-save-state", "error"));
      expect(screen.getByTestId("stylist-save-status")).toHaveTextContent(en.wardrobe_stylist.save_failed);
      expect(screen.getByTestId("stylist-save-look")).not.toBeDisabled();
      expect(screen.queryByText(/Saved to your wardrobe looks/)).toBeNull();
    });

    it("surfaces the server's 422 reason verbatim (e.g. nothing left to save)", async () => {
      await generate(modelResult);
      saveOutfit.mockRejectedValue(new ApiError("None of the pieces in this look are in your wardrobe any more, so it was not saved.", "VALIDATION_ERROR", 422, {}));
      fireEvent.click(screen.getByTestId("stylist-save-look"));
      await waitFor(() => expect(screen.getByTestId("stylist-save-status")).toHaveTextContent(/not saved/));
    });

    it("resets the saved state when another outfit is generated", async () => {
      await generate(modelResult);
      saveOutfit.mockResolvedValue({ id: 7, items: modelResult.items, rejected_references: [], dropped_item_count: 0 });
      fireEvent.click(screen.getByTestId("stylist-save-look"));
      await waitFor(() => expect(screen.getByTestId("stylist-save-look")).toHaveAttribute("data-save-state", "saved"));
      recommendOutfit.mockResolvedValue({ ...modelResult, outfit_id: "wx_2" });
      fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.another }));
      await waitFor(() => expect(recommendOutfit).toHaveBeenCalledTimes(2));
      await waitFor(() => expect(screen.getByTestId("stylist-save-look")).toHaveAttribute("data-save-state", "idle"));
    });
  });
});
