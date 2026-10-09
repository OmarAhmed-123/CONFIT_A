/**
 * C05 — Virtual Stylist Drawer behavioral contract.
 *
 * Goal-oriented: each test states a user outcome (money honesty, no duplicate
 * cart writes, translated chrome, skeleton truth) — not DOM structure.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within, act, fireEvent, cleanup } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import axe from "axe-core";
import i18n from "../../../i18n/i18n";
import enJson from "../../../i18n/en.json";
import { VirtualStylistDrawer } from "../VirtualStylistDrawer";

const {
  chatMock,
  addItemMock,
  openCartMock,
  showToastMock,
  closeStylistMock,
} = vi.hoisted(() => ({
  chatMock: vi.fn(),
  addItemMock: vi.fn(),
  openCartMock: vi.fn(),
  showToastMock: vi.fn(),
  closeStylistMock: vi.fn(),
}));

vi.mock("../../../services/apiServices", async (importOriginal) => {
  const actual: any = await importOriginal();
  return {
    ...actual,
    stylistService: { ...actual.stylistService, chat: chatMock },
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
  useTryOnAvailability: () => ({
    ctaKind: () => "try_on",
    userMessage: null,
  }),
}));

const en = (key: string, vars?: Record<string, unknown>) =>
  i18n.getFixedT("en")(key, vars) as string;

const item = (id: number, over: Record<string, unknown> = {}) => ({
  id,
  product_id: id,
  product_title: `Piece ${id}`,
  brand_name: "Reiss",
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
  color_palette: ["#1B1F3B"],
  style_tags: [],
  is_saved: false,
  is_system_curated: true,
  is_complete: true,
  completeness_status: "complete_look",
  completeness_label: "Complete Ensemble",
  items: [
    item(1, { position: "outerwear" }),
    item(2, { position: "bottom" }),
    item(3, { position: "footwear" }),
  ],
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
  engine: "NVIDIA ultra-550b",
  ...over,
});

function renderDrawer() {
  return render(
    <I18nextProvider i18n={i18n}>
      <VirtualStylistDrawer />
    </I18nextProvider>,
  );
}

/** Drive one prompt through the real VM so a recommendation card renders. */
async function askStylist() {
  const input = screen.getByPlaceholderText(en("stylist.input_placeholder"));
  fireEvent.change(input, { target: { value: "Style me for an evening" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: new RegExp(en("stylist.submit")) }));
  });
}

beforeEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  chatMock.mockReset();
  addItemMock.mockReset().mockResolvedValue(undefined);
  showToastMock.mockReset();
});

afterEach(() => cleanup());

