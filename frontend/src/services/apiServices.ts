import { request } from './apiClient';
import {
  User,
  UserStyleProfile,
  Product,
  Category,
  Outfit,
  StylistMessage,
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
  SearchResponse,
  AutocompleteResponse,
  AdminPlatformAnalytics,
  StoreInventoryLocation,
  TryOnJob,
  GarmentAsset,
} from '../models';

// 1. Authentication Services (G1)
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

  // Group 1 §7: the server verifies the provider_token upstream (Google /
  // Apple / Facebook), so we ONLY send the provider name and the token
  // the SDK gave us — never the email or the display name, which are
  // taken from the provider's verified response.
  socialLogin: (provider: 'google' | 'apple' | 'facebook', providerToken: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>('/auth/social-login', {
      method: 'POST',
      body: JSON.stringify({ provider, provider_token: providerToken }),
    }),

  getMe: () => request<User>('/auth/me'),

  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),

  setupMFA: () => request<{ secret: string; qr_uri: string; backup_codes: string[] }>('/auth/mfa/setup', { method: 'POST' }),

  // Verify returns the plaintext backup codes exactly ONCE — the caller
  // MUST persist / display them to the user immediately.
  verifyMFA: (code: string) =>
    request<{ status: string; backup_codes: string[] }>('/auth/mfa/verify', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),

  disableMFA: (password: string) =>
    request<{ status: string }>('/auth/mfa/disable', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  regenerateMFACodes: () =>
    request<{ status: string; backup_codes: string[] }>('/auth/mfa/regenerate-codes', {
      method: 'POST',
    }),

  refresh: (refresh_token: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token }),
    }),

  forgotPassword: (email: string) =>
    request<{ status: string; message: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, new_password: string) =>
    request<{ status: string; message: string }>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password }),
    }),

  exportGDPR: () => request<any>('/auth/gdpr-export'),

  deleteAccount: () => request<{ status: string }>('/auth/account', { method: 'DELETE' }),
};

// 2. User Style Profile (USP) Services (G1.2)
// The backend now returns EITHER a full USPResponse OR a {state:"not_completed"}
// stub — the caller must handle both. Prior code silently fabricated a
// default USP if the profile was missing; that server-side behavior is gone.
export interface UspNotCompletedStub {
  user_id: number;
  onboarding_completed: false;
  state: 'not_completed';
  message: string;
}
export type UspResponseOrStub = UserStyleProfile | UspNotCompletedStub;

