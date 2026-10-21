export type UserRole = 'consumer' | 'brand_manager' | 'admin';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  phone?: string;
  preferred_language: string;
  is_active: boolean;
  is_verified: boolean;
  mfa_enabled: boolean;
  created_at: string;
  brand_id?: number | null;
  /** A `user_style_profiles` row exists. This is NOT the same as finishing
   *  onboarding — the row appears as soon as the wizard saves any single
   *  field. Never gate the first-run wizard on this; use
   *  `onboarding_completed` (Phase 0.2). */
  has_profile: boolean;
  /** Server-side truth: the shopper submitted the wizard to completion.
   *  Optional because a cached pre-Phase-0.2 `/auth/me` payload won't carry
   *  it — absent is treated as "not completed", which is the safe default. */
  onboarding_completed?: boolean;
  /** When that completed submission landed (ISO-8601). Null/undefined means
   *  either "never completed" or a legacy row whose instant was never
   *  recorded — never invent one. */
  onboarding_completed_at?: string | null;
  /** Which wizard revision the completion satisfied. */
  onboarding_version?: number | null;
}

export interface BodyAttributes {
  height_cm?: number;
  weight_kg?: number;
  body_shape?: string;
  chest_cm?: number;
  waist_cm?: number;
  hip_cm?: number;
  inseam_cm?: number;
  is_encrypted?: boolean;
}

export interface UserStyleProfile {
  id: number;
  user_id: number;
  style_archetypes: string[];
  preferred_colors: string[];
  avoided_colors: string[];
  fashion_aesthetics: string[];
  budget_monthly_min: number;
  budget_monthly_max: number;
  budget_per_outfit_max: number;
  preferred_brands: string[];
  blacklisted_brands: string[];
  occasion_weights: Record<string, number>;
  size_tops: string;
  size_bottoms: string;
  size_shoes: string;
  fit_preference: string;
  body_shape_tag?: string;
  body_attributes?: BodyAttributes;
  onboarding_completed: boolean;
  privacy_consent_tryon_storage: boolean;
  privacy_consent_share_with_brands: boolean;
  updated_at: string;
}

export interface Category {
  id: number;
  name: string;
  name_ar: string;
  slug: string;
  parent_id?: number | null;
  icon_name: string;
}

/**
 * One registered asset, as the catalogue API serialises it.
 *
 * `source_type` is the honesty field: `stock` means the photograph is licensed
 * editorial imagery, not the boutique's own product shot, and `attribution`
 * names whose it is. The storefront must surface that distinction rather than
 * letting a stock picture pass as first-party product photography.
 */
export interface ProductMedia {
  ratio: "4x5" | "1x1" | "3x2" | "16x9" | "master" | string;
  url: string;
  width: number;
  height: number;
  format: string;
  source_type: "stock" | "own" | "partner" | string;
  attribution?: string | null;
  is_primary: boolean;
  bytes?: number | null;
  /** Which supplied photograph this rendition belongs to (0 = hero). */
  photo_index?: number;
}

/**
 * ONE photograph of a product, with its own rendition ladder.
 *
 * `images`/`media` describe renditions of the hero only — a list keyed by
 * ratio cannot hold a second photograph, which is why a brand's back and
 * detail shots had no way onto the page. `photos` is the gallery: one entry per
 * supplied image, in the order supplied. Optional, because list payloads and
 * products whose media predates the gallery contract do not carry it.
 */
export interface ProductPhoto {
  position: number;
  is_primary: boolean;
  /** Best single frame for this photograph (its 4:5 portrait). */
  url: string;
  /** ratio -> URL for this photograph's own renditions. */
  images: Record<string, string>;
  source_ref?: string | null;
  source_type: "stock" | "own" | "partner" | string;
  provider?: string | null;
  attribution?: string | null;
  frames?: ProductMedia[];
}

export interface ProductSKU {
  id: number;
  product_id: number;
  /**
   * Internal inventory key. WITHHELD on the public product page since
   * 2026-10-20: it embeds historical brand initials ("REISS-DRS-GLD-6") and the
   * endpoint is unauthenticated. The brand-owner and admin surfaces still
   * receive it, and no consumer-side view reads it for a shopper.
   */
  sku_code?: string | null;
  size: string;
  color: string;
  color_hex: string;
  price_override?: number | null;
  stock_level: number;
  is_in_stock: boolean;
}

export interface BrandSummary {
  id: number;
  brand_name: string;
  slug: string;
  logo_url?: string;
  return_rate_benchmark: number;
  current_return_rate: number;
}

export interface SizeChartV1 {
  schema_version?: '1.0' | string;
  unit?: 'cm' | 'in' | string;
  type?: 'body' | 'garment' | string;
  fit_type?: 'slim' | 'regular' | 'relaxed' | 'oversized' | string;
  source?: string;
  notes?: string[];
  sizes?: Record<string, Record<string, [number, number] | number>>;
}

export interface BrandVerifiedDomain {
  id: number;
  hostname: string;
  status: 'pending' | 'verified' | 'revoked' | string;
  token: string;
  dns_record: string;
  imports_allowed: boolean;
  is_expired?: boolean;
  expires_at?: string | null;
  verified_at?: string | null;
  last_checked_at?: string | null;
  last_error?: string | null;
  created_at?: string | null;
}

