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
    simulateVoiceInput,
    addCompleteLookToCart,
  };
}
