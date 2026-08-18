import { request } from './apiClient';
import {
  User,
  UserStyleProfile,
  Category,
  Product,
  StoreInventoryLocation,
  StylistMessage,
  Outfit,
  TryOnResult,
  MultiGarmentTryOnResult,
  AnimationTryOnResult,
  NoPhotoFitResult,
  VisualSearchResult,
  WardrobeItem,
  GapAnalysisItem,
  Cart,
  Order,
  OrderTrackingTimeline,
  BrandProfile,
  BrandAnalyticsDashboard,
  SponsoredPlacement,
  AdminPlatformAnalytics,
} from '../models';

// 1. Auth & Identity Services (G1)
export const authService = {
  login: (email: string, password: string, mfa_code?: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, mfa_code }),
    }),

  register: (payload: { email: string; password: string; full_name: string; phone?: string; role?: string }) =>
    request<{ access_token: string; refresh_token: string; user: User }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  socialLogin: (provider: string, email: string, full_name: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>('/auth/social-login', {
      method: 'POST',
      body: JSON.stringify({ provider, access_token: `token_${provider}`, email, full_name }),
    }),

  getMe: () => request<User>('/auth/me'),

  setupMFA: () => request<{ secret: string; qr_uri: string; backup_codes: string[] }>('/auth/mfa/setup', { method: 'POST' }),

  verifyMFA: (code: string) => request<{ status: string; message: string }>('/auth/mfa/verify', {
    method: 'POST',
    body: JSON.stringify({ code }),
  }),

  exportGDPR: () => request<any>('/auth/gdpr-export'),

  deleteAccount: () => request<{ status: string; message: string }>('/auth/account', { method: 'DELETE' }),
};

// 2. Profile & USP Services (G1)
export const profileService = {
  getUSP: () => request<UserStyleProfile>('/profile/me'),

  submitQuiz: (data: any) =>
    request<UserStyleProfile>('/profile/onboarding-quiz', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updatePreferences: (data: any) =>
    request<UserStyleProfile>('/profile/preferences', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
};

// 3. Catalog Services (G2 & G5)
export const catalogService = {
  getCategories: () => request<Category[]>('/catalog/categories'),

  getProducts: (params: {
    category?: string;
    brand_id?: number;
    color?: string;
    occasion?: string;
    min_price?: number;
    max_price?: number;
    search?: string;
    sort_by?: string;
    is_featured?: boolean;
  } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        query.append(k, String(v));
      }
    });
    return request<Product[]>(`/catalog/products?${query.toString()}`);
  },

  getProductDetail: (slugOrId: string | number) => request<Product>(`/catalog/products/${slugOrId}`),

  getBopisStoresForSKU: (skuId: number) => request<StoreInventoryLocation[]>(`/catalog/skus/${skuId}/stores`),
};

