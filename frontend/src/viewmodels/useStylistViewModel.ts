import { msg, detail, translatableFrom, type TranslatableMessage } from '../i18n/messages';
import { apiErrorDescriptor, isRetryable } from '../i18n/apiErrors';
import { useState, useCallback, useRef } from "react";
import { stylistService } from "../services/apiServices";
import { StylistMessage, Outfit } from "../models";
import { useCartStore } from "../stores/cartStore";
import {
  validateStylistImage,
  prepareStylistImage,
  type StylistAttachError,
} from "../components/stylist/stylistImageAttach";
import { useUIStore } from "../stores/uiStore";

// Minimal typing for the Web Speech API (not in default TS DOM lib).
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: (e: any) => void;
  onerror: (e: any) => void;
  onend: () => void;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

/** What went wrong with voice input, from the browser's SpeechRecognition error code. */
export type VoiceFailure =
  | "permission"
  | "no_device"
  | "network"
  | "no_speech"
  | "service_blocked"
  | "aborted"
  | "unknown";

/**
 * Map a SpeechRecognition error code to what actually happened. Only
 * `not-allowed` is a permission problem. `service-not-allowed` means the
 * browser's speech service is blocked, which is a different fix, so it has its
 * own message rather than being reported as a denied microphone.
 */
export function classifySpeechError(code?: string): VoiceFailure {
  switch (code) {
    case "not-allowed":
      return "permission";
    case "audio-capture":
      return "no_device";
    case "network":
      return "network";
    case "no-speech":
      return "no_speech";
    case "service-not-allowed":
      return "service_blocked";
    case "aborted":
      return "aborted";
    default:
      return "unknown";
  }
}

const VOICE_FAILURE_MESSAGE: Record<Exclude<VoiceFailure, "aborted">, string> = {
  permission: "stylist.voice_permission_denied",
  no_device: "stylist.voice_no_device",
  network: "stylist.voice_network",
  no_speech: "stylist.voice_no_speech",
  service_blocked: "stylist.voice_service_blocked",
  unknown: "stylist.voice_error",
};