export interface Product {
  id: number;
  brand_id: number;
  brand_name: string;
  category_id: number;
  category_name: string;
  /** Category slug for storefront deep links (/discover?category=<slug>).
   *  Served on the DETAIL payload; optional because list payloads and
   *  older cached responses do not carry it. */
  category_slug?: string;
  title: string;
  title_ar: string;
  slug: string;
  base_price: number;
  /**
   * The price previously charged, when one genuinely existed. Absent/null
   * means there is no discount to advertise. NEVER synthesise this on the
   * client: a strike-through price that was never charged is a false claim,
   * and it is regulated in several of the markets this storefront serves.
   */
  compare_at_price?: number | null;
  currency: string;
  thumbnail_url: string;
  color_family: string;
  dominant_hex: string;
  gender?: 'mens' | 'womens' | 'unisex' | string | null;
  style_tags: string[];
  occasion_tags: string[];
  price_provenance?: {
    source_currency?: string | null;
    source_amount?: number | null;
    fx_rate?: number | null;
    fx_source?: string | null;
    fx_as_of?: string | null;
  } | null;
  rating: number;
  style_compatibility_score?: number | null;
  ai_fit_score?: number | null;
  is_featured: boolean;
  description?: string;
  description_ar?: string;
  material?: string;
  care_instructions?: string;
  images?: string[];
  /**
   * Every registered asset with the facts needed to attribute it.
   *
   * The server has shipped this since the media pass, including `source_type`
   * (`stock` | `own` | `partner`) and a human `attribution` string, but the
   * client model did not declare it — so the field was dropped on parse and a
   * stock photograph was rendered exactly like the boutique's own shot. It is
   * optional because list payloads do not carry the full registry.
   */
  media?: ProductMedia[];
  /** Every supplied photograph, ordered. Empty/absent for legacy products. */
  photos?: ProductPhoto[];
  size_chart?: Record<string, any>;
  skus?: ProductSKU[];
  bnpl_monthly_installment?: number | null;
  bnpl?: {
    eligible: boolean;
    /** null when no lender may be named — see `is_estimate`. */
    provider?: string | null;
    installment_amount?: number | null;
    installments_count?: number;
    disclaimer?: string;
    /**
     * True when the split is an illustrative estimate rather than an offer from
     * a lender. The server sets it from `bnpl_is_live()`: a live PSP adapter for
     * the provider must exist before any provider is named.
     */
    is_estimate?: boolean;
    market?: string;
    method_id?: string;
  } | null;
  brand?: BrandSummary;
  related_outfits?: Array<{
    title: string;
    occasion?: string;
    compatibility_score?: number;
    items: Array<{
      product_id: number;
      product_title: string;
      brand_name?: string;
      price?: number;
      image_url?: string;
      slug?: string;
    }>;
  }>;
  recommended_size?: string | null;
  recommended_size_available?: boolean | null;
  fit_available?: boolean;
  fit_reasoning?: string | null;
  style_compatibility_available?: boolean;
  style_compatibility_reason?: string | null;
}

export interface AdminCatalogBrandSummary {
  id: number;
  brand_name: string;
  slug: string;
  is_verified: boolean;
  product_count: number;
  active_product_count: number;
  sku_count: number;
  store_count: number;
  placement_count: number;
}

export interface AdminCatalogProduct {
  id: number;
  brand_id: number;
  brand_name: string;
  category_id: number;
  category_name: string;
  category_slug: string;
  title: string;
  title_ar: string;
  slug: string;
  description: string;
  description_ar: string;
  base_price: number;
  currency: string;
  material?: string | null;
  care_instructions?: string | null;
  color_family: string;
  dominant_hex?: string | null;
  thumbnail_url: string;
  images: string[];
  style_tags: string[];
  occasion_tags: string[];
  is_featured: boolean;
  is_active: boolean;
  created_at: string;
  skus: ProductSKU[];
}

export interface AdminCatalogInventoryProduct {
  product_id: number;
  title: string;
  thumbnail_url: string;
  is_active: boolean;
  total_stock: number;
  skus: Array<ProductSKU & {
    store_inventories: Array<{
      id: number;
      store_id: number;
      store_name: string;
      quantity: number;
      reserved: number;
      available: number;
    }>;
  }>;
}

export interface AdminCatalogSnapshot {
  brand: AdminCatalogBrandSummary;
  products: AdminCatalogProduct[];
  inventory: AdminCatalogInventoryProduct[];
  placements: Array<Record<string, any>>;
  stores: Array<Record<string, any>>;
  imports: Array<Record<string, any>>;
  categories: Array<{ id: number; name: string; name_ar: string; slug: string }>;
  generated_at: string;
}

export interface StoreInventoryLocation {
  store_id: number;
  store_name: string;
  store_name_ar: string;
  address: string;
  city: string;
  country: string;
  distance_km?: number;
  quantity_available: number;
  is_available_for_pickup: boolean;
  latitude?: number;
  longitude?: number;
}

export interface OutfitItem {
  id: number;
  product_id: number;
  product_title: string;
  brand_name: string;
  category_name: string;
  price: number;
  /** Real catalogue currency (e.g. "EGP"). Absent on legacy messages —
   *  render an honest placeholder, never assume a currency. */
  currency?: string | null;
  image_url: string;
  color_hex: string;
  position: string;
  slot_type?: string;
  color_family?: string;
  material?: string;
  role_in_outfit?: string;
  sku_id?: number;
  selected_size?: string;
}

export interface Outfit {
  id: number;
  title: string;
  description?: string;
  occasion: string;
  total_price: number;
  /** Currency of total_price, from the composed items themselves. */
  currency?: string | null;
  compatibility_score: number;
  color_palette: string[];
  style_tags: string[];
  is_saved: boolean;
  is_system_curated: boolean;
  is_complete?: boolean;
  completeness_status?: string;
  completeness_label?: string;
  missing_slots?: string[];
  color_harmony_score?: number;
  formality_score?: number;
  budget_limit?: number | null;
  within_budget?: boolean;
  budget_note?: string | null;
  items: OutfitItem[];
  created_at: string;
  updated_at?: string | null;
  composition_warnings?: string[];
  /** Share state comes from the real token lifecycle (OUTFIT-01): a look is
   *  only "shared" when a live, unrevoked, unexpired token exists. */
  is_shared?: boolean;
  share_url?: string | null;
  share_expires_at?: string | null;
  share_view_count?: number;
}

/** Explainable verdict from the server composition policy. */
export interface CompositionViolation {
  code: string;
  message: string;
  positions: string[];
}

export interface CompositionVerdict {
  is_valid: boolean;
  violations: CompositionViolation[];
  warnings: string[];
  missing_positions: string[];
  resolved_items: Array<Record<string, unknown>>;
  unresolved_ids: number[];
}

