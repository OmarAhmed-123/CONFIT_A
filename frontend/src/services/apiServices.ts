import { request } from "./apiClient";
import {
  User,
  UserStyleProfile,
  Product,
  Category,
  CompositionVerdict,
  Outfit,
  ShareLink,
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
  AuditTrailPage,
  AuditFacets,
  AuditIntegrity,
  AuditStats,
} from "../models";

// 1. Authentication Services (G1)
export const authService = {
  login: (email: string, password: string, mfa_code?: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password, mfa_code }),
      },
    ),

  register: (payload: {
    email: string;
    password: string;
    full_name: string;
    phone?: string;
    role?: string;
  }) =>
    request<{ access_token: string; refresh_token: string; user: User }>(
      "/auth/register",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),

  // Group 1 §7: the server verifies the provider_token upstream (Google /
  // Apple / Facebook), so we ONLY send the provider name and the token
  // the SDK gave us — never the email or the display name, which are
  // taken from the provider's verified response.
  socialLogin: (
    provider: "google" | "apple" | "facebook",
    providerToken: string,
  ) =>
    request<{ access_token: string; refresh_token: string; user: User }>(
      "/auth/social-login",
      {
        method: "POST",
        body: JSON.stringify({ provider, provider_token: providerToken }),
      },
    ),

  getMe: () => request<User>("/auth/me"),

  logout: () => request<{ status: string }>("/auth/logout", { method: "POST" }),

  setupMFA: () =>
    request<{ secret: string; qr_uri: string; backup_codes: string[] }>(
      "/auth/mfa/setup",
      { method: "POST" },
    ),

  // Verify returns the plaintext backup codes exactly ONCE — the caller
  // MUST persist / display them to the user immediately.
  verifyMFA: (code: string) =>
    request<{ status: string; backup_codes: string[] }>("/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  // Hardened: removing the second factor re-authenticates with BOTH the
  // password and a current authenticator/recovery code (OWASP MFA guidance —
  // a stolen password alone must never be able to remove MFA).
  disableMFA: (password: string, mfaCode: string) =>
    request<{ status: string }>("/auth/mfa/disable", {
      method: "POST",
      body: JSON.stringify({ password, mfa_code: mfaCode }),
    }),

  // Cycle 9: authenticated password rotation — the only in-product way to
  // change a password while email delivery is unprovisioned (the email
  // reset path honestly 501s until a provider exists). MFA-enabled
  // accounts must also send a current authenticator/recovery code.
  changePassword: (payload: {
    current_password: string;
    new_password: string;
    mfa_code?: string;
  }) =>
    request<{ status: string; message: string }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Step-up contract (server-enforced): regeneration mints fresh recovery
  // codes, so it demands the same proof as disabling MFA — current password
  // plus a current TOTP/recovery code.
  regenerateMFACodes: (password: string, mfaCode: string) =>
    request<{ status: string; backup_codes: string[] }>(
      "/auth/mfa/regenerate-codes",
      {
        method: "POST",
        body: JSON.stringify({ password, mfa_code: mfaCode }),
      },
    ),

  refresh: (refresh_token: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>(
      "/auth/refresh",
      {
        method: "POST",
        body: JSON.stringify({ refresh_token }),
      },
    ),

  forgotPassword: (email: string) =>
    request<{ status: string; message: string }>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, new_password: string) =>
    request<{ status: string; message: string }>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password }),
    }),

  exportGDPR: () => request<any>("/auth/gdpr-export"),

  // Step-up contract: permanent deletion requires explicit confirmation,
  // the current password, and (when MFA is enabled) a current code.
  deleteAccount: (password: string, mfaCode?: string) =>
    request<{ status: string }>("/auth/account", {
      method: "DELETE",
      body: JSON.stringify({
        confirm: "DELETE",
        password,
        ...(mfaCode ? { mfa_code: mfaCode } : {}),
      }),
    }),
};