// 4. AI Stylist & Outfits Services (G2)
export const stylistService = {
  chat: (payload: { prompt: string; occasion?: string; budget_limit?: number; voice_input_used?: boolean }) =>
    request<StylistMessage>('/stylist/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  checkCompatibility: (productIds: number[], targetOccasion = 'Casual') =>
    request<{
      compatibility_score: number;
      color_harmony_type: string;
      color_harmony_verdict: string;
      aesthetic_consistency_verdict: string;
      occasion_score: number;
      budget_status: string;
      suggestions: string[];
    }>('/stylist/compatibility', {
      method: 'POST',
      body: JSON.stringify({ product_ids: productIds, target_occasion: targetOccasion }),
    }),

  getMyLooks: () => request<Outfit[]>('/outfits/my-looks'),

  saveOutfit: (payload: { title: string; occasion: string; product_sku_ids: number[]; description?: string }) =>
    request<Outfit>('/outfits/save', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

// 5. Virtual Try-On & Fit Services (G3)
export const tryOnService = {
  renderTryOn: (payload: {
    product_id: number;
    user_image_url?: string;
    avatar_model_id?: string;
    consent_retain_photo?: boolean;
  }) =>
    request<TryOnResult>('/tryon/render', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  renderAnimationTryOn: (payload: {
    product_ids?: number[];
    slot_mapping?: Record<string, number>;
    user_image_url?: string;
    avatar_model_id?: string;
    gender_mode?: string;
    output_aspect?: string;
    background_mode?: string;
  }) =>
    request<AnimationTryOnResult>('/tryon/animation-render', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  multiRenderTryOn: (payload: {
    product_ids?: number[];
    slot_mapping?: Record<string, number>;
    user_image_url?: string;
    avatar_model_id?: string;
    gender_mode?: string;
    consent_retain_photo?: boolean;
  }) =>
    request<MultiGarmentTryOnResult>('/tryon/multi-render', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  applyGarmentsToSession: (
    sessionId: number,
    payload: {
      product_ids?: number[];
      slot_mapping?: Record<string, number>;
      user_image_url?: string;
      avatar_model_id?: string;
      gender_mode?: string;
      consent_retain_photo?: boolean;
    }
  ) =>
    request<MultiGarmentTryOnResult>(`/tryon/sessions/${sessionId}/apply-garments`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  validateImage: (payload: { image_url?: string; image_base64?: string }) =>
    request<{
      is_valid: boolean;
      detected_gender: string;
      body_framing: string;
      resolution_status: string;
      lighting_quality: string;
      suggestions: string[];
    }>('/tryon/validate-image', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  calculateNoPhotoFit: (payload: {
    product_id: number;
    height_cm: number;
    weight_kg: number;
    body_shape: string;
    chest_cm?: number;
    waist_cm?: number;
    preferred_fit?: string;
  }) =>
    request<NoPhotoFitResult>('/tryon/no-photo-fit', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  searchVisual: (payload: { image_url?: string; max_price?: number; in_stock_only?: boolean }) =>
    request<VisualSearchResult>('/tryon/visual-search', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

// 6. Virtual Wardrobe Services (G4)
export const wardrobeService = {
  getItems: (category?: string) => {
    const q = category && category !== 'All' ? `?category=${category}` : '';
    return request<WardrobeItem[]>(`/wardrobe/items${q}`);
  },

  addItem: (data: Partial<WardrobeItem>) =>
    request<WardrobeItem>('/wardrobe/items', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateItem: (itemId: number, data: Partial<WardrobeItem>) =>
    request<WardrobeItem>(`/wardrobe/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteItem: (itemId: number) =>
    request<{ status: string; message: string }>(`/wardrobe/items/${itemId}`, {
      method: 'DELETE',
    }),

  autoTagImage: (imageUrl: string) =>
    request<{
      detected_title: string;
      detected_category: string;
      detected_subcategory: string;
      detected_color: string;
      detected_color_hex: string;
      detected_pattern: string;
      ai_tags: string[];
      suggested_occasions: string[];
      confidence: number;
    }>('/wardrobe/auto-tag', {
      method: 'POST',
      body: JSON.stringify({ image_url: imageUrl }),
    }),

  getGapAnalysis: () => request<GapAnalysisItem[]>('/wardrobe/gap-analysis'),

  checkDuplicate: (payload: { product_id: number; product_title: string; category: string; color_family: string; strict_mode?: boolean }) =>
    request<{
      has_duplicate_risk: boolean;
      similarity_score: number;
      owned_item?: WardrobeItem;
      alert_message?: string;
      comparison_notes?: string;
    }>('/wardrobe/duplicate-check', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

// 7. Commerce, Cart, BNPL & Order Services (G5)
export const commerceService = {
  getCart: () => request<Cart>('/commerce/cart'),

  addToCart: (productSkuId: number, quantity = 1, outfitId?: number) =>
    request<Cart>('/commerce/cart/items', {
      method: 'POST',
      body: JSON.stringify({ product_sku_id: productSkuId, quantity, outfit_id: outfitId }),
    }),

  updateQuantity: (cartItemId: number, quantity: number) =>
    request<Cart>(`/commerce/cart/items/${cartItemId}?quantity=${quantity}`, {
      method: 'PUT',
    }),

  removeItem: (cartItemId: number) =>
    request<Cart>(`/commerce/cart/items/${cartItemId}`, {
      method: 'DELETE',
    }),

  checkout: (data: {
    payment_method: string;
    fulfillment_type: string;
    bopis_store_id?: number;
    recipient_name: string;
    phone: string;
    address_line?: string;
    city: string;
    country?: string;
    promo_code?: string;
    try_on_assisted?: boolean;
    stylist_assisted?: boolean;
  }) =>
    request<Order>('/commerce/checkout', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getOrders: () => request<Order[]>('/commerce/orders'),

  getOrderDetail: (orderNumber: string) => request<Order>(`/commerce/orders/${orderNumber}`),

  getOrderTracking: (orderNumber: string) => request<OrderTrackingTimeline>(`/commerce/orders/${orderNumber}/tracking`),

  createReturn: (data: { order_id: number; reason: string; details?: string; item_ids: number[] }) =>
    request<any>('/commerce/returns', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getBNPLQuote: (amount: number, provider = 'tabby') =>
    request<{
      provider: string;
      eligible: boolean;
      installments_count: number;
      installment_amount: number;
      payment_schedule: Array<{ due_in_days: number; amount: number; status: string }>;
      disclaimer: string;
    }>('/commerce/bnpl-quote', {
      method: 'POST',
      body: JSON.stringify({ amount, provider }),
    }),
};

// 8. Brand & Admin Portal Services (G6)
export const brandService = {
  getProfile: () => request<BrandProfile>('/brand/profile'),

  getAnalytics: () => request<BrandAnalyticsDashboard>('/brand/analytics'),

  getProducts: () => request<Product[]>('/brand/products'),

  updateSKU: (skuId: number, stockLevel: number, priceOverride?: number) => {
    const q = priceOverride !== undefined ? `&price_override=${priceOverride}` : '';
    return request<any>(`/brand/skus/${skuId}?stock_level=${stockLevel}${q}`, {
      method: 'PUT',
    });
  },

  getPlacements: () => request<SponsoredPlacement[]>('/brand/placements'),

  createPlacement: (data: { product_id: number; placement_type?: string; bid_amount_per_click?: number; daily_budget?: number }) =>
    request<SponsoredPlacement>('/brand/placements', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

export const adminService = {
  getPlatformAnalytics: () => request<AdminPlatformAnalytics>('/admin/analytics'),
};
