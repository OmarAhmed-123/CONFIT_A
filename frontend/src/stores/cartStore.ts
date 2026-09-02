import { create } from 'zustand';
import { useAuthStore } from './authStore';
import { Cart } from '../models';
import { commerceService, wardrobeService } from '../services/apiServices';

function persistCart(cart: Cart | null) {
  try {
    if (cart) {
      localStorage.setItem('confit_cart', JSON.stringify(cart));
    } else {
      localStorage.removeItem('confit_cart');
    }
  } catch {
    /* ignore quota */
  }
}

function getSavedCart(): Cart | null {
  try {
    const raw = localStorage.getItem('confit_cart');
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && Array.isArray(parsed.items)) {
      return parsed as Cart;
    }
  } catch {
    /* ignore */
  }
  return null;
}

interface CartState {
  cart: Cart | null;
  isOpen: boolean;
  isLoading: boolean;
  error: string | null;
  pendingDuplicateAlert: {
    product_sku_id: number;
    quantity: number;
    owned_item: any;
    alert_message: string;
  } | null;
  openCart: () => void;
  closeCart: () => void;
  fetchCart: () => Promise<void>;
  addItem: (
    productSkuId: number,
    productInfo?: { id: number; title: string; category: string; color: string },
    quantity?: number,
    outfitId?: number
  ) => Promise<void>;
  confirmAddDuplicate: () => Promise<void>;
  dismissDuplicate: () => void;
  updateQuantity: (cartItemId: number, quantity: number) => Promise<void>;
  removeItem: (cartItemId: number) => Promise<void>;
  applyPromo: (code: string) => Promise<void>;
}

export const useCartStore = create<CartState>((set, get) => ({
  cart: getSavedCart(),
  isOpen: false,
  isLoading: false,
  error: null,
  pendingDuplicateAlert: null,

  openCart: () => set({ isOpen: true }),
  closeCart: () => set({ isOpen: false }),

  fetchCart: async () => {
    try {
      const cart = await commerceService.getCart();
      persistCart(cart);
      set({ cart, error: null });
    } catch (err: any) {
      set({ error: err?.message || 'Unable to load cart' });
    }
  },

  addItem: async (productSkuId, productInfo, quantity = 1, outfitId) => {
    set({ isLoading: true, error: null });
    try {
      if (productInfo && useAuthStore.getState().isAuthenticated) {
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
        } catch {
          // Duplicate check is advisory — continue with the add.
        }
      }

      const updatedCart = await commerceService.addToCart(productSkuId, quantity, outfitId);
      persistCart(updatedCart);
      set({ cart: updatedCart, isOpen: true, isLoading: false, error: null });
    } catch (err: any) {
      set({ isLoading: false, error: err?.message || 'Could not add item' });
      throw err;
    }
  },

  confirmAddDuplicate: async () => {
    const pending = get().pendingDuplicateAlert;
    if (!pending) return;
    set({ isLoading: true });
    try {
      const updatedCart = await commerceService.addToCart(pending.product_sku_id, pending.quantity);
      persistCart(updatedCart);
      set({ cart: updatedCart, pendingDuplicateAlert: null, isLoading: false, isOpen: true });
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  dismissDuplicate: () => {
    set({ pendingDuplicateAlert: null });
  },

  updateQuantity: async (cartItemId, quantity) => {
    // C7 FIX: Optimistic update with rollback and server reconciliation
    const prevCart = get().cart;
    if (!prevCart) return;

    // Capture previous state for rollback
    const prevItems = prevCart.items;
    const targetItem = prevItems.find((it) => it.id === cartItemId);
    if (!targetItem) return;

    // Optimistic update
    const optimisticItems = prevItems.map((it) =>
      it.id === cartItemId ? { ...it, quantity, subtotal: it.unit_price * quantity } : it
    ).filter((it) => it.quantity > 0);

    const optimisticCart = {
      ...prevCart,
      items: optimisticItems,
      items_count: optimisticItems.reduce((sum, it) => sum + it.quantity, 0),
      subtotal: optimisticItems.reduce((sum, it) => sum + it.subtotal, 0),
    };

    set({ cart: optimisticCart as any, error: null });

    try {
      const serverCart = await commerceService.updateQuantity(cartItemId, quantity);
      // Reconcile with authoritative server response
      persistCart(serverCart);
      set({ cart: serverCart, error: null });
    } catch (err: any) {
      // Rollback on failure - UI must never remain inconsistent with backend
      persistCart(prevCart);
      set({ cart: prevCart, error: err?.message || 'Could not update quantity' });
      throw err;
    }
  },

  removeItem: async (cartItemId) => {
    // C7 FIX: Optimistic removal with rollback
    const prevCart = get().cart;
    if (!prevCart) return;

    const optimisticItems = prevCart.items.filter((it) => it.id !== cartItemId);
    const optimisticCart = {
      ...prevCart,
      items: optimisticItems,
      items_count: optimisticItems.reduce((sum, it) => sum + it.quantity, 0),
      subtotal: optimisticItems.reduce((sum, it) => sum + it.subtotal, 0),
    };

    set({ cart: optimisticCart as any, error: null });

    try {
      const serverCart = await commerceService.removeItem(cartItemId);
      persistCart(serverCart);
      set({ cart: serverCart, error: null });
    } catch (err: any) {
      // Rollback
      persistCart(prevCart);
      set({ cart: prevCart, error: err?.message || 'Could not remove item' });
      throw err;
    }
  },

  applyPromo: async (code) => {
    const prevCart = get().cart;
    try {
      const updatedCart = await commerceService.applyPromo(code);
      persistCart(updatedCart);
      set({ cart: updatedCart, error: null });
    } catch (err: any) {
      // Promo failure should not rollback cart, just show error
      set({ error: err?.message || 'Could not apply promo' });
      throw err;
    }
  },
}));