// 2. User Style Profile (USP) Services (G1.2)
// The backend now returns EITHER a full USPResponse OR a {state:"not_completed"}
// stub — the caller must handle both. Prior code silently fabricated a
// default USP if the profile was missing; that server-side behavior is gone.
export interface UspNotCompletedStub {
  user_id: number;
  onboarding_completed: false;
  state: "not_completed";
  message: string;
}
export type UspResponseOrStub = UserStyleProfile | UspNotCompletedStub;

export const profileService = {
  getProfile: () => request<UspResponseOrStub>("/profile/me"),
  getUSP: () => request<UspResponseOrStub>("/profile/me"),

  submitOnboardingQuiz: (quizData: any) =>
    request<UserStyleProfile>("/profile/onboarding-quiz", {
      method: "POST",
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
    request<UserStyleProfile>("/me/style-profile", {
      method: "PATCH",
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
    request<UserStyleProfile>("/me/body-profile", {
      method: "PATCH",
      body: JSON.stringify(attributes),
    }),

  deleteBodyAttributes: () =>
    request<{ status: string }>("/me/body-profile", { method: "DELETE" }),

  updateBudget: (data: {
    budget_monthly_min?: number;
    budget_monthly_max?: number;
    budget_per_outfit_max?: number;
  }) =>
    request<UserStyleProfile>("/me/budget", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  updateBrandPreferences: (data: {
    preferred_brands?: string[];
    blacklisted_brands?: string[];
  }) =>
    request<UserStyleProfile>("/me/brands", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  updateOccasions: (occasion_weights: Record<string, number>) =>
    request<UserStyleProfile>("/me/occasions", {
      method: "PATCH",
      body: JSON.stringify({ occasion_weights }),
    }),

  updateSizeFit: (data: {
    size_tops?: string;
    size_bottoms?: string;
    size_shoes?: string;
    fit_preference?: string;
  }) =>
    request<UserStyleProfile>("/me/size-fit", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // Legacy alias used by older call sites — accepts the full quiz payload.
  submitQuiz: (quizData: any) =>
    request<UserStyleProfile>("/profile/onboarding-quiz", {
      method: "POST",
      body: JSON.stringify(quizData),
    }),

  updateProfile: (data: any) =>
    request<UserStyleProfile>("/profile/preferences", {
      method: "PUT",
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
    }>("/me/consents"),

  updateConsents: (consents: {
    photo_storage?: boolean;
    ai_personalization?: boolean;
    marketing_analytics?: boolean;
    share_with_brands?: boolean;
  }) =>
    request<any>("/me/consents", {
      method: "PATCH",
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
      Object.entries(params ?? {}).filter(
        ([, v]) => v !== undefined && v !== null && v !== "",
      ),
    );
    const query = new URLSearchParams(
      clean as Record<string, string>,
    ).toString();
    return request<Product[]>(`/catalog/products${query ? `?${query}` : ""}`);
  },

  getProductDetail: (slug: string) =>
    request<Product>(`/catalog/products/${slug}`),

  /** The detail endpoint resolves slug OR id; saved outfit items store the
   *  numeric product id, so rehydrating a look uses this path. */
  getProductById: (id: number) => request<Product>(`/catalog/products/${id}`),

  getCategories: () => request<Category[]>("/catalog/categories"),
  getCapabilities: () =>
    request<{
      payments_live: boolean;
      payments_mode: "live" | "demo";
      bnpl_live: boolean;
      /** Measured (live probe), not "the env var is set". See useCapabilities. */
      vton_gpu_ready: boolean;
      /** Canonical engine state, shared with /try-on/capabilities. */
      vton_engine_state: string;
      /** false = this deployment does not offer try-on (not an outage). */
      vton_offered: boolean;
      /** true when a job submitted now can render (ready or cold start). */
      vton_renderable: boolean;
      ai_stylist_live: boolean;
      bopis_live: boolean;
      bopis_store_count: number;
      storage_mode: string;
      returns_window_days: number;
    }>("/catalog/capabilities"),

  getFeaturedCollections: () =>
    request<Product[]>("/catalog/products?is_featured=true"),

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
      Object.entries(params).filter(
        ([, v]) => v !== undefined && v !== null && v !== "",
      ),
    );
    const query = new URLSearchParams(
      clean as Record<string, string>,
    ).toString();
    return request<SearchResponse>(
      `/catalog/search${query ? `?${query}` : ""}`,
    );
  },

  autocompleteCatalog: (q: string) =>
    request<AutocompleteResponse>(
      `/catalog/autocomplete?q=${encodeURIComponent(q)}`,
    ),

  getBopisStoresForSKU: (skuId: number) =>
    request<StoreInventoryLocation[]>(`/catalog/skus/${skuId}/stores`),

  // Home Dashboard (G2.4): personalized picks, trending, recently-viewed,
  // new-from-your-brands — composed server-side from the real profile + catalog.
  getDashboard: (coords?: { lat: number; lon: number }) => {
    const query = coords ? `?lat=${coords.lat}&lon=${coords.lon}` : "";
    return request<any>(`/catalog/dashboard${query}`);
  },
};

// 4. Virtual Stylist & Outfitting Engine Services (G2.2)
export const stylistService = {
  chat: (payload: {
    prompt: string;
    session_id?: number;
    occasion?: string;
    budget_limit?: number;
    voice_input_used?: boolean;
    recommendation_constraints?: {
      palette?: string;
      avoid_palette?: string;
      preferred_fit?: string;
      size_tops?: string;
      size_bottoms?: string;
      size_shoes?: string;
    };
  }) =>
    request<StylistMessage>("/stylist/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  checkCompatibility: (productIdsOrPayload: any, targetOccasion?: string) => {
    const payload = Array.isArray(productIdsOrPayload)
      ? {
          product_ids: productIdsOrPayload,
          target_occasion: targetOccasion || "Casual",
        }
      : productIdsOrPayload;
    return request<{
      compatibility_score: number;
      breakdown: Record<string, number>;
      color_harmony_type: string;
      notes: string[];
    }>("/stylist/compatibility", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getSavedOutfits: () => request<Outfit[]>("/outfits"),

  saveOutfit: (data: {
    title: string;
    occasion: string;
    product_ids?: number[];
    product_sku_ids?: number[];
  }) =>
    request<Outfit>("/outfits", {
      method: "POST",
      body: JSON.stringify({
        title: data.title,
        occasion: data.occasion,
        // Canonical contract: send whichever identifier set the caller holds.
        // No fabricated fallback ids — the backend validates non-empty.
        ...(data.product_sku_ids
          ? { product_sku_ids: data.product_sku_ids }
          : {}),
        ...(data.product_ids ? { product_ids: data.product_ids } : {}),
      }),
    }),

  getOutfit: (id: number) => request<Outfit>(`/outfits/${id}`),

  updateOutfit: (
    id: number,
    data: { title?: string; occasion?: string; description?: string },
  ) =>
    request<Outfit>(`/outfits/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  /** OUTFIT-02: replace a saved look's whole item set (edit + reorder).
   *  Whole-set semantics mirror the server contract: the composition policy
   *  validates a SET, so partial patches could not be checked coherently. */
  replaceOutfitItems: (
    id: number,
    data: { product_sku_ids?: number[]; product_ids?: number[] },
  ) =>
    request<Outfit>(`/outfits/${id}/items`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /** Dry-run the SAME policy the write path uses, so the canvas can show why
   *  a combination will be rejected before the user presses Save. */
  previewComposition: (data: {
    product_sku_ids?: number[];
    product_ids?: number[];
  }) =>
    request<CompositionVerdict>("/outfits/composition/preview", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteOutfit: (id: number) =>
    request<{ status: string }>(`/outfits/${id}`, { method: "DELETE" }),

  // C8/OUTFIT-01: mint (or fetch the idempotent) share token for an owned
  // outfit. The response carries the REAL expiry and active flag — no
  // fabricated card URL and no assumed liveness.
  shareOutfit: (id: number, opts?: { ttl_days?: number; rotate?: boolean }) =>
    request<ShareLink>(`/outfits/${id}/share`, {
      method: "POST",
      body: JSON.stringify(opts ?? {}),
    }),

  /** Owner-facing share status: active?, expiry, real view count. */
  getShareState: (id: number) => request<ShareLink>(`/outfits/${id}/share`),

  /** Revoke the public link. Idempotent; the token is never re-issued. */
  revokeShare: (id: number) =>
    request<{
      outfit_id: number;
      revoked: boolean;
      was_active: boolean;
      is_active: boolean;
    }>(`/outfits/${id}/share`, { method: "DELETE" }),
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
export interface TryOnProductCapability {
  product_id: number;
  product_slug?: string | null;
  category_slug?: string | null;
  slot_type?: string | null;
  state:
    | "supported"
    | "unsupported"
    | "temporarily_unavailable"
    | "misconfigured"
    | "unknown";
  reason_code: string;
  message: string;
  provider: string;
}

/**
 * Live engine health as measured by the backend (a real probe of the GPU
 * worker, not "the env var is set"). Added 2026-09-21 after production
 * reported `engine_state: "available"` while the GPU workspace was disabled by
 * its spend limit and every single job failed.
 */
export interface TryOnEngineHealth {
  verdict: "ready" | "cold_start" | "unavailable" | "not_configured" | "unknown" | string;
  production_ready: boolean;
  detail?: string | null;
  probe_age_seconds?: number | null;
  error_code?: string | null;
  circuit_state?: "closed" | "open" | "half_open" | string | null;
  retry_after_seconds?: number | null;
}

/**
 * Published service-level expectations. The backend asserts these in its live
 * E2E harness, so they are a contract rather than a suggestion.
 */
export interface TryOnSla {
  warm_render_seconds_p50: number;
  warm_render_seconds_p95: number;
  cold_start_seconds_budget: number;
  fail_fast_seconds: number;
  job_timeout_seconds: number;
  delivery_ttl_seconds: number;
  max_garments_per_job: number;
}

export interface TryOnCapabilitiesResponse {
  provider: string;
  engine_state:
    | "available"
    | "cold_start"
    | "temporarily_unavailable"
    | "misconfigured"
    | "unknown"
    | string;
  supported_slots: string[];
  unsupported_slots: string[];
  products: TryOnProductCapability[];
  engine?: TryOnEngineHealth | null;
  sla?: TryOnSla | null;
  /** Backend-authored, user-facing sentence for the current engine state. */
  user_message?: string | null;
}

export const tryOnService = {
  getCapabilities: (productIds: number[]) => {
    const params = productIds
      .map((id) => `product_ids=${encodeURIComponent(String(id))}`)
      .join("&");
    return request<TryOnCapabilitiesResponse>(
      `/try-on/capabilities${params ? `?${params}` : ""}`,
    );
  },

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
    request<TryOnJob>("/try-on/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getTryOnJobStatus: (jobId: string) =>
    request<TryOnJob>(`/try-on/jobs/${jobId}`),

  cancelTryOnJob: (jobId: string) =>
    request<{ job_id: string; status: string }>(
      `/try-on/jobs/${jobId}/cancel`,
      {
        method: "POST",
      },
    ),

  getGarmentAsset: (productId: number) =>
    request<GarmentAsset>(`/try-on/garments/${productId}/asset`),

  // Multi-Garment Synchronous Render
  renderTryOn: (payload: {
    product_id: number;
    user_image_url?: string;
    avatar_model_id?: string;
    consent_retain_photo?: boolean;
  }) =>
    request<TryOnResult>("/tryon/render", {
      method: "POST",
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
    request<AnimationTryOnResult>("/tryon/animation-render", {
      method: "POST",
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
    request<MultiGarmentTryOnResult>("/tryon/multi-render", {
      method: "POST",
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
    }>("/tryon/validate-image", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /**
   * Fit Finder size recommendation.
   *
   * Units are sent EXPLICITLY and the numbers are in that system — the server
   * converts, once. The client must not pre-convert: doing it on both sides
   * was how an inch value could be scored as centimetres.
   *
   * A resolved result with `recommended: false` is a normal outcome (the
   * engine declined to guess), not an error.
   */
  calculateNoPhotoFit: (payload: {
    product_id: number;
    units: "metric" | "imperial";
    height: number;
    weight?: number | null;
    chest?: number | null;
    waist?: number | null;
    hip?: number | null;
    shoulder?: number | null;
    inseam?: number | null;
    neck?: number | null;
    body_shape?: string | null;
    preferred_fit?: string;
    demographic?: "men" | "women" | "unisex";
  }) =>
    request<NoPhotoFitResult>("/tryon/no-photo-fit", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Mirrors backend VisualSearchRequest (schemas/tryon.py): the result-count
  // field is `top_k` (1..20, default 8) — there is no `limit` field.
  searchVisual: (payload: {
    image_url?: string;
    image_base64?: string;
    top_k?: number;
    min_price?: number;
    max_price?: number;
    brand_ids?: number[];
    in_stock_only?: boolean;
  }) =>
    request<VisualSearchResult>("/tryon/visual-search", {
      method: "POST",
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
  status: "created" | "failed" | "duplicate";
  detail?: string;
  item?: WardrobeItem;
}

export interface WardrobeUploadResponse {
  results: WardrobeUploadResultEntry[];
  summary: {
    total: number;
    succeeded: number;
    failed: number;
    duplicates_skipped: number;
  };
}

export interface WardrobeFirstOutfitItem {
  position: string;
  source: "owned" | "catalog";
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
    const q = category && category !== "All" ? `?category=${category}` : "";
    return request<WardrobeItem[]>(`/wardrobe/items${q}`);
  },

  addItem: (data: Partial<WardrobeItem>) =>
    request<WardrobeItem>("/wardrobe/items", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateItem: (itemId: number, data: Partial<WardrobeItem>) =>
    request<WardrobeItem>(`/wardrobe/items/${itemId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteItem: (itemId: number) =>
    request<{ status: string }>(`/wardrobe/items/${itemId}`, {
      method: "DELETE",
    }),

  getGapAnalysis: () => request<GapAnalysisItem[]>("/wardrobe/gap-analysis"),

  autoTagImage: (imageRef: string) => {
    // Backend contract is { image_url } for URLs or { image_base64 } for data
    // URLs — the previous payload key (image_data_url) matched neither and
    // silently 422'd.
    const body = imageRef.startsWith("data:image")
      ? { image_base64: imageRef }
      : { image_url: imageRef };
    return request<AutoTagResponse>("/wardrobe/auto-tag", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  uploadImage: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<WardrobeUploadResponse>("/wardrobe/upload", {
      method: "POST",
      body: form,
    });
  },

  uploadBulk: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<WardrobeUploadResponse>("/wardrobe/upload/bulk", {
      method: "POST",
      body: form,
    });
  },

  analyzeItem: (itemId: number) =>
    request<WardrobeItem>(`/wardrobe/items/${itemId}/analyze`, {
      method: "POST",
    }),

  getOutfitSuggestions: (occasion: string = "Smart Casual") =>
    request<WardrobeFirstOutfit>(
      `/wardrobe/outfit-suggestions?occasion=${encodeURIComponent(occasion)}`,
    ),

  checkDuplicate: (payload: {
    product_id: number;
    product_title: string;
    category: string;
    color_family: string;
    strict_mode?: boolean;
  }) =>
    request<{
      has_duplicate_risk: boolean;
      similarity_score: number;
      duplicate_item?: WardrobeItem;
      owned_item?: WardrobeItem;
      alert_message?: string;
      recommendation: string;
    }>("/wardrobe/duplicate-check", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

// 6b. Mood Boards (G1 backend, G4 surface) — real CRUD + real media upload.
// Tiles: {kind:'url', payload:{url}} | {kind:'product', payload:{product_id}}
//       | {kind:'upload', payload:{upload_id, url}} (upload_id from upload()).
export interface MoodBoardItem {
  id: number;
  kind: "url" | "product" | "upload";
  payload: Record<string, any>;
  position: number;
  created_at: string;
}

export interface MoodBoard {
  id: number;
  title: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  items: MoodBoardItem[];
}

export const moodBoardService = {
  list: () => request<MoodBoard[]>("/me/mood-boards"),

  create: (title: string, description?: string) =>
    request<MoodBoard>("/me/mood-boards", {
      method: "POST",
      body: JSON.stringify({ title, description: description || null }),
    }),

  update: (boardId: number, patch: { title?: string; description?: string }) =>
    request<MoodBoard>(`/me/mood-boards/${boardId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  remove: (boardId: number) =>
    request<{ status: string }>(`/me/mood-boards/${boardId}`, {
      method: "DELETE",
    }),

  addItem: (boardId: number, kind: MoodBoardItem["kind"], payload: Record<string, any>) =>
    request<MoodBoard>(`/me/mood-boards/${boardId}/items`, {
      method: "POST",
      body: JSON.stringify({ kind, payload }),
    }),

  removeItem: (boardId: number, itemId: number) =>
    request<MoodBoard>(`/me/mood-boards/${boardId}/items/${itemId}`, {
      method: "DELETE",
    }),

  /** Real multipart upload -> returns the stored reference (upload_id + URL).
   * The returned URL is a short-lived presigned GET when the object lives in
   * private object storage — attach it via addItem({kind:'upload', ...}). */
  upload: (boardId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ upload_id: string; url: string; content_type: string; size: number }>(
      `/me/mood-boards/${boardId}/upload`,
      { method: "POST", body: form },
    );
  },
};

// 7. Unified Commerce & BOPIS Services (G5)
export const commerceService = {
  getCart: () => request<Cart>("/commerce/cart"),

  addToCart: (productSkuId: number, quantity: number = 1, outfitId?: number) =>
    request<Cart>("/commerce/cart/items", {
      method: "POST",
      body: JSON.stringify({
        product_sku_id: productSkuId,
        quantity,
        outfit_id: outfitId,
      }),
    }),

  updateQuantity: (itemId: number, quantity: number) =>
    request<Cart>(`/commerce/cart/items/${itemId}`, {
      method: "PUT",
      body: JSON.stringify({ quantity }),
    }),

  removeFromCart: (itemId: number) =>
    request<Cart>(`/commerce/cart/items/${itemId}`, { method: "DELETE" }),

  // P0-01e: move guest-cart lines into the authenticated user's cart.
  // Server-side is lock-guarded and dedups by sku, so a repeated merge is safe.
  mergeGuestCart: (guestToken: string) =>
    request<Cart>("/commerce/cart/merge", {
      method: "POST",
      body: JSON.stringify({ guest_token: guestToken }),
    }),
  removeItem: (itemId: number) =>
    request<Cart>(`/commerce/cart/items/${itemId}`, { method: "DELETE" }),

  applyPromo: (promo_code: string) =>
    request<Cart>("/commerce/cart/promo", {
      method: "POST",
      body: JSON.stringify({ promo_code }),
    }),

  getPaymentMethods: (countryCode = "AE") =>
    request<{
      available_methods: Array<{
        id: string;
        title_en: string;
        description_en: string;
        installment_available?: boolean;
        installments_count?: number | null;
        provider_name: string;
      }>;
      currency_code: string;
    }>(
      `/commerce/payment-methods?country_code=${encodeURIComponent(countryCode)}`,
    ),

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
    guest_email?: string;
    shipping_method?: string;
    idempotency_key?: string;
  }) =>
    request<Order>("/commerce/checkout", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getOrders: () => request<Order[]>("/commerce/orders"),

  getOrderDetail: (orderNumber: string) =>
    request<Order>(`/commerce/orders/${orderNumber}`),

  getOrderTracking: (orderNumber: string) =>
    request<OrderTrackingTimeline>(`/commerce/orders/${orderNumber}/tracking`),

  createReturn: (payload: {
    order_id: number;
    item_ids: number[];
    reason: string;
    details?: string;
  }) =>
    request<any>("/commerce/returns", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

// 8. B2B Brand Management & Platform Admin Services (G6)
export const brandService = {
  requestDemo: (payload: {
    company_name: string;
    contact_name: string;
    work_email: string;
    website?: string;
    phone?: string;
    monthly_order_volume?: string;
    message?: string;
    source_path?: string;
  }) =>
    request<{
      id: number;
      status: string;
      notification_status: string;
      duplicate: boolean;
      message: string;
    }>("/brand/request-demo", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getProfile: () => request<BrandProfile>("/brand/profile"),

  getAnalytics: () => request<BrandAnalyticsDashboard>("/brand/analytics"),
  getAnalyticsDashboard: () =>
    request<BrandAnalyticsDashboard>("/brand/analytics"),

  getProducts: () => request<Product[]>("/brand/products"),

  updateSKU: (skuId: number, stockLevel: number, priceOverride?: number) => {
    const q = priceOverride ? `&price_override=${priceOverride}` : "";
    return request<any>(`/brand/skus/${skuId}?stock_level=${stockLevel}${q}`, {
      method: "PUT",
    });
  },

  updateSKUStock: (
    skuId: number,
    stockLevel: number,
    priceOverride?: number,
  ) => {
    const q = priceOverride ? `&price_override=${priceOverride}` : "";
    return request<any>(`/brand/skus/${skuId}?stock_level=${stockLevel}${q}`, {
      method: "PUT",
    });
  },

  getPlacements: () => request<any[]>("/brand/placements"),

  createPlacement: (payload: {
    product_id: number;
    placement_type: string;
    bid_amount_per_click: number;
    daily_budget: number;
  }) =>
    request<any>("/brand/placements", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getAdminAnalytics: () => request<AdminPlatformAnalytics>("/admin/analytics"),
};

// 9. Admin Service
export interface AuditTrailQuery {
  page?: number;
  page_size?: number;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  actor_id?: number;
  search?: string;
  date_from?: string;
  date_to?: string;
  only_admin_actions?: boolean;
  include_facets?: boolean;
}

const auditQuery = (params: AuditTrailQuery = {}): string => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    search.set(key, String(value));
  });
  const qs = search.toString();
  return qs ? `?${qs}` : "";
};

export const adminService = {
  getPlatformAnalytics: () =>
    request<AdminPlatformAnalytics>("/admin/analytics"),
  getBrandComparison: () => request<any[]>("/admin/analytics/brands"),
  /** Paginated, filterable audit trail (ADMIN-01). Replaces the untyped
   *  bare-list call that no view ever consumed (G-07). */
  getAuditTrail: (params: AuditTrailQuery = {}) =>
    request<AuditTrailPage>(`/admin/audit${auditQuery(params)}`),
  getAuditFacets: (params: AuditTrailQuery = {}) =>
    request<AuditFacets>(`/admin/audit/facets${auditQuery(params)}`),
  getAuditStats: (windowDays = 30) =>
    request<AuditStats>(`/admin/audit/stats?window_days=${windowDays}`),
  getAuditIntegrity: (windowDays = 30) =>
    request<AuditIntegrity>(`/admin/audit/integrity?window_days=${windowDays}`),
};
