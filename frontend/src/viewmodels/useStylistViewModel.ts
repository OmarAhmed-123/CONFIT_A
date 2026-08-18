import { useState, useCallback } from 'react';
import { stylistService } from '../services/apiServices';
import { StylistMessage, Outfit } from '../models';
import { useCartStore } from '../stores/cartStore';
import { useUIStore } from '../stores/uiStore';

export function useStylistViewModel() {
  const [messages, setMessages] = useState<StylistMessage[]>([]);
  const [inputPrompt, setInputPrompt] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const simulateVoiceInput = useCallback(() => {
    setIsRecording(true);
    setTimeout(() => {
      setIsRecording(false);
      setInputPrompt('Find me a quiet luxury evening outfit for an art opening under $350');
      sendPrompt('Find me a quiet luxury evening outfit for an art opening under $350', 'Evening & Party', 350);
    }, 2500);
  }, [sendPrompt]);

  const addCompleteLookToCart = useCallback(async (outfit: Outfit) => {
    try {
      for (const it of outfit.items) {
        if (it.sku_id) {
          await addItem(it.sku_id, { id: it.product_id, title: it.product_title, category: it.category_name, color: it.color_hex });
        }
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
    simulateVoiceInput,
    addCompleteLookToCart,
  };
}