export interface ShareLink {
  outfit_id: number;
  share_token: string | null;
  share_url: string | null;
  expires_at: string | null;
  is_active: boolean;
  view_count: number;
}

export interface StylistMessage {
  id: number;
  session_id: number;
  sender: 'user' | 'assistant' | 'system';
  content: string;
  audio_url?: string;
  intent_detected?: Record<string, any>;
  /**
   * Which engine produced this answer, straight from the API:
   * "<Provider> <model actually served>" | "CONFIT Grounded Styling Engine"
   * (deterministic fallback after every provider failed) | "none" (a
   * clarifying question, no engine called). The drawer shows this so a reader
   * is never told that fallback prose is a live model answer.
   */
  engine?: string | null;
  /**
   * WHY the text is what it is. "provider" (a model answered), "grounding_rejected"
   * (a model answered but named a brand outside the looks shown, so the grounded
   * description was used), "providers_unavailable", "no_provider_configured".
   */
  answer_source?: string | null;
  /** "A" (photos analysed) or "B" (text-only). Absent on older rows. */
  mode?: string | null;
  /** Set when photos were attached but this reply could not use them. */
  fallback_reason?: string | null;
  /** What the photo analysis produced. Never image bytes. Null for text turns. */
  image_analysis?: {
    available: boolean;
    engine?: string | null;
    reason?: string | null;
    images?: number;
  } | null;
  recommendations: Outfit[];
  created_at: string;
}

export interface AppliedGarmentSlot {
  product_id: number;
  product_title: string;
  brand_name: string;
  category_name: string;
  position: string;
  image_url: string;
  color_family?: string;
  color_hex?: string;
  material?: string;
  price: number;
  selected_size?: string;
  layer_order: number;
}

export interface AnimationKeyframe {
  step: number;
  slot: string;
  product_title: string;
  brand_name: string;
  image_url: string;
  status: string;
}

export interface AnimationTryOnResult {
  session_id: number;
  status: string;
  animation_style: string;
  output_aspect: string;
  rendered_animation_url: string;
  keyframes_sequence: AnimationKeyframe[];
  fit_confidence_score: number;
  body_fit_verdict: string;
  traceability_hash: string;
  ai_disclosure: string;
  dynamic_animation_prompt: string;
  applied_items: AppliedGarmentSlot[];
  total_price: number;
  /** The REAL engine the worker reported (e.g. fashn-vton-v1.5) — shown to
   *  the user instead of a hardcoded engine brand. */
  model_used?: string | null;
}

export interface GarmentLayerVerification {
  layer: number;
  product_id?: number | null;
  slot_type?: string | null;
  verify_pass?: boolean | null;
  metric_pixel_change?: number | null;
}

export interface OutfitVerification {
  all_layers_verified: boolean;
  layers_requested: number;
  layers_failed: number;
  failed_layers: GarmentLayerVerification[];
}

export interface MultiGarmentTryOnResult {
  session_id: number;
  status: string;
  user_reference_image: string;
  rendered_result_url: string;
  before_after_split_url?: string;
  applied_items: AppliedGarmentSlot[];
  total_price: number;
  fit_confidence_score: number;
  body_fit_verdict: string;
  recommended_sizes: Record<string, string>;
  ai_disclosure: string;
  traceability_hash: string;
  layering_order: string[];
  dynamic_prompt_generated?: string;
  expires_at?: string;
  // Honest per-layer verification outcome (null/absent for legacy/single-garment
  // results). all_layers_verified=false means one or more garments were NOT
  // confirmed applied by the engine — the UI must show a truthful warning.
  verification?: OutfitVerification | null;
  // How the outfit was composed on the worker: "single_call" (whole outfit in
  // one GPU call — fashn_v15 contract) or "sequential_chain" (single-garment
  // worker adaptation). Observable, never assumed.
  composition_mode?: string | null;
}

export interface TryOnResult {
  session_id: number;
  product_id: number;
  product_title: string;
  brand_name: string;
  status: string;
  original_item_image: string;
  rendered_result_url: string;
  fit_confidence_score: number;
  body_fit_verdict: string;
  recommended_size: string;
  ai_disclosure: string;
  traceability_hash: string;
  expires_at?: string;
}

/**
 * Fit Finder result — mirrors backend NoPhotoFitResponse (schemas/tryon.py).
 *
 * `recommended` is the discriminator callers MUST branch on. When it is false
 * the engine deliberately declined to name a size (no chart, no stock, not
 * enough evidence) and `reason_code` says which. That is a successful, honest
 * response — the UI must render the refusal, never fall back to a guess.
 */
export interface FitSizeChartSource {
  /**
   * Must stay in sync with ChartProvenance.source in
   * backend/app/services/fit/size_charts.py. 'product_chart_derived' is a chart
   * attached to THIS product but derived from a stated external source -- it is
   * NOT the brand's own word, and `is_brand_published` stays false for it.
   */
  source: 'brand_published' | 'product_chart_derived' | 'standard_en13402' | 'none';
  label: string;
  updated_at: string | null;
  standard: string | null;
  measurement_type: 'body' | 'garment';
  is_brand_published: boolean;
  notes: string[];
}

export interface FitSizeRow {
  size: string;
  ranges_cm: Record<string, [number, number]>;
  fit_score: number;
  fit_rating: string;
  /** Tri-state: null means availability could NOT be confirmed for this size. */
  in_stock: boolean | null;
  availability?: 'in_stock' | 'out_of_stock' | 'unknown';
  stock_level: number | null;
  is_recommended: boolean;
}

export interface FitBrandTendency {
  summary: string;
  has_published_chart: boolean;
  chart_updated_at: string | null;
  return_rate_signal: string | null;
  known_size_bias: string | null;
  known_size_bias_note: string;
}

export interface FitReturnRisk {
  label: string;
  basis: string;
  fit_score?: number;
  confidence?: number;
  note?: string;
}

