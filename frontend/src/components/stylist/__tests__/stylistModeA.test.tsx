/**
 * StyleList Mode A (photo styling) — drawer behaviour and accessibility.
 *
 * Covers the remaining T-STY-07 acceptance items that are in spec 009 scope:
 * - an image turn that could not use the photos says WHY (honest fallback, FR-003);
 * - the served model is stated on the answer (FR-003);
 * - a Mode A look can be saved through the existing outfit-save API (STY-10 scope
 *   amendment in spec.md), signed-in only, with honest error states;
 * - attachment errors and thumbnails are announced and labelled (WCAG);
 * - axe runs with colour-contrast ENABLED on the attachment states (the existing
 *   contract test turns it off);
 * - Arabic renders right-to-left and the new strings are localized.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import axe from "axe-core";
import i18n from "../../../i18n/i18n";
import { VirtualStylistDrawer } from "../VirtualStylistDrawer";
import { ApiError } from "../../../services/apiClient";

const { chatMock, saveOutfitMock, addItemMock, openCartMock, showToastMock, closeStylistMock } = vi.hoisted(() => ({
  chatMock: vi.fn(),
  saveOutfitMock: vi.fn(),
  addItemMock: vi.fn(),
  openCartMock: vi.fn(),
  showToastMock: vi.fn(),
  closeStylistMock: vi.fn(),
}));

vi.mock("../../../services/apiServices", async (importOriginal) => {
  const actual: any = await importOriginal();
  return {
    ...actual,
    stylistService: { ...actual.stylistService, chat: chatMock, saveOutfit: saveOutfitMock },
  };
});

vi.mock("../../../stores/cartStore", () => ({
  useCartStore: () => ({ addItem: addItemMock, openCart: openCartMock }),
}));

vi.mock("../../../stores/uiStore", () => ({
  useUIStore: () => ({
    isStylistDrawerOpen: true,
    closeStylist: closeStylistMock,
    stylistPrefillOccasion: null,
    openTryOn: vi.fn(),
    openRuler: vi.fn(),
    showToast: showToastMock,
  }),
}));

vi.mock("../../../hooks/useTryOnAvailability", () => ({
  useTryOnAvailability: () => ({ ctaKind: () => "try_on", userMessage: null }),
}));

const en = (key: string, vars?: Record<string, unknown>) => i18n.getFixedT("en")(key, vars) as string;

const item = (id: number, over: Record<string, unknown> = {}) => ({
  id,
  product_id: id,
  product_title: `Piece ${id}`,
  brand_name: "Arket",
  category_name: "Apparel",
  price: 120,
  currency: "EGP",
  image_url: "/img.jpg",
  color_hex: "#1B1F3B",
  position: "top",
  sku_id: id * 100,
  selected_size: "M",
  ...over,
});

const outfit = (over: Record<string, unknown> = {}) => ({
  id: 101,
  title: "Evening Composition",
  description: "",
  occasion: "Evening & Party",
  total_price: 360,
  currency: "EGP",
  compatibility_score: 91,
  color_harmony_score: 84,
  formality_score: 72,
  color_palette: ["#1B1F3B", "#C5A059", "#FAF9F6"],
  style_tags: [],
  is_saved: false,
  is_system_curated: true,
  is_complete: true,
  completeness_status: "complete_look",
  completeness_label: "Complete Ensemble",
  items: [item(1, { position: "outerwear" }), item(2, { position: "bottom" }), item(3, { position: "footwear" })],
  created_at: "2026-01-01T00:00:00Z",
  ...over,
});

const assistantMessage = (over: Record<string, unknown> = {}) => ({
  id: 7,
  session_id: 1,
  sender: "assistant",
  content: "Here is a composed look.",
  intent_detected: {},
  recommendations: [outfit()],
  created_at: "2026-01-01T00:00:00Z",
  engine: "NVIDIA google/diffusiongemma-26b-a4b-it",
  mode: "A",
  fallback_reason: null,
  image_analysis: { available: true, engine: "NVIDIA google/diffusiongemma-26b-a4b-it" },
  ...over,
});

function renderDrawer() {
  return render(
    <I18nextProvider i18n={i18n}>
      <VirtualStylistDrawer />
    </I18nextProvider>,
  );
}

async function ask(text = "Style me from this photo") {
  const input = screen.getByPlaceholderText(en("stylist.input_placeholder"));
  fireEvent.change(input, { target: { value: text } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: new RegExp(en("stylist.submit")) }));
  });
}

function pngFile(name = "outfit.png") {
  return new File([new Uint8Array([137, 80, 78, 71])], name, { type: "image/png" });
}

async function attach(files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input, "a file input must exist").toBeTruthy();
  await act(async () => {
    fireEvent.change(input, { target: { files } });
  });
}

beforeEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  chatMock.mockReset();
  saveOutfitMock.mockReset();
  addItemMock.mockReset();
  showToastMock.mockReset();
});

afterEach(() => cleanup());

describe("Mode A — honest state on the answer (FR-003)", () => {
  it("states why the photos were not used when the vision leg was unavailable", async () => {
    const reason = "The image analysis service did not answer, so this reply uses your text request only.";
    chatMock.mockResolvedValue(
      assistantMessage({
        mode: "B",
        fallback_reason: reason,
        image_analysis: { available: false, reason },
        engine: "CONFIT Grounded Styling Engine",
      }),
    );
    renderDrawer();
    await ask();
    const note = await screen.findByTestId("stylist-mode-note");
    // Localized note, not the backend's English sentence: an Arabic shopper must not read English here.
    expect(note.textContent).toBe(en("stylist.mode_fallback_note"));
    expect(note.getAttribute("role")).toBe("status");
  });

  it("names the vision model that actually answered the photo analysis", async () => {
    chatMock.mockResolvedValue(assistantMessage());
    renderDrawer();
    await ask();
    await screen.findByTestId("stylist-ensemble-total");
    const engine = document.querySelector('[data-engine="NVIDIA google/diffusiongemma-26b-a4b-it"]');
    expect(engine?.textContent).toContain("google/diffusiongemma-26b-a4b-it");
    expect(screen.queryByTestId("stylist-mode-note")).toBeNull();
  });
});

describe("Mode A — save a look (STY-10 scope amendment)", () => {
  it("offers Save look only on Mode A recommendations", async () => {
    chatMock.mockResolvedValue(assistantMessage({ mode: "B", image_analysis: null, engine: "none" }));
    renderDrawer();
    await ask("a smart casual dinner");
    await screen.findByTestId("stylist-ensemble-total");
    expect(screen.queryByRole("button", { name: en("stylist.save_look") })).toBeNull();
  });

  it("saves through the existing outfit API with the look's real product ids", async () => {
    chatMock.mockResolvedValue(assistantMessage());
    saveOutfitMock.mockResolvedValue({ id: 555 });
    renderDrawer();
    await ask();
    const btn = await screen.findByRole("button", { name: en("stylist.save_look") });
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(saveOutfitMock).toHaveBeenCalledTimes(1);
    expect(saveOutfitMock).toHaveBeenCalledWith({
      title: "Evening Composition",
      occasion: "Evening & Party",
      product_ids: [1, 2, 3],
    });
    expect(await screen.findByRole("status", { name: en("stylist.look_saved") })).toBeTruthy();
    // Saved state is terminal for that look: no second save write.
    expect(screen.queryByRole("button", { name: en("stylist.save_look") })).toBeNull();
  });

  it("tells a guest to sign in rather than failing silently", async () => {
    chatMock.mockResolvedValue(assistantMessage());
    saveOutfitMock.mockRejectedValue(new ApiError("Not authenticated", "UNAUTHORIZED", 401));
    renderDrawer();
    await ask();
    const btn = await screen.findByRole("button", { name: en("stylist.save_look") });
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(await screen.findByText(en("stylist.save_look_signin"))).toBeTruthy();
  });

  it("shows a generic, honest error for any other save failure", async () => {
    chatMock.mockResolvedValue(assistantMessage());
    saveOutfitMock.mockRejectedValue(new ApiError("boom", "SERVER_ERROR", 500));
    renderDrawer();
    await ask();
    const btn = await screen.findByRole("button", { name: en("stylist.save_look") });
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(await screen.findByText(en("stylist.save_look_failed"))).toBeTruthy();
    expect(screen.queryByText(/boom/)).toBeNull();
  });
});

describe("Mode A — attachments: announced, labelled, keyboard reachable", () => {
  it("announces a rejected file type through an alert and keeps the input usable", async () => {
    renderDrawer();
    await attach([new File(["gif"], "anim.gif", { type: "image/gif" })]);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(en("stylist.attach_error_type"));
  });

  it("labels the file control and gives each thumbnail a remove button with a name", async () => {
    renderDrawer();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.getAttribute("accept")).toBe("image/jpeg,image/png,image/webp");
    // The visible control is a <label> that wraps the input, so the input has an accessible name.
    const label = input.closest("label");
    expect(label?.textContent).toContain(en("stylist.attach_photo"));
    await attach([pngFile()]);
    const removeButtons = await screen.findAllByRole("button", { name: en("stylist.remove_photo", { n: 1 }) });
    expect(removeButtons.length).toBe(1);
  });
});

describe("Mode A — accessibility with colour contrast enabled", () => {
  it("the drawer with photos attached and a refusal alert has no serious or critical axe violations", async () => {
    renderDrawer();
    await attach([pngFile()]);
    await attach([new File(["gif"], "anim.gif", { type: "image/gif" })]);
    await screen.findByRole("alert");
    const results = await axe.run(document.body, {
      rules: { "target-size": { enabled: false } },
    });
    const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact || ""));
    expect(serious, JSON.stringify(serious.map((v) => ({ id: v.id, nodes: v.nodes.length })))).toEqual([]);
  });

  it("a saved look and a Mode A answer pass axe with colour contrast enabled", async () => {
    chatMock.mockResolvedValue(assistantMessage());
    renderDrawer();
    await ask();
    await screen.findByRole("button", { name: en("stylist.save_look") });
    const results = await axe.run(document.body, {
      rules: { "target-size": { enabled: false } },
    });
    const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact || ""));
    expect(serious, JSON.stringify(serious.map((v) => ({ id: v.id, nodes: v.nodes.length })))).toEqual([]);
  });
});

describe("Mode A — Arabic (RTL) and localization", () => {
  it("renders the drawer right-to-left with localized attachment and save strings", async () => {
    await act(async () => {
      await i18n.changeLanguage("ar");
    });
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
    renderDrawer();
    await attach([new File(["gif"], "anim.gif", { type: "image/gif" })]);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(i18n.getFixedT("ar")("stylist.attach_error_type") as string);
    // No English fallback leaks into the attachment UI.
    expect(alert.textContent).not.toMatch(/Only JPEG/);
    const label = (document.querySelector('input[type="file"]') as HTMLInputElement).closest("label");
    expect(label?.textContent).toContain(i18n.getFixedT("ar")("stylist.attach_photo") as string);
  });

  it("has no serious or critical axe violations in Arabic", async () => {
    await act(async () => {
      await i18n.changeLanguage("ar");
    });
    renderDrawer();
    await attach([new File(["gif"], "anim.gif", { type: "image/gif" })]);
    await screen.findByRole("alert");
    const results = await axe.run(document.body, {
      rules: { "target-size": { enabled: false } },
    });
    const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact || ""));
    expect(serious, JSON.stringify(serious.map((v) => ({ id: v.id, nodes: v.nodes.length })))).toEqual([]);
  });
});
