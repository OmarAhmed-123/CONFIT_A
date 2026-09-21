import { msg, detail } from '../i18n/messages';
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
  const [error, setError] = useState<string | null>(null);
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
    ) => {
      const textToSend = promptText || inputPrompt;
      if (!textToSend.trim()) return;

      const userMsg: StylistMessage = {
        id: Date.now(),
        session_id: 1,
        sender: "user",
        content: textToSend,
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
        setError(err.message || "Stylist service momentarily unavailable");
        setIsTyping(false);
        showToast(
          "Stylist error: " + (err.message || "Check connection"),
          "error",
        );
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
      showToast(
        "Voice input is not supported in this browser. Please type your request.",
        "error",
      );
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
        showToast(
          "Microphone permission denied. Enable mic access to use voice styling.",
          "error",
        );
      } else if (e?.error !== "aborted") {
        showToast(
          "Voice recognition error: " + (e?.error || "unknown"),
          "error",
        );
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
      showToast(
        "Could not start voice input: " + (err?.message || "unknown"),
        "error",
      );
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