export interface NoPhotoFitResult {
  product_id: number;
  recommended: boolean;
  recommended_size: string | null;
  alternative_size: string | null;
  is_between_sizes: boolean;
  /** Honest headline signal: deterministic, evidence-based. Render THIS. */
  confidence_band?: 'high' | 'medium' | 'low' | null;
  confidence_band_reason?: string | null;
  /**
   * Internal evidence tally 0-100, kept for backwards compatibility.
   * NOT a calibrated probability — never render it as "N% likely".
   */
  confidence_score: number;
  confidence_is_probability?: boolean;
  confidence_factors: string[];
  is_estimated: boolean;
  fit_verdict: string;
  confidence_disclosure: string;
  reason_code?: string | null;
  missing?: string[];
  diagnostics?: Record<string, unknown>;
  fit_breakdown: Record<string, string>;
  size_comparison_table: FitSizeRow[];
  measurements_used: Record<string, unknown> & {
    estimated_fields?: string[];
    sections_scored?: string[];
  };
  size_chart_source: FitSizeChartSource;
  garment: {
    garment_class: string;
    material: string | null;
    ease_targets_cm: Record<string, number>;
    category: string | null;
  };
  brand_sizing_tendency: FitBrandTendency;
  return_risk: FitReturnRisk;
  notes: string[];
  engine_version: string;
  /** @deprecated legacy free-text field retained for the PDP */
  return_risk_score: string;
}

export interface VisualSearchResultItem {
  product_id: number;
  title: string;
  brand_name: string;
  price: number;
  /** Sent by the API so the client never guesses the symbol. */
  currency?: string;
  image_url: string;
  similarity_score: number;
  detected_color: string;
  match_type: string;
}

export interface VisualSearchResult {
  query_id: number;
  analysis_available: boolean;
  analysis_source?: string | null;
  detected_category: string | null;
  detected_color: string | null;
  detected_pattern: string | null;
  detected_style: string | null;
  results_count: number;
  matches: VisualSearchResultItem[];
}

export interface WardrobeItem {
  id: number;
  user_id: number;
  title: string;
  category: string;
  subcategory?: string;
  color_name: string;
  color_hex: string;
  pattern: string;
  brand_name: string;
  image_url: string;
  ai_tags: string[];
  occasions: string[];
  wear_frequency: string;
  wear_count: number;
  is_favorite: boolean;
  secondary_colors?: string[];
  seasonality?: string;
  processing_status?: 'uploaded' | 'processing' | 'ready' | 'failed';
  processing_error?: string | null;
  ai_confidence?: number | null;
  created_at: string;
}

export interface GapAnalysisItem {
  id: number;
  missing_category: string;
  missing_subcategory: string;
  suggested_colors: string[];
  rationale: string;
  unlocks_outfit_count: number;
  /** Ready-item counts per category the estimate/rationale are computed from. */
  owned_counts?: Record<string, number>;
  recommended_products: Array<{
    product_id: number;
    title: string;
    brand_name: string;
    price: number;
    /** Sent alongside the price so the client never guesses the symbol. */
    currency?: string;
    image_url: string;
  }>;
}

export interface CartItem {
  id: number;
  product_sku_id: number;
  product_id: number;
  product_title: string;
  product_title_ar: string;
  brand_name: string;
  size: string;
  color: string;
  unit_price: number;
  quantity: number;
  subtotal: number;
  image_url: string;
  ai_fit_verdict: string;
  outfit_id?: number | null;
}

export interface Cart {
  id: number;
  items: CartItem[];
  subtotal: number;
  discount_amount: number;
  tax_amount: number;
  shipping_amount: number;
  total: number;
  currency: string;
  items_count: number;
  bnpl_monthly_quote: number;
  /**
   * True when the instalment figure is an illustrative estimate: the server sets
   * it from `bnpl_is_live()` (a live PSP adapter must exist before a lender is
   * named). Optional because older cached payloads predate the field, which the
   * call sites treat as an estimate — the safe direction.
   */
  bnpl_is_estimate?: boolean;
  promo_code?: string | null;
  brands?: string[];
  fit_summary?: Array<{
    cart_item_id: number;
    title: string;
    size?: string;
    verdict: string;
    size_confirmed?: boolean;
  }>;
  outfit_groups?: Array<{ outfit_id: number; item_ids: number[] }>;
}

export interface OrderItem {
  id: number;
  product_id: number;
  product_title: string;
  brand_name: string;
  size: string;
  color: string;
  unit_price: number;
  quantity: number;
  subtotal: number;
  is_returned: boolean;
}

export interface Order {
  id: number;
  order_number: string;
  status: string;
  total_amount: number;
  subtotal_amount: number;
  discount_amount: number;
  tax_amount: number;
  shipping_amount: number;
  currency: string;
  payment_method: string;
  payment_status: string;
  payment_installments: number;
  fulfillment_type: string;
  bopis_store_name?: string | null;
  bopis_pickup_code?: string | null;
  shipping_recipient_name?: string | null;
  shipping_address_line?: string | null;
  shipping_city?: string | null;
  tracking_number?: string | null;
  estimated_delivery_date?: string | null;
  try_on_assisted: boolean;
  stylist_assisted: boolean;
  items: OrderItem[];
  created_at: string;
  user_id?: number | null;
  guest_email?: string | null;
  promo_code?: string | null;
  payment_mode?: string | null;
  shipping_method?: string | null;
  fulfillment_groups?: Array<Record<string, unknown>>;
  outfit_groups?: Array<Record<string, unknown>>;
}

export interface TrackingMilestone {
  status_key: string;
  title: string;
  description: string;
  timestamp?: string;
  is_completed: boolean;
  is_current: boolean;
}

export interface OrderTrackingTimeline {
  order_number: string;
  current_status: string;
  estimated_delivery?: string;
  carrier?: string | null;
  tracking_number?: string;
  timeline: TrackingMilestone[];
  bopis_store_info?: {
    name: string;
    address: string;
    city: string;
    pickup_instructions: string;
    pickup_code: string;
  } | null;
  shipments?: Array<{
    carrier?: string;
    tracking_number?: string;
    status?: string;
  }>;
}

