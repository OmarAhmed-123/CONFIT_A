import { create } from 'zustand';
import { Cart } from '../models';
import { commerceService, wardrobeService } from '../services/apiServices';
import { getAuthToken } from '../services/apiClient';

interface CartState {
  cart: Cart | null;
  isOpen: boolean;
  isLoading: boolean;
  pendingDuplicateAlert: {
    product_sku_id: number;
    quantity: number;
    owned_item: any;
    alert_message: string;
  } | null;
  openCart: () => void;
  closeCart: () => void;
  fetchCart: () => Promise<void>;
  addItem: (productSkuId: number, productInfo?: { id: number; title: string; category: string; color: string }, quantity?: number, outfitId?: number) => Promise<void>;
  confirmAddDuplicate: () => Promise<void>;
  dismissDuplicate: () => void;
  updateQuantity: (cartItemId: number, quantity: number) => Promise<void>;
  removeItem: (cartItemId: number) => Promise<void>;
}

export const useCartStore = create<CartState>((set, get) => ({
  cart: null,
  isOpen: false,
  isLoading: false,
  pendingDuplicateAlert: null,

  openCart: () => set({ isOpen: true }),
  closeCart: () => set({ isOpen: false }),

  fetchCart: async () => {
    try {
      const cart = await commerceService.getCart();
      set({ cart });
    } catch (err) {
      console.error('Failed to load cart', err);
    }
  },

  addItem: async (productSkuId, productInfo, quantity = 1, outfitId) => {
    set({ isLoading: true });
    try {
      // Check duplicate alert only if user is logged in (has an active digital wardrobe)
      if (productInfo && getAuthToken()) {
        try {
          const dupRes = await wardrobeService.checkDuplicate({
            product_id: productInfo.id,
            product_title: productInfo.title,
            category: productInfo.category,
            color_family: productInfo.color,
            strict_mode: true,
          });

          if (dupRes.has_duplicate_risk && dupRes.owned_item) {
            set({
              isLoading: false,
              pendingDuplicateAlert: {
                product_sku_id: productSkuId,
                quantity,
                owned_item: dupRes.owned_item,
                alert_message: dupRes.alert_message || 'You own a similar piece!',
              },
            });
            return;
          }
        } catch (e) {
          // If check fails or guest, proceed directly
        }
      }

      const cart = await commerceService.addToCart(productSkuId, quantity, outfitId);
      set({ cart, isOpen: true, isLoading: false });
    } catch (err: any) {
      set({ isLoading: false });
      throw err;
    }
  },

  confirmAddDuplicate: async () => {
    const pending = get().pendingDuplicateAlert;
    if (!pending) return;
    set({ isLoading: true });
    try {
      const cart = await commerceService.addToCart(pending.product_sku_id, pending.quantity);
      set({ cart, isOpen: true, pendingDuplicateAlert: null, isLoading: false });
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  dismissDuplicate: () => {
    set({ pendingDuplicateAlert: null });
  },

  updateQuantity: async (cartItemId, quantity) => {
    try {
      const cart = await commerceService.updateQuantity(cartItemId, quantity);
      set({ cart });
    } catch (err) {
      console.error(err);
    }
  },

  removeItem: async (cartItemId) => {
    try {
      const cart = await commerceService.removeItem(cartItemId);
      set({ cart });
    } catch (err) {
      console.error(err);
    }
  },
}));
