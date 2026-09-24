import { msg, detail, translatableFrom, type TranslatableMessage } from '../i18n/messages';
import { useState, useCallback, useRef } from "react";
import { stylistService } from "../services/apiServices";
import { StylistMessage, Outfit } from "../models";
import { useCartStore } from "../stores/cartStore";
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

export function useStylistViewModel() {
  const [messages, setMessages] = useState<StylistMessage[]>([]);
  const [inputPrompt, setInputPrompt] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  // The failure the shopper sees is a KEY, resolved at the render boundary — a view
  // model has no i18n context, and the previous code put the raw transport string on
  // screen: the Arabic drawer showed `Request failed with status 500`. The technical
  // detail still goes to the console, where an engineer can read it and a shopper
  // never can.
  const [error, setError] = useState<TranslatableMessage | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  const { addItem, openCart } = useCartStore();
  const { showToast } = useUIStore();

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

      const userMsg: StylistMessage = {
        id: Date.now(),
        session_id: 1,
        sender: "user",
        content: displayText || textToSend,
        recommendations: [],
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setInputPrompt("");
      setIsTyping(true);
      setError(null);

      try {
        const response = await stylistService.chat({
          prompt: textToSend,
          occasion,
          budget_limit: budget,
          voice_input_used: isRecording,
          recommendation_constraints: recommendationConstraints,
        });

        setMessages((prev) => [...prev, response]);
        setIsTyping(false);
      } catch (err: any) {
        // eslint-disable-next-line no-console
        console.error("[stylist] request failed:", err?.code ?? "", err?.message ?? err);
        setError(msg("stylist.error_unavailable"));
        setIsTyping(false);
        showToast(msg("stylist.error_toast"), "error");
      }
    },
    [inputPrompt, isRecording, showToast],
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
      if (e?.error === "not-allowed" || e?.error === "service-not-allowed") {
        showToast(msg("stylist.voice_permission_denied"), "error");
      } else if (e?.error !== "aborted") {
        // eslint-disable-next-line no-console
        console.error("[stylist] voice recognition error:", e?.error);
        showToast(msg("stylist.voice_error"), "error");
      }
    };
    rec.onend = () => {
      setIsRecording(false);
      const text = finalTranscript.trim();
      if (text) sendPrompt(text);
    };

    try {
      setInputPrompt("");
      setIsRecording(true);
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
      try {
        const itemsToAdd = outfit.items || [];
        if (itemsToAdd.length === 0) {
          showToast(
            "This stylist look has no verified catalog items to add yet. Open a product detail page or ask for another recommendation.",
            "error",
          );
          return;
        }

        const missingSku = itemsToAdd.find((it) => !it.sku_id);
        if (missingSku) {
          showToast(
            "This stylist look is missing verified SKU data, so it cannot be added to bag yet.",
            "error",
          );
          return;
        }

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
      }
    },
    [addItem, openCart, showToast],
  );

  return {
    messages,
    inputPrompt,
    setInputPrompt,
    isTyping,
    isRecording,
    error,
    sendPrompt,
    startVoiceInput,
    addCompleteLookToCart,
  };
}