export interface BrandProfile {
  id: number;
  user_id: number;
  brand_name: string;
  slug: string;
  logo_url?: string;
  banner_url?: string;
  description?: string;
  website?: string;
  commission_rate: number;
  return_rate_benchmark: number;
  current_return_rate: number;
  is_verified: boolean;
  publication_status?: string;
  created_at: string;
}

export interface SponsoredPlacement {
  id: number;
  brand_id: number;
  product_id: number;
  product_title: string;
  placement_type: string;
  bid_amount_per_click: number;
  daily_budget: number;
  spent_today: number;
  status: string;
  impressions: number;
  clicks: number;
  conversions: number;
  revenue_generated: number;
  created_at: string;
}

export interface BrandAnalyticsDashboard {
  data_source: string;
  methodology: string;
  return_cohorts: { methodology: string; non_tryon_items: number; tryon_items: number };
  brand_name: string;
  total_products_count: number;
  total_skus_count: number;
  total_views: number;
  total_tryons: number;
  total_add_to_carts: number;
  total_purchases: number;
  /** null = not measurable (zero views). Never render null as 0%. */
  funnel_conversion_rate: number | null;
  return_rate_before_vton: number | null;
  return_rate_after_vton: number | null;
  return_reduction_percentage: number | null;
  outfit_appearance_rankings: Array<{
    product_id: number;
    product_title: string;
    thumbnail_url: string;
    outfit_appearances: number;
    add_to_cart_rate: number;
    purchase_rate: number;
  }>;
  bopis_store_fulfillment_rate: number | null;
  ad_spend_total: number;
  ad_revenue_total: number;
}

export interface FacetCount {
  label: string;
  value: string;
  count: number;
  selected?: boolean;
}

export interface PriceRangeFacet {
  min_price: number;
  max_price: number;
  avg_price: number;
}

export interface SearchFacets {
  categories: FacetCount[];
  brands: FacetCount[];
  colors: FacetCount[];
  price_range: PriceRangeFacet;
}

export interface SearchResultItem extends Product {
  relevance_score: number;
  matched_field: string;
  highlighted_snippet?: string;
  in_stock: boolean;
}

export interface SearchResponse {
  query: string;
  total_matches: number;
  page: number;
  limit: number;
  results: SearchResultItem[];
  facets: SearchFacets;
  did_you_mean?: string;
  execution_time_ms: number;
}

export interface AutocompleteSuggestion {
  title: string;
  type: 'product' | 'category' | 'brand';
  slug_or_query: string;
  subtitle?: string;
  thumbnail_url?: string;
}

export interface AutocompleteResponse {
  query: string;
  suggestions: AutocompleteSuggestion[];
}

/**
 * One published cell of a style-signal aggregate.
 *
 * Every dimension uses this ONE shape (G-04): the backend previously emitted
 * `{name, share}` from the dashboard endpoint and `{name, weight, count}` from
 * the standalone heatmap endpoint, and colours as `string[]` in one and
 * `{color, weight, count}[]` in the other — so the dashboard rendered
 * `undefined%` bars and then threw on `trending_colors.map`.
 */
export interface StyleHeatmapCell {
  name: string;
  /** Value exactly as stored, before any display casing. */
  raw_name?: string;
  /** Percentage of ALL occurrences in this dimension, not just the top-N. */
  share: number;
  count: number;
}

export interface StyleHeatmap {
  /** Display label. "Platform-wide" unless a real region predicate ran. */
  region: string;
  region_scope?: string;
  region_filter_applied?: boolean;
  /** Window actually applied to the SQL predicate; nulls mean unbounded. */
  period?: { from: string | null; to: string | null } | null;
  /** Outfits actually aggregated — never inflated to a user count. */
  sample_size?: number;
  min_sample_required?: number;
  k_anonymity_floor?: number;
  /** False => every list is empty BY DESIGN; render the reason, not a chart. */
  data_available?: boolean;
  top_aesthetics: StyleHeatmapCell[];
  trending_colors: StyleHeatmapCell[];
  top_occasions: StyleHeatmapCell[];
  suppressed_cells?: number;
  privacy_threshold?: string;
  methodology?: string;
  limitations?: string[];
}

export interface AdminPlatformAnalytics {
  total_users_count: number;
  total_brands_count: number;
  /** Null when the selected orders contain multiple currencies. */
  total_gmv: number | null;
  currency?: string | null;
  currency_status?: 'no_data' | 'single_currency' | 'mixed_currencies';
  gmv_by_currency?: Record<string, number>;
  attribution_by_currency?: Record<string, Record<string, number>>;
  total_orders: number;
  /**
   * P1 honesty contract: null = the denominator was zero, nothing was
   * measured — render N/A. A 0 here is a REAL measured zero.
   */
  tryon_adoption_rate: number | null;
  stylist_conversion_ratio: number | null;
  platform_avg_return_rate: number | null;
  return_rate_tryon_users: number | null;
  return_rate_non_tryon_users: number | null;
  revenue_attribution: Record<string, number | null>;
  /** Operational metrics vs billing ledger — echoed from the backend. */
  financial_semantics?: string;
  top_performing_brands: Array<{
    brand_id?: number;
    brand: string;
    products?: number;
    views?: number;
    tryons?: number;
    orders: number;
    conversion_rate?: number;
    tryon_rate: string;
    return_rate: string;
    return_rate_value?: number;
  }>;
  style_preference_heatmap: StyleHeatmap;
  most_styled_items?: Array<{
    product_id: number;
    title: string;
    brand_name: string;
    thumbnail_url: string;
    appearances: number;
    outfit_count?: number;
  }>;
  outfit_to_purchase_ratio?: number;
  /**
   * Spec 12 §6.2 — the server's own description of the analysed window
   * (TimeRange.describe() in backend/app/core/timeutils.py). Rendering it
   * verbatim is what makes every number auditable: source + bounds.
   */
  time_range?: {
    source: string;
    date_from: string | null;
    date_to: string | null;
    date_to_inclusive?: boolean;
    is_all_time: boolean;
  };
  /** Echoed by the backend: what counts as revenue (accrual basis note). */
  revenue_basis?: string;
  revenue_excludes_statuses?: string[];
  methodology?: Record<string, unknown>;
}

