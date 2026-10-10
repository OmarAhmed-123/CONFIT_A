/**
 * StyleList composer: multiline input, keyboard submit, duplicate guard, draft
 * restore on failure, and the honest footer for a grounding-rejected answer.
 *
 * Runs in jsdom with the chat service mocked (no network, no provider call).
 * What it does NOT prove: real-browser layout (wrapping, auto-grow height,
 * scroll), IME behaviour on a real device, or real provider answers. Those are
 * covered by the browser gate and the manual checks recorded in the PR.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, cleanup, waitFor } from "@testing-library/react";
import i18n from "../../../i18n/i18n";
import { VirtualStylistDrawer } from "../VirtualStylistDrawer";

const { chatMock, showToastMock } = vi.hoisted(() => ({
  chatMock: vi.fn(),
  showToastMock: vi.fn(),
}));

vi.mock("../../../services/apiServices", async (importOriginal) => {
  const actual: any = await importOriginal();
  return {
    ...actual,
    stylistService: { ...actual.stylistService, chat: chatMock, saveOutfit: vi.fn() },
  };
});

vi.mock("../../../stores/cartStore", () => ({
  useCartStore: () => ({ addItem: vi.fn(), openCart: vi.fn() }),
}));

vi.mock("../../../stores/uiStore", () => ({
  useUIStore: () => ({
    isStylistDrawerOpen: true,
    closeStylist: vi.fn(),
    stylistPrefillOccasion: null,
    openTryOn: vi.fn(),
    openRuler: vi.fn(),
    showToast: showToastMock,
  }),
}));

vi.mock("../../../hooks/useTryOnAvailability", () => ({
  useTryOnAvailability: () => ({ ctaKind: () => "try_on", userMessage: null }),
}));

const en = (key: string) => i18n.getFixedT("en")(key) as string;

function renderDrawer() {
  render(<VirtualStylistDrawer />);
  return screen.getByRole("textbox", { name: en("stylist.input_label") }) as HTMLTextAreaElement;
}

beforeEach(() => {
  chatMock.mockReset();
  showToastMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("composer is a multiline textarea", () => {
  it("renders a textarea with auto text direction (Arabic and English)", () => {
    const box = renderDrawer();
    expect(box.tagName).toBe("TEXTAREA");
    expect(box.getAttribute("dir")).toBe("auto");
  });

  it("Enter inserts a newline and does not submit", () => {
    const box = renderDrawer();
    fireEvent.change(box, { target: { value: "Paragraph one" } });
    fireEvent.keyDown(box, { key: "Enter", code: "Enter" });
    expect(chatMock).not.toHaveBeenCalled();
    // jsdom does not insert the newline for us; the key handler must not block it.
    expect(box.value).toBe("Paragraph one");
  });

  it("Ctrl+Enter submits and the newlines reach the request unchanged", async () => {
    chatMock.mockResolvedValue({ id: 2, sender: "assistant", content: "ok", recommendations: [] });
    const box = renderDrawer();
    const text = "الجملة الأولى للطلب.\n\nالفقرة الثانية: قميص أبيض وبنطلون كحلي.\nEnglish line 3.";
    fireEvent.change(box, { target: { value: text } });
    await act(async () => {
      fireEvent.keyDown(box, { key: "Enter", code: "Enter", ctrlKey: true });
    });
    await waitFor(() => expect(chatMock).toHaveBeenCalledTimes(1));
    expect(chatMock.mock.calls[0][0].prompt).toBe(text);
  });

  it("Cmd+Enter (Mac) also submits", async () => {
    chatMock.mockResolvedValue({ id: 2, sender: "assistant", content: "ok", recommendations: [] });
    const box = renderDrawer();
    fireEvent.change(box, { target: { value: "A casual weekend look" } });
    await act(async () => {
      fireEvent.keyDown(box, { key: "Enter", code: "Enter", metaKey: true });
    });
    await waitFor(() => expect(chatMock).toHaveBeenCalledTimes(1));
  });

  it("does not send an empty or whitespace-only draft", () => {
    const box = renderDrawer();
    fireEvent.change(box, { target: { value: "   \n  " } });
    fireEvent.keyDown(box, { key: "Enter", code: "Enter", ctrlKey: true });
    expect(chatMock).not.toHaveBeenCalled();
  });
});

describe("duplicate-submit guard and draft preservation", () => {
  it("two submits in the same tick produce one request", async () => {
    let release: (v: unknown) => void = () => {};
    chatMock.mockReturnValue(new Promise((resolve) => (release = resolve)));
    const box = renderDrawer();
    fireEvent.change(box, { target: { value: "Work outfit please" } });
    await act(async () => {
      fireEvent.keyDown(box, { key: "Enter", code: "Enter", ctrlKey: true });
      fireEvent.keyDown(box, { key: "Enter", code: "Enter", ctrlKey: true });
    });
    expect(chatMock).toHaveBeenCalledTimes(1);
    await act(async () => release({ id: 3, sender: "assistant", content: "done", recommendations: [] }));
  });

  it("a failed request gives the draft back to the composer", async () => {
    chatMock.mockRejectedValue(new Error("network down"));
    const box = renderDrawer();
    const text = "Line one\nLine two that must survive a failed send.";
    fireEvent.change(box, { target: { value: text } });
    await act(async () => {
      fireEvent.keyDown(box, { key: "Enter", code: "Enter", ctrlKey: true });
    });
    await waitFor(() => expect(showToastMock).toHaveBeenCalled());
    expect(box.value).toBe(text);
  });

  it("the submit button shows a busy state while the request is in flight", async () => {
    let release: (v: unknown) => void = () => {};
    chatMock.mockReturnValue(new Promise((resolve) => (release = resolve)));
    const box = renderDrawer();
    fireEvent.change(box, { target: { value: "Something" } });
    await act(async () => {
      fireEvent.keyDown(box, { key: "Enter", code: "Enter", ctrlKey: true });
    });
    const button = document.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.textContent).toContain(en("stylist.sending"));
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(button.disabled).toBe(true);
    await act(async () => release({ id: 4, sender: "assistant", content: "done", recommendations: [] }));
  });
});

describe("footer states the true answer source", () => {
  it("a grounding-rejected answer is NOT described as a provider outage", async () => {
    chatMock.mockResolvedValue({
      id: 5,
      sender: "assistant",
      content: "Grounded description of the looks shown.",
      engine: "CONFIT Grounded Styling Engine (Grounded & Resilient)",
      answer_source: "grounding_rejected",
      recommendations: [],
    });
    const box = renderDrawer();
    fireEvent.change(box, { target: { value: "Build me a look" } });
    await act(async () => {
      fireEvent.keyDown(box, { key: "Enter", code: "Enter", ctrlKey: true });
    });
    const footer = await screen.findByText(en("stylist.engine_rejected"));
    expect(footer.textContent).not.toContain("provider was unavailable");
  });

  it("a real provider answer keeps the provider footer", async () => {
    chatMock.mockResolvedValue({
      id: 6,
      sender: "assistant",
      content: "A navy blazer with brown shoes.",
      engine: "NVIDIA nvidia/nemotron-3-super-120b-a12b",
      answer_source: "provider",
      recommendations: [],
    });
    const box = renderDrawer();
    fireEvent.change(box, { target: { value: "Shoe colour?" } });
    await act(async () => {
      fireEvent.keyDown(box, { key: "Enter", code: "Enter", ctrlKey: true });
    });
    expect(await screen.findByText(en("stylist.engine_provider").replace("{{engine}}", "NVIDIA nvidia/nemotron-3-super-120b-a12b"))).toBeTruthy();
  });
});
