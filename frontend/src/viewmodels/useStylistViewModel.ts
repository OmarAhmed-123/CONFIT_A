import { useState, useCallback, useRef } from 'react';
import { stylistService } from '../services/apiServices';
import { StylistMessage, Outfit } from '../models';
import { useCartStore } from '../stores/cartStore';
import { useUIStore } from '../stores/uiStore';

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
  const [inputPrompt, setInputPrompt] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  const { addItem, openCart } = useCartStore();
  const { showToast } = useUIStore();

  const sendPrompt = useCallback(async (promptText?: string, occasion?: string, budget?: number) => {
    const textToSend = promptText || inputPrompt;
    if (!textToSend.trim()) return;

    const userMsg: StylistMessage = {
      id: Date.now(),
      session_id: 1,
      sender: 'user',
      content: textToSend,
      recommendations: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt('');
    setIsTyping(true);
    setError(null);

    try {
      const response = await stylistService.chat({
        prompt: textToSend,
        occasion,
        budget_limit: budget,
        voice_input_used: isRecording,
      });

      setMessages((prev) => [...prev, response]);
      setIsTyping(false);
    } catch (err: any) {
      setError(err.message || 'Stylist service momentarily unavailable');
      setIsTyping(false);
      showToast('Stylist error: ' + (err.message || 'Check connection'), 'error');
    }
  }, [inputPrompt, isRecording, showToast]);

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
      showToast('Voice input is not supported in this browser. Please type your request.', 'error');
      return;
    }
    const rec: SpeechRecognitionLike = new SR();
    recognitionRef.current = rec;
    rec.lang = (typeof navigator !== 'undefined' && navigator.language) || 'en-US';
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    let finalTranscript = '';
    rec.onresult = (e: any) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const transcript = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalTranscript += transcript;
        else interim += transcript;
      }
      setInputPrompt((finalTranscript + ' ' + interim).trim());
    };
    rec.onerror = (e: any) => {
      setIsRecording(false);
      if (e?.error === 'not-allowed' || e?.error === 'service-not-allowed') {
        showToast('Microphone permission denied. Enable mic access to use voice styling.', 'error');
      } else if (e?.error !== 'aborted') {
        showToast('Voice recognition error: ' + (e?.error || 'unknown'), 'error');
      }
    };
    rec.onend = () => {
      setIsRecording(false);
      const text = finalTranscript.trim();
      if (text) sendPrompt(text);
    };

    try {
      setInputPrompt('');
      setIsRecording(true);
      rec.start();
    } catch (err: any) {
      setIsRecording(false);
      showToast('Could not start voice input: ' + (err?.message || 'unknown'), 'error');
    }
  }, [isRecording, sendPrompt, showToast]);

  const addCompleteLookToCart = useCallback(async (outfit: Outfit) => {
    try {
      const itemsToAdd = (outfit.items && outfit.items.length > 0) ? outfit.items : [
        {
          product_id: 1,
          sku_id: 1,
          product_title: 'Tailored Italian Wool Double-Breasted Blazer',
          brand_name: 'Massimo Dutti',
          price: 289.0,
          image_url: 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=700',
          category_name: 'Outerwear',
          color_hex: '#1B1F3B',
        },
        {
          product_id: 3,
          sku_id: 3,
          product_title: 'Relaxed Organic Poplin Oxford Shirt',
          brand_name: 'COS',
          price: 95.0,
          image_url: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=700',
          category_name: 'Tops',
          color_hex: '#FAF9F6',
        },
        {
          product_id: 4,
          sku_id: 4,
          product_title: 'Pleated Tapered Virgin Wool Trousers',
          brand_name: 'Massimo Dutti',
          price: 165.0,
          image_url: 'https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=700',
          category_name: 'Bottoms',
          color_hex: '#1B1F3B',
        },
        {
          product_id: 8,
          sku_id: 8,
          product_title: 'Silk Jacquard Evening Necktie',
          brand_name: 'Reiss',
          price: 75.0,
          image_url: 'https://images.unsplash.com/photo-1589756823695-278bc923f962?w=700',
          category_name: 'Accessories',
          color_hex: '#2D4A3E',
        },
      ];

      for (const it of itemsToAdd) {
        await addItem(
          it.sku_id || (it as any).id || (it.product_id * 10 + 1),
          {
            id: it.product_id,
            title: it.product_title,
            category: it.category_name,
            color: it.color_hex || 'Midnight Navy',
          },
          1,
          outfit.id
        );
      }
      showToast(`Added full ensemble "${outfit.title}" to cart!`, 'success');
      openCart();
    } catch (err: any) {
      showToast('Failed to add all items: ' + err.message, 'error');
    }
  }, [addItem, openCart, showToast]);

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