export type TryOnJobStatusType =
  | 'queued'
  | 'parsing_person'
  | 'warping_garment'
  | 'diffusion_rendering'
  | 'harmonizing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface TryOnJobDelivery {
  download_url: string;
  token: string;
  expires_at?: string | null;
  content_type?: string | null;
  byte_size?: number | null;
  ttl_seconds?: number | null;
  one_time?: boolean;
}

export interface TryOnJob {
  id: number;
  job_id: string;
  status: TryOnJobStatusType;
  progress_pct: number;
  current_stage: string;
  model_used: string;
  /** Never a stored reference — generated try-on images are not persisted. */
  output_image_url?: string | null;
  /**
   * Guaranteed in-response delivery of the generated image (completion
   * response only). Render directly from this value and offer it for
   * download client-side — it is not retained by the server.
   */
  result_image_data_url?: string | null;
  /** One-shot, TTL-bounded, owner-only download (best effort on serverless). */
  delivery?: TryOnJobDelivery | null;
  delivery_expires_at?: string | null;
  metrics: Record<string, any>;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface GarmentAsset {
  id: number;
  product_id: number;
  slot_type: string;
  flat_image_url: string;
  segmented_garment_url?: string;
  garment_mask_url?: string;
  created_at: string;
}

/* ------------------------------------------------------------------ *
 * Platform audit trail (ADMIN-01 / gap register G-05, G-07)
 *
 * Mirrors backend/app/schemas/audit.py field-for-field. This contract is
 * deliberately explicit: the heatmap types above drifted from the backend
 * (weight vs share, top_colors vs trending_colors) and the admin dashboard
 * rendered `undefined%` as a result (G-04).
 * ------------------------------------------------------------------ */

export interface AuditEntry {
  id: number;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  actor: string;
  actor_id?: number | null;
  actor_email?: string | null;
  actor_role?: string | null;
  ip_address?: string | null;
  request_id?: string | null;
  details?: string | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  changed_fields: string[];
  timestamp?: string | null;
}

export interface AuditPageMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface AuditFacetValue {
  value: string;
  count: number;
  actor_id?: number | null;
  role?: string | null;
}

export interface AuditFacets {
  actions: AuditFacetValue[];
  resource_types: AuditFacetValue[];
  actors: AuditFacetValue[];
  oldest?: string | null;
  newest?: string | null;
}

export interface AuditTrailPage {
  items: AuditEntry[];
  meta: AuditPageMeta;
  filters: Record<string, unknown>;
  facets?: AuditFacets | null;
  request_id?: string | null;
  methodology?: string;
}

export interface AuditViolation {
  row_id: number | null;
  issue: string;
  action?: string;
  detail?: string;
}

/** Hash-chain verification block (migration 0020, core/audit_chain.py). */
export interface AuditChain {
  chained_rows: number;
  unchained_rows: number;
  /** id of the first chained row; unchained rows AFTER it are suspicious. */
  first_chained_row_id?: number | null;
  /** Unchained rows written AFTER chaining began — possible write-path bypass. */
  bypass_suspected_rows?: number;
  breaks: AuditViolation[];
  head_hash?: string | null;
  key_version: number;
  canonical_version: number;
}

/**
 * Explicit verification coverage (2026-09-24 re-audit): the dashboard check
 * is a WINDOW SAMPLE — this block exists so no consumer can present it as a
 * full-history guarantee. Full history is verified by an offline procedure.
 */
export interface AuditCoverage {
  mode: string;
  window_days: number;
  sample_limit: number;
  sampled_rows: number;
  rows_in_window: number;
  window_anchored_to_predecessor: boolean;
  full_history: boolean;
  full_history_procedure?: string;
}

export interface AuditIntegrity {
  checked_rows: number;
  window_days: number;
  sampled_rows?: number;
  violations: AuditViolation[];
  unresolved_actors: number;
  redaction_markers: number;
  rows_with_before_after: number;
  rows_with_request_id: number;
  rows_with_ip: number;
  distinct_actors?: number;
  verdict: string;
  /**
   * Computed by the backend from real chain verification: true only when
   * HMAC-chained rows exist in the sample and the chain verifies. Never
   * asserted from configuration alone.
   */
  tamper_evident: boolean;
  coverage?: AuditCoverage | null;
  chain?: AuditChain | null;
  /** 0023 HMAC-chain status for persisted verification results themselves. */
  verification_runs?: {
    coverage_mode: string;
    sample_limit: number;
    sampled_rows: number;
    signed_rows: number;
    unsigned_rows: number;
    first_signed_run_id?: number | null;
    forgery_suspected_rows: number;
    breaks: Array<{ run_id?: number | null; issue: string; detail?: string }>;
    malformed_crosslinks?: number;
    anchor?: {
      audit_row_id?: number | null;
      run_id?: number | null;
      verdict: string;
      detail?: string;
    } | null;
    intact: boolean;
    head_hash?: string | null;
    canonical_version: number;
  } | null;
  verification_run?: {
    id: number;
    run_hash: string;
    previous_run_hash: string;
    hmac_key_version: number;
  } | null;
  limitations: string[];
}

export interface AuditStats {
  window_days: number;
  total_events: number;
  by_action: AuditFacetValue[];
  by_resource_type: AuditFacetValue[];
  by_actor: AuditFacetValue[];
  by_day: Array<{ day: string; count: number }>;
  distinct_actors: number;
  admin_action_events: number;
  methodology?: string;
}


/**
 * One sold line as the OWNING BRAND sees it.
 *
 * Money is carried as strings, exactly as the API sends them: the backend
 * computes in Decimal and apportions the order discount with the
 * largest-remainder method, and converting to JS `number` here would undo
 * that precision for the sake of display convenience.
 */
export interface BrandOrderLine {
  line_id: number;
  order_id: number;
  order_number: string;
  placed_at: string | null;
  order_status: string;
  fulfillment_status: string | null;
  fulfillment_type: string;
  tracking_number: string | null;
  payment_status: string;
  payment_method: string;
  /** Shipping recipient, account holder, or a masked guest address. */
  customer_name: string;
  customer_city: string | null;
  product_id: number;
  product_title: string;
  thumbnail_url: string | null;
  sku_code: string | null;
  size: string;
  color: string;
  quantity: number;
  /** null = the SKU row is gone, so remaining stock is UNKNOWN, not zero. */
  sku_stock_remaining: number | null;
  store_id: number | null;
  store_name: string | null;
  currency: string;
  unit_price: string;
  gross_amount: string;
  discount_amount: string;
  net_amount: string;
  promo_code: string | null;
  is_returned: boolean;
}

export interface BrandOrderLinesResponse {
  lines: BrandOrderLine[];
  pagination: {
    limit: number;
    offset: number;
    returned: number;
    total_lines: number;
    has_more: boolean;
  };
  /** Computed over the WHOLE filtered set, never just the current page. */
  totals: {
    orders: number;
    lines: number;
    units: number;
    gross_amount: string;
    discount_amount: string;
    net_amount: string;
  };
  filters: Record<string, unknown>;
}

// ============================================================================
// Customer Brand Discovery, Store Locator & Branch-Level Product Availability
// ============================================================================

export interface BrandPromotion {
  id: number;
  code: string;
  description: string;
  discount_type: 'percent' | 'fixed';
  discount_value: number;
  min_order_amount: number;
  currency: string;
  starts_at?: string | null;
  expires_at?: string | null;
  is_active: boolean;
}

export interface StoreBranchSummary {
  id: number;
  brand_id: number;
  brand_name: string;
  brand_slug: string;
  name: string;
  name_ar: string;
  address: string;
  city: string;
  country: string;
  latitude: number;
  longitude: number;
  phone?: string | null;
  pickup_instructions?: string | null;
  is_bopis_enabled: boolean;
  distance_km?: number | null;
  google_maps_url: string;
  in_stock_skus_count: number;
  active_promotions: BrandPromotion[];
}

export interface CustomerBrand {
  id: number;
  brand_name: string;
  slug: string;
  logo_url?: string | null;
  banner_url?: string | null;
  description?: string | null;
  description_ar?: string | null;
  website?: string | null;
  is_verified: boolean;
  return_rate_benchmark: number;
  current_return_rate: number;
  total_products: number;
  stores_count: number;
  cities: string[];
  categories: string[];
  active_promotions_count: number;
  promotions: BrandPromotion[];
  sample_products: Product[];
}

export interface CustomerBrandDetail extends CustomerBrand {
  stores: StoreBranchSummary[];
  all_promotions: BrandPromotion[];
}

export interface BranchSKUAvailability {
  sku_id: number;
  sku_code: string;
  size: string;
  color: string;
  color_hex: string;
  quantity_available: number;
  reserved_quantity: number;
  is_in_stock: boolean;
  availability_status: 'in_stock' | 'low_stock' | 'out_of_stock';
}

export interface BranchProductItem extends Product {
  branch_id: number;
  branch_name: string;
  branch_total_units: number;
  branch_in_stock: boolean;
  branch_availability_status: 'in_stock' | 'low_stock' | 'out_of_stock';
  branch_skus: BranchSKUAvailability[];
  discount_percent?: number | null;
}

export interface BranchInventoryCatalog {
  store: StoreBranchSummary;
  brand: BrandSummary;
  total_items: number;
  products: BranchProductItem[];
  categories: string[];
  available_sizes: string[];
  active_promotions: BrandPromotion[];
}

export interface BrandRegistrationPayload {
  brand_name: string;
  email: string;
  password: string;
  full_name: string;
  phone?: string;
  description?: string;
  description_ar?: string;
  website?: string;
  logo_url?: string;
  country?: string;
  city?: string;
  preferred_language?: string;
}

export interface BrandRegistrationResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  brand: BrandProfile;
  message: string;
  status: 'created' | 'existing';
  next_step: string;
  is_verified: boolean;
}

