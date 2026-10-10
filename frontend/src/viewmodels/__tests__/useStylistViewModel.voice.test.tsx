/**
 * Voice styling and follow-up context, at the view-model boundary.
 *
 * SIMULATED: the browser's SpeechRecognition is replaced by a fake that the test
 * drives (fires onresult / onerror / onend). This proves what the app does with
 * each browser outcome. It does NOT prove that a real microphone works; that is
 * a separate, manual check on the deployed HTTPS origin.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

const chat = vi.fn();
const showToast = vi.fn();

vi.mock("../../services/apiServices", () => ({
  stylistService: { chat: (...args: unknown[]) => chat(...args) },
}));
vi.mock("../../stores/uiStore", () => ({
  useUIStore: () => ({ showToast }),
}));
vi.mock("../../stores/cartStore", () => ({
  useCartStore: () => ({ addItem: vi.fn(), openCart: vi.fn() }),
}));

import { useStylistViewModel, classifySpeechError } from "../useStylistViewModel";

/** Fake SpeechRecognition: the test decides what the browser reports. */
class FakeRecognition {
  static last: FakeRecognition | null = null;
  lang = "";
  interimResults = false;
  maxAlternatives = 1;
  onresult: (e: any) => void = () => {};
  onerror: (e: any) => void = () => {};
  onend: () => void = () => {};
  started = false;
  start() {
    this.started = true;
    FakeRecognition.last = this;
  }
  stop() {
    this.onend();
  }
  abort() {
    this.onend();
  }
}

const shownKeys = () => showToast.mock.calls.map((c) => (c[0] as { key: string }).key);

beforeEach(() => {
  chat.mockReset();
  showToast.mockReset();
  (window as any).SpeechRecognition = FakeRecognition;
  FakeRecognition.last = null;
});

afterEach(() => {
  delete (window as any).SpeechRecognition;
});

describe("classifySpeechError", () => {
  it.each([
    ["not-allowed", "permission"],
    ["audio-capture", "no_device"],
    ["network", "network"],
    ["no-speech", "no_speech"],
    ["service-not-allowed", "service_blocked"],
    ["aborted", "aborted"],
    ["something-new", "unknown"],
    [undefined, "unknown"],
  ])("maps %s to %s", (code, expected) => {
    expect(classifySpeechError(code)).toBe(expected);
  });

  it("never reports service-not-allowed as a denied microphone", () => {
    expect(classifySpeechError("service-not-allowed")).not.toBe("permission");
  });
});

describe("voice input outcomes (simulated browser)", () => {
  it("reports a denied permission with the permission message and sends nothing", () => {
    const { result } = renderHook(() => useStylistViewModel());
    act(() => result.current.startVoiceInput());
    act(() => FakeRecognition.last!.onerror({ error: "not-allowed" }));
    act(() => FakeRecognition.last!.onend());
    expect(shownKeys()).toEqual(["stylist.voice_permission_denied"]);
    expect(chat).not.toHaveBeenCalled();
  });

  it("reports a blocked speech service as that, not as a denied microphone", () => {
    const { result } = renderHook(() => useStylistViewModel());
    act(() => result.current.startVoiceInput());
    act(() => FakeRecognition.last!.onerror({ error: "service-not-allowed" }));
    expect(shownKeys()).toEqual(["stylist.voice_service_blocked"]);
  });

  it("reports a missing microphone", () => {
    const { result } = renderHook(() => useStylistViewModel());
    act(() => result.current.startVoiceInput());
    act(() => FakeRecognition.last!.onerror({ error: "audio-capture" }));
    expect(shownKeys()).toEqual(["stylist.voice_no_device"]);
  });

  it("reports a network failure", () => {
    const { result } = renderHook(() => useStylistViewModel());
    act(() => result.current.startVoiceInput());
    act(() => FakeRecognition.last!.onerror({ error: "network" }));
    expect(shownKeys()).toEqual(["stylist.voice_network"]);
  });

  it("stays silent when the shopper cancels", () => {
    const { result } = renderHook(() => useStylistViewModel());
    act(() => result.current.startVoiceInput());
    act(() => FakeRecognition.last!.onerror({ error: "aborted" }));
    act(() => FakeRecognition.last!.onend());
    expect(showToast).not.toHaveBeenCalled();
  });

  it("says so when recording ends with nothing heard", () => {
    const { result } = renderHook(() => useStylistViewModel());
    act(() => result.current.startVoiceInput());
    act(() => FakeRecognition.last!.onend());
    expect(shownKeys()).toEqual(["stylist.voice_no_speech"]);
    expect(chat).not.toHaveBeenCalled();
  });

  it("submits the transcript through the same chat path as typed text", async () => {
    chat.mockResolvedValue({ id: 1, sender: "assistant", content: "An answer", recommendations: [] });
    const { result } = renderHook(() => useStylistViewModel());
    act(() => result.current.startVoiceInput());
    act(() =>
      FakeRecognition.last!.onresult({
        resultIndex: 0,
        results: [{ 0: { transcript: "a navy look for work" }, isFinal: true }],
      }),
    );
    await act(async () => FakeRecognition.last!.onend());
    expect(chat).toHaveBeenCalledTimes(1);
    expect(chat.mock.calls[0][0]).toMatchObject({ prompt: "a navy look for work", voice_input_used: true });
  });
});

describe("follow-up context", () => {
  it("sends the earlier turns with a follow-up question", async () => {
    chat
      .mockResolvedValueOnce({ id: 1, sender: "assistant", content: "A navy blazer look.", recommendations: [] })
      .mockResolvedValueOnce({ id: 2, sender: "assistant", content: "Brown suede suits it.", recommendations: [] });
    const { result } = renderHook(() => useStylistViewModel());

    await act(async () => {
      await result.current.sendPrompt("Build a navy smart casual look.");
    });
    await act(async () => {
      await result.current.sendPrompt("Which shoe colour suits it?");
    });

    const second = chat.mock.calls[1][0];
    expect(second.prompt).toBe("Which shoe colour suits it?");
    expect(second.history).toEqual([
      { role: "user", content: "Build a navy smart casual look." },
      { role: "assistant", content: "A navy blazer look." },
    ]);
  });

  it("does not send history on the first message", async () => {
    chat.mockResolvedValue({ id: 1, sender: "assistant", content: "An answer", recommendations: [] });
    const { result } = renderHook(() => useStylistViewModel());
    await act(async () => {
      await result.current.sendPrompt("A weekend look");
    });
    expect(chat.mock.calls[0][0]).not.toHaveProperty("history");
  });
});
