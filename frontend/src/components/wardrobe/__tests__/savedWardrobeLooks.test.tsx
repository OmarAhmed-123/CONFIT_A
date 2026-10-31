/**
 * Saved wardrobe looks — contract tests.
 *   · lists GET /wardrobe/outfits with stored photos and per-look provenance;
 *   · a rule-based look is labelled as such, never as a model;
 *   · dropped garments are reported, incomplete looks flagged;
 *   · delete removes the card only after the API succeeded; a failure keeps it;
 *   · empty + error states; signed-out renders nothing (no request);
 *   · axe-clean in EN and AR.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "vitest-axe";

import i18n, { setAppLanguage } from "../../../i18n/i18n";
import en from "../../../i18n/en.json";
import ar from "../../../i18n/ar.json";
import { ApiError } from "../../../services/apiClient";

const listSavedOutfits = vi.fn();
const deleteSavedOutfit = vi.fn();
vi.mock("../../../services/apiServices", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../../../services/apiServices")>();
  return {
    ...mod,
    wardrobeService: {
      ...mod.wardrobeService,
      listSavedOutfits: (...a: unknown[]) => listSavedOutfits(...a),
      deleteSavedOutfit: (...a: unknown[]) => deleteSavedOutfit(...a),
    },
  };
});

import { SavedWardrobeLooks } from "../SavedWardrobeLooks";

const aiLook = {
  id: 11, title: "Evening smart casual", occasion: "Smart Casual", summary: "Shirt, chinos, loafers.",
  items: [
    { wardrobe_item_id: 1, role: "top", category: "Tops", title: "White Oxford Shirt", color_name: "White", color_hex: "#fff", image_url: "https://cdn.example.com/1.jpg", reason: "Base." },
    { wardrobe_item_id: 2, role: "bottom", category: "Bottoms", title: "Navy Chinos", color_name: "Navy", color_hex: "#123", image_url: "https://cdn.example.com/2.jpg", reason: "Contrast." },
    { wardrobe_item_id: 3, role: "footwear", category: "Footwear", title: "Brown Loafers", color_name: "Brown", color_hex: "#531", image_url: "https://cdn.example.com/3.jpg", reason: "Finish." },
  ],
  styling_notes: [], limitations: [], missing_categories: [], context: {}, is_complete: true,
  source: "watsonx", ai_generated: true, model_id: "ibm/granite-4-h-small", prompt_version: "wx-stylist-1.0",
  created_at: "2026-10-26T10:00:00+00:00", dropped_item_count: 0, rejected_references: [],
};
const rulesLook = {
  ...aiLook, id: 12, title: "Rule-based look", source: "deterministic_fallback", ai_generated: false, model_id: null,
  items: aiLook.items.slice(0, 1), is_complete: false, dropped_item_count: 2,
};

function renderIt(props: Partial<React.ComponentProps<typeof SavedWardrobeLooks>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <SavedWardrobeLooks isAuthenticated onOpenStylist={vi.fn()} {...props} />
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(async () => {
  await setAppLanguage("en");
  listSavedOutfits.mockReset();
  deleteSavedOutfit.mockReset();
});
afterEach(() => cleanup());

describe("SavedWardrobeLooks", () => {
  it("renders saved looks with stored photos and honest provenance", async () => {
    listSavedOutfits.mockResolvedValue([aiLook, rulesLook]);
    renderIt();
    const cards = await screen.findAllByTestId("saved-wardrobe-look");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute("data-source", "watsonx");
    expect(cards[0].querySelector('[data-testid="saved-look-provenance"]')).toHaveTextContent("ibm/granite-4-h-small");
    expect(cards[1].querySelector('[data-testid="saved-look-provenance"]')).toHaveTextContent(en.wardrobe_stylist.saved_looks_made_by_rules);
    expect(cards[1]).not.toHaveTextContent("granite");
    const img = cards[0].querySelector("img[src='https://cdn.example.com/3.jpg']");
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute("alt", "Brown Loafers — Brown");
    expect(cards[1].querySelector('[data-testid="saved-look-caveat"]')).toHaveTextContent("2 pieces");
  });

  it("deletes a look only after the API confirms, and keeps it on failure", async () => {
    listSavedOutfits.mockResolvedValue([aiLook, rulesLook]);
    renderIt();
    await screen.findAllByTestId("saved-wardrobe-look");
    deleteSavedOutfit.mockRejectedValueOnce(new ApiError("down", "HTTP_ERROR", 503, {}));
    const [first] = screen.getAllByRole("button", { name: en.wardrobe_stylist.saved_looks_delete });
    fireEvent.click(first);
    await waitFor(() => expect(deleteSavedOutfit).toHaveBeenCalledWith(11));
    await screen.findByText(en.wardrobe_stylist.saved_looks_delete_failed);
    expect(screen.getAllByTestId("saved-wardrobe-look")).toHaveLength(2);

    deleteSavedOutfit.mockResolvedValueOnce(undefined);
    fireEvent.click(screen.getAllByRole("button", { name: en.wardrobe_stylist.saved_looks_delete })[0]);
    await waitFor(() => expect(screen.getAllByTestId("saved-wardrobe-look")).toHaveLength(1));
    expect(screen.getByText(en.wardrobe_stylist.saved_looks_deleted)).toBeInTheDocument();
  });

  it("shows the empty state with a path to the stylist, and the error state", async () => {
    const onOpenStylist = vi.fn();
    listSavedOutfits.mockResolvedValue([]);
    renderIt({ onOpenStylist });
    await screen.findByText(en.wardrobe_stylist.saved_looks_empty);
    fireEvent.click(screen.getByRole("button", { name: en.wardrobe_stylist.tab }));
    expect(onOpenStylist).toHaveBeenCalled();
    cleanup();
    listSavedOutfits.mockRejectedValue(new ApiError("x", "HTTP_ERROR", 500, {}));
    renderIt();
    await screen.findByRole("alert");
  });

  it("makes no request and renders nothing when signed out", () => {
    const { container } = renderIt({ isAuthenticated: false });
    expect(listSavedOutfits).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });

  it("is axe-clean in EN and AR", async () => {
    listSavedOutfits.mockResolvedValue([aiLook, rulesLook]);
    const { container } = renderIt();
    await screen.findAllByTestId("saved-wardrobe-look");
    expect((await axe(container)).violations).toEqual([]);
    cleanup();
    await setAppLanguage("ar");
    const { container: arC } = renderIt();
    await screen.findByText(ar.wardrobe_stylist.saved_looks_title);
    expect((await axe(arC)).violations).toEqual([]);
  });
});