export const profileService = {
  getProfile: () => request<UspResponseOrStub>('/profile/me'),
  getUSP: () => request<UspResponseOrStub>('/profile/me'),

  submitOnboardingQuiz: (quizData: any) =>
    request<UserStyleProfile>('/profile/onboarding-quiz', {
      method: 'POST',
      body: JSON.stringify(quizData),
    }),

  // Split PATCH endpoints (G1 §31) — each accepts only the fields for its
  // own concern, so an update to one area cannot silently overwrite others.
  updateStylePreferences: (data: {
    style_archetypes?: string[];
    preferred_colors?: string[];
    avoided_colors?: string[];
    fashion_aesthetics?: string[];
  }) =>
    request<UserStyleProfile>('/me/style-profile', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  updateBodyAttributes: (attributes: {
    height_cm?: number;
    weight_kg?: number;
    body_shape?: string;
    chest_cm?: number;
    waist_cm?: number;
    hip_cm?: number;
    inseam_cm?: number;
  }) =>
    request<UserStyleProfile>('/me/body-profile', {
      method: 'PATCH',
      body: JSON.stringify(attributes),
    }),

  deleteBodyAttributes: () =>
    request<{ status: string }>('/me/body-profile', { method: 'DELETE' }),

  updateBudget: (data: {
    budget_monthly_min?: number;
    budget_monthly_max?: number;
    budget_per_outfit_max?: number;
  }) =>
    request<UserStyleProfile>('/me/budget', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  updateBrandPreferences: (data: {
    preferred_brands?: string[];
    blacklisted_brands?: string[];
  }) =>
    request<UserStyleProfile>('/me/brands', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  updateOccasions: (occasion_weights: Record<string, number>) =>
    request<UserStyleProfile>('/me/occasions', {
      method: 'PATCH',
      body: JSON.stringify({ occasion_weights }),
    }),

  updateSizeFit: (data: {
    size_tops?: string;
    size_bottoms?: string;
    size_shoes?: string;
    fit_preference?: string;
  }) =>
    request<UserStyleProfile>('/me/size-fit', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Legacy alias used by older call sites — accepts the full quiz payload.
  submitQuiz: (quizData: any) =>
    request<UserStyleProfile>('/profile/onboarding-quiz', {
      method: 'POST',
      body: JSON.stringify(quizData),
    }),

  updateProfile: (data: any) =>
    request<UserStyleProfile>('/profile/preferences', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  getConsents: () =>
    request<{
      user_id: number;
      photo_storage: boolean;
      ai_personalization: boolean;
      marketing_analytics: boolean;
      share_with_brands: boolean;
      policy_version: number;
      last_agreed_at: string | null;
    }>('/me/consents'),

  updateConsents: (consents: {
    photo_storage?: boolean;
    ai_personalization?: boolean;
    marketing_analytics?: boolean;
    share_with_brands?: boolean;
  }) =>
    request<any>('/me/consents', {
      method: 'PATCH',
      body: JSON.stringify(consents),
    }),
};

// 3. Catalog, Search & BOPIS Services (G2.1)
export const catalogService = {
  getProducts: (params?: {
    category?: string;
    brand_id?: number;
    color?: string;
    occasion?: string;
    min_price?: number;
    max_price?: number;
    search?: string;
    sort_by?: string;
    limit?: number;
  }) => {
    // Root-cause fix for the empty live catalog: URLSearchParams serializes
    // undefined values as the literal string "undefined", which the backend
    // then applied as a real filter (search="undefined" matches nothing, so
    // the whole catalog rendered empty). Only defined, non-empty params go
    // on the wire.
    const clean = Object.fromEntries(
      Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== null && v !== '')
    );
    const query = new URLSearchParams(clean as Record<string, string>).toString();
    return request<Product[]>(`/catalog/products${query ? `?${query}` : ''}`);
  },

  getProductDetail: (slug: string) => request<Product>(`/catalog/products/${slug}`),

  getCategories: () => request<Category[]>('/catalog/categories'),

  getFeaturedCollections: () => request<Product[]>('/catalog/products?is_featured=true'),

  searchCatalog: (params: {
    q: string;
    category?: string;
    brand_id?: number;
    color?: string;
    min_price?: number;
    max_price?: number;
    sort_by?: string;
    page?: number;
    limit?: number;
  }) => {
    // Same undefined-serialization guard as getProducts.
    const clean = Object.fromEntries(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    );
    const query = new URLSearchParams(clean as Record<string, string>).toString();
    return request<SearchResponse>(`/catalog/search${query ? `?${query}` : ''}`);
  },

  autocompleteCatalog: (q: string) => request<AutocompleteResponse>(`/catalog/autocomplete?q=${encodeURIComponent(q)}`),

  getBopisStoresForSKU: (skuId: number) => request<StoreInventoryLocation[]>(`/catalog/skus/${skuId}/stores`),

  // Home Dashboard (G2.4): personalized picks, trending, recently-viewed,
  // new-from-your-brands — composed server-side from the real profile + catalog.
  getDashboard: (coords?: { lat: number; lon: number }) => {
    const query = coords ? `?lat=${coords.lat}&lon=${coords.lon}` : '';
    return request<any>(`/catalog/dashboard${query}`);
  },
};

// 4. Virtual Stylist & Outfitting Engine Services (G2.2)
export const stylistService = {
  chat: (payload: { prompt: string; session_id?: number; occasion?: string; budget_limit?: number; voice_input_used?: boolean }) =>
    request<StylistMessage>('/stylist/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  checkCompatibility: (productIdsOrPayload: any, targetOccasion?: string) => {
    const payload = Array.isArray(productIdsOrPayload)
      ? { product_ids: productIdsOrPayload, target_occasion: targetOccasion || 'Casual' }
      : productIdsOrPayload;
    return request<{ compatibility_score: number; breakdown: Record<string, number>; color_harmony_type: string; notes: string[] }>(
      '/stylist/compatibility',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  },

  getSavedOutfits: () => request<Outfit[]>('/outfits'),

  saveOutfit: (data: { title: string; occasion: string; product_ids?: number[]; product_sku_ids?: number[] }) =>
    request<Outfit>('/outfits', {
      method: 'POST',
      body: JSON.stringify({
        title: data.title,
        occasion: data.occasion,
        // Canonical contract: send whichever identifier set the caller holds.
        // No fabricated fallback ids — the backend validates non-empty.
        ...(data.product_sku_ids ? { product_sku_ids: data.product_sku_ids } : {}),
        ...(data.product_ids ? { product_ids: data.product_ids } : {}),
      }),
    }),

  deleteOutfit: (id: number) => request<{ status: string }>(`/outfits/${id}`, { method: 'DELETE' }),

  // C8: mint (or fetch the idempotent) share token for an owned outfit.
  // The response intentionally contains no fabricated card URL.
  shareOutfit: (id: number) =>
    request<{ outfit_id: number; share_token: string; share_url: string }>(`/outfits/${id}/share`, {
      method: 'POST',
    }),
};

// 4b. Public Shared Looks (C8) — unauthenticated, public-safe DTO only.
export const publicLookService = {
  getPublicLook: (token: string) =>
    request<{
      title: string;
      occasion: string;
      description?: string | null;
      total_price: number;
      compatibility_score: number;
      items: Array<{
        product_title: string;
        brand_name: string;
        category_name: string;
        price: number;
        image_url: string;
        color_hex: string;
        position: string;
      }>;
      created_at: string;
    }>(`/public/looks/${encodeURIComponent(token)}`),
};

// 5. Virtual Try-On & Fit Services (G3)
export const tryOnService = {
  // Asynchronous GPU VTON Job Queue
  submitTryOnJob: (payload: {
    product_ids: number[];
    user_image_url?: string;
    user_image_base64?: string;
    avatar_model_id?: string;
    gender_mode?: string;
    output_aspect?: string;
    consent_retain_photo?: boolean;
  }) =>
    request<TryOnJob>('/try-on/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getTryOnJobStatus: (jobId: string) => request<TryOnJob>(`/try-on/jobs/${jobId}`),

  cancelTryOnJob: (jobId: string) =>
    request<{ job_id: string; status: string }>(`/try-on/jobs/${jobId}/cancel`, {
      method: 'POST',
    }),

  getGarmentAsset: (productId: number) => request<GarmentAsset>(`/try-on/garments/${productId}/asset`),

  // Multi-Garment Synchronous Render
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
export interface AutoTagResponse {
  analysis_available: boolean;
  detail?: string;
  detected_title?: string;
  detected_category?: string;
  detected_subcategory?: string;
  detected_color?: string;
  detected_color_hex?: string;
  detected_pattern?: string;
  ai_tags?: string[];
  suggested_occasions?: string[];
  seasonality?: string;
  confidence?: number;
}

export interface WardrobeUploadResultEntry {
  filename: string;
  status: 'created' | 'failed' | 'duplicate';
  detail?: string;
  item?: WardrobeItem;
}

export interface WardrobeUploadResponse {
  results: WardrobeUploadResultEntry[];
  summary: { total: number; succeeded: number; failed: number; duplicates_skipped: number };
}

export interface WardrobeFirstOutfitItem {
  position: string;
  source: 'owned' | 'catalog';
  wardrobe_item_id?: number;
  product_id?: number;
  product_title: string;
  brand_name: string;
  color_family?: string;
  dominant_hex?: string;
  image_url: string;
  price: number;
}

export interface WardrobeFirstOutfit {
  occasion: string;
  owned_items: WardrobeFirstOutfitItem[];
  owned_count: number;
  missing_positions: string[];
  purchase_suggestions: WardrobeFirstOutfitItem[];
  compatibility_score: number;
  is_complete_outfit: boolean;
  wardrobe_first: boolean;
  message: string;
}

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

  deleteItem: (itemId: number) => request<{ status: string }>(`/wardrobe/items/${itemId}`, { method: 'DELETE' }),

  getGaps: () => request<GapAnalysisItem[]>('/wardrobe/gap-analysis'),
  getGapAnalysis: () => request<GapAnalysisItem[]>('/wardrobe/gap-analysis'),

  autoTagImage: (imageRef: string) => {
    // Backend contract is { image_url } for URLs or { image_base64 } for data
    // URLs — the previous payload key (image_data_url) matched neither and
    // silently 422'd.
    const body = imageRef.startsWith('data:image')
      ? { image_base64: imageRef }
      : { image_url: imageRef };
    return request<AutoTagResponse>('/wardrobe/auto-tag', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  uploadImage: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<WardrobeUploadResponse>('/wardrobe/upload', {
      method: 'POST',
      body: form,
    });
  },

  uploadBulk: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    return request<WardrobeUploadResponse>('/wardrobe/upload/bulk', {
      method: 'POST',
      body: form,
    });
  },

  analyzeItem: (itemId: number) =>
    request<WardrobeItem>(`/wardrobe/items/${itemId}/analyze`, { method: 'POST' }),

  getOutfitSuggestions: (occasion: string = 'Smart Casual') =>
    request<WardrobeFirstOutfit>(`/wardrobe/outfit-suggestions?occasion=${encodeURIComponent(occasion)}`),

  checkDuplicate: (payload: { product_id: number; product_title: string; category: string; color_family: string; strict_mode?: boolean }) =>
    request<{ has_duplicate_risk: boolean; similarity_score: number; duplicate_item?: WardrobeItem; owned_item?: WardrobeItem; alert_message?: string; recommendation: string }>(
      '/wardrobe/duplicate-check',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    ),
};

// 7. Unified Commerce & BOPIS Services (G5)
export const commerceService = {
  getCart: () => request<Cart>('/commerce/cart'),

  addToCart: (productSkuId: number, quantity: number = 1, outfitId?: number) =>
    request<Cart>('/commerce/cart/items', {
      method: 'POST',
      body: JSON.stringify({ product_sku_id: productSkuId, quantity, outfit_id: outfitId }),
    }),

  updateQuantity: (itemId: number, quantity: number) =>
    request<Cart>(`/commerce/cart/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify({ quantity }),
    }),

  removeFromCart: (itemId: number) => request<Cart>(`/commerce/cart/items/${itemId}`, { method: 'DELETE' }),
  removeItem: (itemId: number) => request<Cart>(`/commerce/cart/items/${itemId}`, { method: 'DELETE' }),

  checkout: (payload: {
    payment_method: string;
    fulfillment_type: string;
    bopis_store_id?: number;
    recipient_name: string;
    phone: string;
    address_line?: string;
    city?: string;
    country?: string;
    promo_code?: string;
    try_on_assisted?: boolean;
    stylist_assisted?: boolean;
  }) =>
    request<Order>('/commerce/checkout', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getOrders: () => request<Order[]>('/commerce/orders'),

  getOrderDetail: (orderNumber: string) => request<Order>(`/commerce/orders/${orderNumber}`),

  getOrderTracking: (orderNumber: string) => request<OrderTrackingTimeline>(`/commerce/orders/${orderNumber}/tracking`),

  createReturn: (payload: { order_id: number; item_ids: number[]; reason: string; details?: string }) =>
    request<any>('/commerce/returns', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

// 8. B2B Brand Management & Platform Admin Services (G6)
export const brandService = {
  getProfile: () => request<BrandProfile>('/brand/profile'),

  getAnalytics: () => request<BrandAnalyticsDashboard>('/brand/analytics'),
  getAnalyticsDashboard: () => request<BrandAnalyticsDashboard>('/brand/analytics'),

  getProducts: () => request<Product[]>('/brand/products'),

  updateSKU: (skuId: number, stockLevel: number, priceOverride?: number) => {
    const q = priceOverride ? `&price_override=${priceOverride}` : '';
    return request<any>(`/brand/skus/${skuId}?stock_level=${stockLevel}${q}`, {
      method: 'PUT',
    });
  },

  updateSKUStock: (skuId: number, stockLevel: number, priceOverride?: number) => {
    const q = priceOverride ? `&price_override=${priceOverride}` : '';
    return request<any>(`/brand/skus/${skuId}?stock_level=${stockLevel}${q}`, {
      method: 'PUT',
    });
  },

  getPlacements: () => request<any[]>('/brand/placements'),

  createPlacement: (payload: { product_id: number; placement_type: string; bid_amount_per_click: number; daily_budget: number }) =>
    request<any>('/brand/placements', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getAdminAnalytics: () => request<AdminPlatformAnalytics>('/admin/analytics'),
};

// 9. Admin Service
export const adminService = {
  getPlatformAnalytics: () => request<AdminPlatformAnalytics>('/admin/analytics'),
  getBrandComparison: () => request<any[]>('/admin/analytics/brands'),
  getAuditLogs: () => request<any[]>('/admin/audit'),
};