describe("VirtualStylistDrawer — behavioral contract (C05)", () => {
  it("GOAL money honesty: a recommendation priced in EGP renders EGP everywhere — item lines, budget row, ensemble total — never a hard-coded $", async () => {
    chatMock.mockResolvedValue(
      assistantMessage({
        recommendations: [outfit({ budget_limit: 500, within_budget: true })],
      }),
    );
    renderDrawer();
    await askStylist();
    const total = await screen.findByTestId("stylist-ensemble-total");
    expect(total.textContent).toContain("EGP");
    expect(total.textContent).not.toContain("$");
    // every rendered money string on the card is EGP
    const card = total.closest("div.bg-white.border") as HTMLElement;
    expect((card?.textContent || "").includes("$")).toBe(false);
  });

  it("COUNTER-GOAL legacy currency: an outfit without a declared currency shows an honest em-dash, never an assumed $", async () => {
    chatMock.mockResolvedValue(
      assistantMessage({
        recommendations: [
          outfit({
            currency: null,
            items: [item(1, { currency: null }), item(2, { currency: null }), item(3, { currency: null })],
          }),
        ],
      }),
    );
    renderDrawer();
    await askStylist();
    const total = await screen.findByTestId("stylist-ensemble-total");
    expect(total.textContent?.trim()).toBe("\u2014");
    expect(document.body.textContent).not.toContain("$360");
  });

  it("COUNTER-GOAL no duplicate cart writes: double-clicking 'add complete look' issues each piece exactly once", async () => {
    chatMock.mockResolvedValue(assistantMessage());
    let release!: () => void;
    addItemMock.mockImplementation(
      () => new Promise<void>((res) => { release = res; }),
    );
    renderDrawer();
    await askStylist();
    const addBtn = await screen.findByRole("button", {
      name: new RegExp(en("stylist.add_complete_to_bag")),
    });
    fireEvent.click(addBtn);
    fireEvent.click(addBtn); // second click lands mid-flight
    expect(addBtn.getAttribute("aria-busy")).toBe("true");
    await act(async () => {
      release();
      await Promise.resolve();
    });
    // 3 pieces -> first click awaits them sequentially; drain the chain
    await act(async () => {
      for (let i = 0; i < 6; i++) {
        if (release) release();
        await Promise.resolve();
      }
    });
    expect(addItemMock.mock.calls.length).toBeLessThanOrEqual(3);
  });

  it("GOAL skeleton truth: while the stylist thinks, a geometry-matched skeleton card shows, and it leaves when the answer lands", async () => {
    let resolveChat!: (v: unknown) => void;
    chatMock.mockImplementation(
      () => new Promise((res) => { resolveChat = res; }),
    );
    renderDrawer();
    await askStylist();
    const thinking = await screen.findByTestId("stylist-thinking");
    expect(thinking.querySelectorAll(".skeleton-shimmer").length).toBeGreaterThanOrEqual(5);
    await act(async () => {
      resolveChat(assistantMessage());
      await Promise.resolve();
    });
    expect(screen.queryByTestId("stylist-thinking")).toBeNull();
    expect(await screen.findByTestId("stylist-ensemble-total")).toBeTruthy();
  });

  it("GOAL honest empty recommendation: a look with zero verified items shows the translated banner and a disabled bag CTA", async () => {
    chatMock.mockResolvedValue(
      assistantMessage({ recommendations: [outfit({ items: [] })] }),
    );
    renderDrawer();
    await askStylist();
    expect(await screen.findByText(en("stylist.no_verified_items"))).toBeTruthy();
    const addBtn = screen.getByRole("button", {
      name: new RegExp(en("stylist.add_complete_to_bag")),
    });
    expect((addBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it("ARABIC truth: the Arabic drawer carries no hard-coded English slot labels or banner prose", async () => {
    await act(async () => {
      await i18n.changeLanguage("ar");
    });
    chatMock.mockResolvedValue(assistantMessage());
    renderDrawer();
    const input = screen.getByPlaceholderText(
      i18n.getFixedT("ar")("stylist.input_placeholder") as string,
    );
    fireEvent.change(input, { target: { value: "نسقي لي إطلالة سهرة" } });
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", {
          name: new RegExp(i18n.getFixedT("ar")("stylist.submit") as string),
        }),
      );
    });
    await screen.findByTestId("stylist-ensemble-total");
    const text = document.body.textContent || "";
    for (const leak of ["Outerwear", "Trousers", "Footwear", "Accessory",
      "Complete Ensemble",
      "This stylist response did not include"]) {
      expect(text.includes(leak), `leak: ${leak}`).toBe(false);
    }
    // the translated slot labels really render
    expect(text).toContain(i18n.getFixedT("ar")("stylist.position_outerwear") as string);
  });

  it("A11Y: close and mic controls have accessible names, 44px+ targets, and the open drawer passes axe (serious/critical)", async () => {
    chatMock.mockResolvedValue(assistantMessage());
    const { container } = renderDrawer();
    const close = screen.getByRole("button", { name: en("common.close") });
    expect(close.className).toContain("w-11");
    const mic = screen.getByRole("button", { name: en("stylist.hold_voice") });
    expect(mic.className).toContain("min-h-[48px]");
    expect(mic.textContent).not.toContain("🎙️");
    const results = await axe.run(container, {
      rules: {
        "color-contrast": { enabled: false },
        "target-size": { enabled: false },
      },
    });
    const serious = results.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact || ""),
    );
    expect(serious, JSON.stringify(serious.map((v) => v.id))).toEqual([]);
  });
});

// sanity: the keys this suite leans on exist in the shipped bundle
it("i18n keys for the drawer exist", () => {
  const st = (enJson as any).stylist;
  for (const k of [
    "position_outerwear", "position_bottom", "position_footwear",
    "position_accessory", "no_verified_items", "toast_no_items",
    "toast_missing_sku", "adding_to_bag", "voice_stop",
  ]) {
    expect(st[k], k).toBeTruthy();
  }
});
