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
  has_profile: boolean;
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

export interface ProductSKU {
  id: number;
  product_id: number;
  sku_code: string;
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

export interface Product {
  id: number;
  brand_id: number;
  brand_name: string;
  category_id: number;
  category_name: string;
  title: string;
  title_ar: string;
  slug: string;
  base_price: number;
  currency: string;
  thumbnail_url: string;
  color_family: string;
  dominant_hex: string;
  style_tags: string[];
  occasion_tags: string[];
  rating: number;
  style_compatibility_score?: number | null;
  ai_fit_score?: number | null;
  is_featured: boolean;
  description?: string;
  description_ar?: string;
  material?: string;
  care_instructions?: string;
  images?: string[];
  size_chart?: Record<string, any>;
  skus?: ProductSKU[];
  bnpl_monthly_installment?: number | null;
  bnpl?: {
    eligible: boolean;
    provider?: string | null;
    installment_amount?: number | null;
    installments_count?: number;
    disclaimer?: string;
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
  source: 'brand_published' | 'standard_en13402' | 'none';
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
  funnel_conversion_rate: number;
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
  total_gmv: number;
  total_orders: number;
  tryon_adoption_rate: number;
  stylist_conversion_ratio: number;
  platform_avg_return_rate: number;
  return_rate_tryon_users: number;
  return_rate_non_tryon_users: number;
  revenue_attribution: Record<string, number>;
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
  row_id: number;
  issue: string;
  action?: string;
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
  /** Always false today: audit_logs has no persisted hash chain. */
  tamper_evident: boolean;
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