export function useStylistViewModel() {
  const [messages, setMessages] = useState<StylistMessage[]>([]);
  const [inputPrompt, setInputPrompt] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  // Synchronous duplicate-submit guard. `isTyping` is state, so two submits in the
  // same tick (double Enter, double click) would both pass a state check.
  const inFlightRef = useRef(false);
  const [isRecording, setIsRecording] = useState(false);
  // The failure the shopper sees is a KEY, resolved at the render boundary — a view
  // model has no i18n context, and the previous code put the raw transport string on
  // screen: the Arabic drawer showed `Request failed with status 500`. The technical
  // detail still goes to the console, where an engineer can read it and a shopper
  // never can.
  const [error, setError] = useState<TranslatableMessage | null>(null);
  //: Whether offering "Retry" is honest for the current failure.
  const [errorRetryable, setErrorRetryable] = useState(true);
  // COUNTER-GOAL guard: adding a multi-piece look issues one cart write per
  // piece; a double-click mid-flight would duplicate every piece. One
  // in-flight add at a time, surfaced so the CTA can show a real busy state.
  const [isAddingLook, setIsAddingLook] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  // Read by sendPrompt through refs, not closures. A voice transcript is sent from
  // the recognition `onend` handler, which keeps the sendPrompt of the render that
  // STARTED recording: without refs its history and voice flag were stale.
  const messagesRef = useRef<StylistMessage[]>([]);
  messagesRef.current = messages;
  const voiceTurnRef = useRef(false);

  const { addItem, openCart } = useCartStore();
  const { showToast } = useUIStore();

  // Mode A: photos the shopper attached to the next message (data URIs).
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [attachError, setAttachError] = useState<StylistAttachError | null>(null);

  const addImages = useCallback(async (files: File[]) => {
    let next = [...pendingImages];
    let firstError: StylistAttachError | null = null;
    for (const file of files) {
      const problem = validateStylistImage(file, next.length);
      if (problem) {
        firstError = firstError ?? problem;
        continue;
      }
      // Reduced in the browser to the 1 MB per-image contract the backend enforces.
      const prepared = await prepareStylistImage(file);
      if ("error" in prepared) {
        firstError = firstError ?? prepared.error;
        continue;
      }
      next = [...next, prepared.dataUrl];
    }
    setPendingImages(next);
    setAttachError(firstError);
  }, [pendingImages]);

  const removeImage = useCallback((index: number) => {
    setPendingImages((prev) => prev.filter((_, i) => i !== index));
    setAttachError(null);
  }, []);

  const sendPrompt = useCallback(
    async (
      promptText?: string,
      occasion?: string,
      budget?: number,
      recommendationConstraints?: {
        palette?: string;
        avoid_palette?: string;
        preferred_fit?: string;
        size_tops?: string;
        size_bottoms?: string;
        size_shoes?: string;
      },
      // What the shopper sees in their own message bubble. The REQUEST text is
      // English by contract (the backend parses English occasion/material
      // keywords), but echoing that contract value back into an Arabic transcript
      // showed an Arabic shopper their own request in English. Value -> API,
      // label -> screen.
      displayText?: string,
    ) => {
      const textToSend = promptText || inputPrompt;
      if (!textToSend.trim()) return;
      if (inFlightRef.current) return;
      inFlightRef.current = true;

      const userMsg: StylistMessage = {
        id: Date.now(),
        session_id: 1,
        sender: "user",
        content: displayText || textToSend,
        recommendations: [],
        created_at: new Date().toISOString(),
      };

      const imagesToSend = pendingImages;
      // A failed request must not cost the shopper their words or photos.
      const restoreDraft = () => {
        setInputPrompt((prev) => (prev.trim() ? prev : textToSend));
        setPendingImages((prev) => (prev.length ? prev : imagesToSend));
      };
      const usedVoice = voiceTurnRef.current;
      voiceTurnRef.current = false;
      // The earlier turns of this chat travel with the request, so a follow-up
      // ("and the shoes?") is answered in context. Text only, bounded to the
      // last 8 turns; the server re-bounds it. Before this, every turn was a new
      // backend session and the model saw none of the conversation.
      const historyToSend = messagesRef.current
        .filter((m) => (m.sender === "user" || m.sender === "assistant") && String(m.content ?? "").trim())
        .slice(-8)
        .map((m) => ({ role: m.sender as "user" | "assistant", content: String(m.content).slice(0, 1200) }));
      setMessages((prev) => [...prev, userMsg]);
      setInputPrompt("");
      setPendingImages([]);
      setAttachError(null);
      setIsTyping(true);
      setError(null);
      setErrorRetryable(true);

      try {
        const response = await stylistService.chat({
          prompt: textToSend,
          occasion,
          budget_limit: budget,
          voice_input_used: usedVoice,
          ...(imagesToSend.length ? { images: imagesToSend } : {}),
          recommendation_constraints: recommendationConstraints,
          ...(historyToSend.length ? { history: historyToSend } : {}),
        });

        // D-4 §14 (empty response). An answer with no usable text must not be
        // appended as an empty bubble — that looks like a silent failure and is
        // not an answer. Nothing the shopper did caused it, so it is retryable and
        // reuses the same contract as a transport failure: a localizable sentence,
        // a stable code, and the Retry affordance.
        if (!String((response as any)?.content ?? "").trim()) {
          setError({ key: "errors.empty_answer" });
          setErrorRetryable(true);
          setIsTyping(false);
          restoreDraft();
          showToast(msg("stylist.error_toast"), "error");
          return;
        }

        setMessages((prev) => [...prev, response]);
        setIsTyping(false);
      } catch (err: any) {
        // eslint-disable-next-line no-console
        console.error("[stylist] request failed:", err?.code ?? "", err?.message ?? err);
        // A KNOWN code gets its own sentence; anything else gets the generic one.
        // The technical detail goes to the console (above) so an engineer can read
        // it and a shopper never sees a status line.
        setError(apiErrorDescriptor(err));
        setErrorRetryable(isRetryable(err));
        setIsTyping(false);
        restoreDraft();
        showToast(msg("stylist.error_toast"), "error");
      } finally {
        inFlightRef.current = false;
      }
    },
    [inputPrompt, showToast, pendingImages],
  );

  // Real voice input via the browser SpeechRecognition (Web Speech) pipeline:
  // Microphone -> permission -> live transcript -> intent -> styling engine.
  // No simulated/canned transcription. Gracefully reports when unsupported.
  const startVoiceInput = useCallback(() => {
    if (isRecording) {
      recognitionRef.current?.stop();
      return;
    }
    const w = window as any;
    const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SR) {
      showToast(msg("stylist.voice_unsupported"), "error");
      return;
    }
    const rec: SpeechRecognitionLike = new SR();
    recognitionRef.current = rec;
    rec.lang =
      (typeof navigator !== "undefined" && navigator.language) || "en-US";
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    let finalTranscript = "";
    let voiceFailed = false;
    rec.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const transcript = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalTranscript += transcript;
        else interim += transcript;
      }
      setInputPrompt((finalTranscript + " " + interim).trim());
    };
    rec.onerror = (e: any) => {
      setIsRecording(false);
      voiceFailed = true;
      voiceTurnRef.current = false;
      const kind = classifySpeechError(e?.error);
      if (kind === "aborted") return; // the shopper cancelled; nothing to report
      // eslint-disable-next-line no-console
      console.error("[stylist] voice recognition error:", e?.error);
      showToast(msg(VOICE_FAILURE_MESSAGE[kind]), "error");
    };
    rec.onend = () => {
      setIsRecording(false);
      const text = finalTranscript.trim();
      if (text) {
        sendPrompt(text);
      } else {
        voiceTurnRef.current = false;
      }
      if (!text && !voiceFailed) {
        // Ended cleanly with nothing recognised: say so, instead of doing nothing.
        showToast(msg(VOICE_FAILURE_MESSAGE.no_speech), "error");
      }
    };

    try {
      setInputPrompt("");
      setIsRecording(true);
      voiceTurnRef.current = true;
      rec.start();
    } catch (err: any) {
      setIsRecording(false);
      // eslint-disable-next-line no-console
      console.error("[stylist] voice start failed:", err?.message ?? err);
      showToast(translatableFrom(err, "stylist.voice_start_failed"), "error");
    }
  }, [isRecording, sendPrompt, showToast]);

  const addCompleteLookToCart = useCallback(
    async (outfit: Outfit) => {
      if (isAddingLook) return;
      try {
        const itemsToAdd = outfit.items || [];
        if (itemsToAdd.length === 0) {
          // Keys, not raw English: the Arabic drawer showed this sentence
          // untranslated.
          showToast(msg("stylist.toast_no_items"), "error");
          return;
        }

        const missingSku = itemsToAdd.find((it) => !it.sku_id);
        if (missingSku) {
          showToast(msg("stylist.toast_missing_sku"), "error");
          return;
        }
        setIsAddingLook(true);

        for (const it of itemsToAdd) {
          await addItem(
            it.sku_id!,
            {
              id: it.product_id,
              title: it.product_title,
              category: it.category_name,
              color: it.color_hex || "Midnight Navy",
            },
            1,
            outfit.id,
          );
        }
        showToast(msg('toast.ensemble_added', { title: outfit.title }), "success");
        openCart();
      } catch (err: any) {
        showToast(msg('toast.add_all_failed', { reason: detail(err) }), "error");
      } finally {
        setIsAddingLook(false);
      }
    },
    [addItem, openCart, showToast, isAddingLook],
  );

  return {
    messages,
    inputPrompt,
    setInputPrompt,
    isTyping,
    isRecording,
    error,
    errorRetryable,
    isAddingLook,
    sendPrompt,
    pendingImages,
    attachError,
    addImages,
    removeImage,
    startVoiceInput,
    addCompleteLookToCart,
  };
}
