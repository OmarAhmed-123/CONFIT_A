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
  style_compatibility_score: number;
  ai_fit_score: number;
  is_featured: boolean;
  description?: string;
  description_ar?: string;
  material?: string;
  care_instructions?: string;
  images?: string[];
  size_chart?: Record<string, any>;
  skus?: ProductSKU[];
  bnpl_monthly_installment?: number;
  brand?: BrandSummary;
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
  items: OutfitItem[];
  created_at: string;
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

export interface NoPhotoFitResult {
  product_id: number;
  recommended_size: string;
  confidence_score: number;
  fit_breakdown: Record<string, string>;
  size_comparison_table: Array<{
    size: string;
    chest: string;
    waist: string;
    fit_rating: string;
  }>;
  brand_sizing_tendency: string;
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
  detected_category: string;
  detected_color: string;
  detected_pattern: string;
  detected_style: string;
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
  created_at: string;
}

export interface GapAnalysisItem {
  id: number;
  missing_category: string;
  missing_subcategory: string;
  suggested_colors: string[];
  rationale: string;
  unlocks_outfit_count: number;
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
  carrier: string;
  tracking_number?: string;
  timeline: TrackingMilestone[];
  bopis_store_info?: {
    name: string;
    address: string;
    city: string;
    pickup_instructions: string;
    pickup_code: string;
  } | null;
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
  brand_name: string;
  total_products_count: number;
  total_skus_count: number;
  total_views: number;
  total_tryons: number;
  total_add_to_carts: number;
  total_purchases: number;
  funnel_conversion_rate: number;
  return_rate_before_vton: number;
  return_rate_after_vton: number;
  return_reduction_percentage: number;
  outfit_appearance_rankings: Array<{
    product_id: number;
    product_title: string;
    thumbnail_url: string;
    outfit_appearances: number;
    add_to_cart_rate: number;
    purchase_rate: number;
  }>;
  bopis_store_fulfillment_rate: number;
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
    brand: string;
    orders: number;
    tryon_rate: string;
    return_rate: string;
  }>;
  style_preference_heatmap: {
    region: string;
    top_aesthetics: Array<{ name: string; share: number }>;
    trending_colors: string[];
  };
}