export interface BrandOnboardingStep {
  key: string;
  title: string;
  description: string;
  is_completed: boolean;
  action_url: string;
}

export interface BrandOnboardingStatus {
  brand_id: number;
  brand_name: string;
  is_verified: boolean;
  is_published: boolean;
  publication_status: 'active' | 'pending_review' | 'draft';
  welcome_message: string;
  primary_cta_label: string;
  primary_cta_url: string;
  completed_steps_count: number;
  total_steps_count: number;
  completion_percentage: number;
  steps: BrandOnboardingStep[];
  stores_count: number;
  products_count: number;
  active_promotions_count: number;
}

export interface PartnerStoreDetail {
  id: number;
  brand_id: number;
  name: string;
  name_ar: string;
  city: string;
  country: string;
  address: string;
  latitude: number;
  longitude: number;
  phone?: string | null;
  pickup_instructions?: string | null;
  is_bopis_enabled: boolean;
  is_location_verified: boolean;
  inventory_items_count: number;
  total_stock_units: number;
  google_maps_url: string;
  created_at: string;
}

export interface CatalogImportPreviewRecord {
  row_number: number;
  status: 'valid' | 'warning' | 'error';
  action: 'create' | 'update' | 'error';
  product_name: string;
  sku: string;
  category: string;
  price: string;
  original_price?: string | null;
  currency: string;
  stock: number;
  size: string;
  color: string;
  /** mens | womens | unisex — the value the stylist filters on. */
  gender?: string;
  thumbnail_url?: string;
  branch_id?: number | null;
  error_message?: string;
}

export interface CatalogImportPreviewResponse {
  total_rows: number;
  valid_rows_count: number;
  error_rows_count: number;
  warning_rows_count: number;
  duplicate_rows_count: number;
  can_import: boolean;
  /** Reasons NOTHING would land (no storage, disabled image source, …).
   *  `can_import` is false whenever this is non-empty. */
  blocked_reasons?: string[];
  preview_records: CatalogImportPreviewRecord[];
  errors: Array<{
    row: number;
    field: string;
    message: string;
    value?: string | null;
    suggestion?: string;
  }>;
  warnings: Array<{
    row: number;
    field: string;
    message: string;
    /** Row 0/1 = a file-level note; >1 is a data row. */
    blocking?: boolean;
  }>;
}

export interface CatalogImportResult {
  job_id: number;
  /**
   * The five states the job table constrains. `queued` is a real state now that
   * the import runs on a worker: the endpoint persists the job and returns
   * before any row is touched, so a fresh job is queued, not processing.
   */
  status: 'queued' | 'processing' | 'completed' | 'partially_completed' | 'failed';
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  /** Rows the worker has actually handled so far, persisted as it goes. */
  processed_rows?: number;
  /** How many times a worker has claimed the job (bounded by the server). */
  attempts?: number;
  /** Why the last attempt failed, when there is one. */
  last_error?: string | null;
  /** Where this job can be polled; returned by the acceptance response. */
  status_url?: string;
  notifications_queued?: number;
  notification_recipients_count?: number;
  /** Derived completeness facts the API already returns — surfaced so the
   *  summary cannot claim success while hiding an untranslated catalogue. */
  media_rows_registered?: number;
  rows_missing_title_ar?: number;
  rows_missing_description_ar?: number;
  rows_gender_inferred?: number;
  /** Photographs supplied but not imported (one entry per dropped image). */
  photos_not_imported?: number;
  media_warnings?: Array<{ row?: number | null; field?: string; message: string }>;
  errors?: any[];
}

// -------------------------------------------------------------------------
// Business Intelligence & Advanced Analytics Models
// -------------------------------------------------------------------------
export interface BiKpis {
  gross_sales: number;
  net_sales: number;
  discount_total: number;
  returned_value: number;
  orders_count: number;
  units_sold: number;
  returned_units: number;
  average_order_value: number;
  return_rate: number | null;
  tryon_assisted_orders: number;
  tryon_share_pct: number | null;
  currency: string;
}

export interface BiTrendPoint {
  date: string;
  orders: number;
  units: number;
  gross_sales: number;
  net_sales: number;
}

export interface BiCategoryItem {
  category_id: number;
  category_name: string;
  category_name_ar?: string;
  units_sold: number;
  gross_sales: number;
  share_pct: number;
}

export interface BiProductItem {
  product_id: number;
  title: string;
  category: string;
  base_price: number;
  currency: string;
  units_sold: number;
  gross_sales: number;
  returned_units: number;
  return_rate: number | null;
  stock_level: number;
}

export interface BiBranchItem {
  store_id: number;
  name: string;
  name_ar?: string;
  city: string;
  country: string;
  address: string;
  is_bopis_enabled: boolean;
  orders_count: number;
  units_sold: number;
  gross_sales: number;
  available_stock: number;
  reserved_stock: number;
  low_stock_skus: number;
}

export interface BiReplenishmentItem {
  sku_id: number;
  sku_code: string;
  product_id: number;
  product_title: string;
  size: string;
  color: string;
  stock_level: number;
  status: 'out_of_stock' | 'low_stock';
  recommended_reorder: number;
}

export interface BiInventoryHealth {
  total_skus: number;
  total_warehouse_units: number;
  total_branch_bopis_units: number;
  in_stock_count: number;
  low_stock_count: number;
  out_of_stock_count: number;
  replenishment_items: BiReplenishmentItem[];
}

export interface BiPromotionItem {
  id: number;
  code: string;
  description?: string;
  discount_type: string;
  discount_value: number;
  is_active: boolean;
  is_expired: boolean;
  redemptions: number;
  total_discount: number;
  revenue_generated: number;
}

export interface BiInsightItem {
  type: string;
  severity: 'positive' | 'warning' | 'alert' | 'info';
  title: string;
  message: string;
}

export interface BiDashboardResponse {
  brand: {
    id: number;
    name: string;
    slug: string;
    commission_rate: number;
    return_rate_benchmark: number;
    current_return_rate: number;
  };
  generated_at: string;
  period: {
    from: string | null;
    to: string | null;
    label: string;
    comparison_from: string | null;
    comparison_to: string | null;
    comparison_label: string | null;
  };
  filters: {
    branch_id?: number | null;
    category_id?: number | null;
  };
  kpis: BiKpis;
  comparison_kpis?: BiKpis | null;
  growth: Record<string, number | null>;
  /** Why each growth figure is a number, or absent.
   *  `ok` | `no_prior_baseline` (P=0, C>0) | `no_activity` (both 0) |
   *  `not_comparable` (a period was not measured). Never render a null as 0%. */
  growth_basis?: Record<string, 'ok' | 'no_prior_baseline' | 'no_activity' | 'not_comparable'>;
  trends: BiTrendPoint[];
  categories: BiCategoryItem[];
  products: BiProductItem[];
  branches: BiBranchItem[];
  inventory: BiInventoryHealth;
  promotions: BiPromotionItem[];
  insights: BiInsightItem[];
  methodology: string;
}

export interface AdminBiBrandPerformance {
  brand_id: number;
  brand_name: string;
  slug: string;
  is_verified: boolean;
  products_count: number;
  stores_count: number;
  orders_count: number;
  gross_sales: number;
  currency: string;
  return_rate: number | null;
}

export interface AdminBiDashboardResponse {
  period: {
    from: string | null;
    to: string | null;
    label: string;
    comparison_label?: string | null;
  };
  kpis: BiKpis;
  comparison_kpis?: BiKpis | null;
  growth: Record<string, number | null>;
  /** Why each growth figure is a number, or absent.
   *  `ok` | `no_prior_baseline` (P=0, C>0) | `no_activity` (both 0) |
   *  `not_comparable` (a period was not measured). Never render a null as 0%. */
  growth_basis?: Record<string, 'ok' | 'no_prior_baseline' | 'no_activity' | 'not_comparable'>;
  gmv_by_currency: Record<string, number>;
  brands_performance: AdminBiBrandPerformance[];
  trends: BiTrendPoint[];
  total_brands: number;
  generated_at: string;
}




