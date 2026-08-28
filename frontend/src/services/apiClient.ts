const API_BASE_URL = '/api/v1';

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, any>;

  constructor(message: string, code = 'API_ERROR', status = 500, details = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

// Generate or retrieve persistent guest session token
export const getSessionToken = (): string => {
  let token = localStorage.getItem('confit_session_token');
  if (!token) {
    token = 'sess_' + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
    localStorage.setItem('confit_session_token', token);
  }
  return token;
};

export const getAuthToken = (): string | null => {
  const token = localStorage.getItem('confit_access_token');
  if (!token || token === 'null' || token === 'undefined' || token.trim() === '') {
    return null;
  }
  return token.trim();
};

export const setAuthTokens = (access: string, refresh: string) => {
  localStorage.setItem('confit_access_token', access);
  localStorage.setItem('confit_refresh_token', refresh);
};

export const clearAuthTokens = () => {
  localStorage.removeItem('confit_access_token');
  localStorage.removeItem('confit_refresh_token');
  localStorage.removeItem('confit_user');
};

export async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  // Inject session token for guest carts and anonymous session identification
  headers.set('X-Session-Token', getSessionToken());

  // Attach Authorization Bearer token strictly when a valid token exists
  const token = getAuthToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (res.ok) {
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        return await res.json();
      }
      // A 200 with a non-JSON body means the request never reached the API
      // (e.g. static hosting returned index.html). That is an error — it must
      // never be parsed as a payload or routed into a fabricated fallback.
      throw new ApiError(
        'The server returned a non-JSON response. The API may not be deployed.',
        'API_NOT_REACHABLE',
        res.status
      );
    }

    // If endpoint returned 404, 405 (Method Not Allowed on static CDN), or non-JSON HTML
    if (res.status === 404 || res.status === 405 || !res.ok) {
      const fallbackResult = handleEdgeFallback<T>(endpoint, options);
      if (fallbackResult !== null) {
        return fallbackResult;
      }

      let errJson: any = {};
      try {
        errJson = await res.json();
      } catch (e) {}

      const err = errJson.error || {};
      let userFriendlyMessage = err.message || `Request failed with status ${res.status}`;

      if (res.status === 401 || (userFriendlyMessage && userFriendlyMessage.toLowerCase().includes('bearer token'))) {
        userFriendlyMessage = 'Sign in to access your personal style profile and account features.';
      }

      throw new ApiError(
        userFriendlyMessage,
        err.code || (res.status === 401 ? 'AUTH_REQUIRED' : 'HTTP_ERROR'),
        res.status,
        err.details || {}
      );
    }

    return await res.json();
  } catch (err: any) {
    if (err instanceof ApiError) {
      throw err;
    }
    const fallbackResult = handleEdgeFallback<T>(endpoint, options);
    if (fallbackResult !== null) {
      return fallbackResult;
    }
    throw new ApiError(err.message || 'Network communication failure', 'NETWORK_ERROR', 0);
  }
}

const FALLBACK_PRODUCTS = [
  {
    id: 1,
    title: 'Tailored Italian Wool Double-Breasted Blazer',
    title_ar: 'سترة بليزر صوف إيطالي بصدر مزدوج',
    slug: 'tailored-italian-wool-double-breasted-blazer',
    brand_id: 1,
    brand_name: 'Massimo Dutti',
    category_id: 1,
    category_name: 'Outerwear',
    base_price: 289.0,
    currency: 'USD',
    material: '100% Virgin Wool',
    care_instructions: 'Specialist Dry Clean Only',
    color_family: 'Navy Blue',
    dominant_hex: '#1B1F3B',
    thumbnail_url: 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=700',
    images: ['https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=700'],
    style_tags: ['smart_casual', 'quiet_luxury', 'formal', 'tailored'],
    occasion_tags: ['wedding', 'formal', 'work', 'business', 'dinner', 'party'],
    rating: 4.9,
    style_compatibility_score: 96,
    is_featured: true,
    skus: [
      { id: 1, sku_code: 'MD-BLZ-NVY-S', size: 'S', color: 'Navy Blue', color_hex: '#1B1F3B', stock_level: 12 },
      { id: 2, sku_code: 'MD-BLZ-NVY-M', size: 'M', color: 'Navy Blue', color_hex: '#1B1F3B', stock_level: 18 },
      { id: 3, sku_code: 'MD-BLZ-NVY-L', size: 'L', color: 'Navy Blue', color_hex: '#1B1F3B', stock_level: 15 },
    ],
  },
  {
    id: 2,
    title: 'Tuxedo Peak Lapel Evening Dinner Jacket',
    title_ar: 'سترة توكسيدو سهرة بياقة ساتان مدببة',
    slug: 'tuxedo-peak-lapel-evening-dinner-jacket',
    brand_id: 3,
    brand_name: 'Reiss',
    category_id: 1,
    category_name: 'Outerwear',
    base_price: 395.0,
    currency: 'USD',
    material: 'Wool Silk Blend',
    care_instructions: 'Dry Clean Only',
    color_family: 'Midnight Black',
    dominant_hex: '#111111',
    thumbnail_url: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700',
    images: ['https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700'],
    style_tags: ['formal', 'evening', 'quiet_luxury'],
    occasion_tags: ['wedding', 'gala', 'black_tie', 'party'],
    rating: 4.9,
    style_compatibility_score: 98,
    is_featured: true,
    skus: [
      { id: 4, sku_code: 'REISS-TUX-BLK-38', size: '38', color: 'Midnight Black', color_hex: '#111111', stock_level: 8 },
      { id: 5, sku_code: 'REISS-TUX-BLK-40', size: '40', color: 'Midnight Black', color_hex: '#111111', stock_level: 14 },
    ],
  },
  {
    id: 3,
    title: 'Relaxed Organic Poplin Oxford Shirt',
    title_ar: 'قميص أكسفورد بوبلين عضوي بقصة مريحة',
    slug: 'relaxed-organic-poplin-oxford-shirt',
    brand_id: 2,
    brand_name: 'COS',
    category_id: 2,
    category_name: 'Tops & Shirts',
    base_price: 95.0,
    currency: 'USD',
    material: '100% Organic Cotton',
    care_instructions: 'Machine Wash 30C',
    color_family: 'Optic White',
    dominant_hex: '#FAF9F6',
    thumbnail_url: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=700',
    images: ['https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=700'],
    style_tags: ['smart_casual', 'minimalist', 'essential'],
    occasion_tags: ['work', 'casual', 'dinner', 'wedding'],
    rating: 4.8,
    style_compatibility_score: 95,
    is_featured: false,
    skus: [
      { id: 6, sku_code: 'COS-SHR-WHT-S', size: 'S', color: 'Optic White', color_hex: '#FAF9F6', stock_level: 15 },
      { id: 7, sku_code: 'COS-SHR-WHT-M', size: 'M', color: 'Optic White', color_hex: '#FAF9F6', stock_level: 20 },
    ],
  },
  {
    id: 4,
    title: 'Pleated Tapered Virgin Wool Trousers',
    title_ar: 'بنطال صوف فيرجن بقصة مريحة وكسرات',
    slug: 'pleated-tapered-virgin-wool-trousers',
    brand_id: 1,
    brand_name: 'Massimo Dutti',
    category_id: 3,
    category_name: 'Bottoms & Trousers',
    base_price: 165.0,
    currency: 'USD',
    material: '100% Virgin Wool',
    care_instructions: 'Dry Clean',
    color_family: 'Navy Blue',
    dominant_hex: '#1B1F3B',
    thumbnail_url: 'https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=700',
    images: ['https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=700'],
    style_tags: ['formal', 'tailored', 'smart_casual'],
    occasion_tags: ['wedding', 'work', 'business', 'dinner'],
    rating: 4.8,
    style_compatibility_score: 94,
    is_featured: false,
    skus: [
      { id: 8, sku_code: 'MD-TRS-NVY-30', size: '30', color: 'Navy Blue', color_hex: '#1B1F3B', stock_level: 10 },
      { id: 9, sku_code: 'MD-TRS-NVY-32', size: '32', color: 'Navy Blue', color_hex: '#1B1F3B', stock_level: 15 },
    ],
  },
  {
    id: 5,
    title: 'Silk Slip Column Maxi Dress with Drape Neckline',
    title_ar: 'فستان ماكسي حرير بتصميم عمودي وياقة منسدلة',
    slug: 'silk-slip-column-maxi-dress',
    brand_id: 3,
    brand_name: 'Reiss',
    category_id: 4,
    category_name: 'Dresses',
    base_price: 340.0,
    currency: 'USD',
    material: '100% Mulberry Silk',
    care_instructions: 'Specialist Dry Clean',
    color_family: 'Champagne Gold',
    dominant_hex: '#D4AF37',
    thumbnail_url: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=700',
    images: ['https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=700'],
    style_tags: ['formal', 'evening', 'glamour', 'quiet_luxury'],
    occasion_tags: ['wedding', 'party', 'gala', 'dinner'],
    rating: 4.9,
    style_compatibility_score: 98,
    is_featured: true,
    skus: [
      { id: 10, sku_code: 'REISS-DRS-GLD-6', size: '6', color: 'Champagne Gold', color_hex: '#D4AF37', stock_level: 9 },
      { id: 11, sku_code: 'REISS-DRS-GLD-8', size: '8', color: 'Champagne Gold', color_hex: '#D4AF37', stock_level: 14 },
    ],
  },
  {
    id: 6,
    title: 'Goodyear Welted Leather Oxford Shoes',
    title_ar: 'حذاء أكسفورد جلد بحياكة جوديير كلاسيكية',
    slug: 'goodyear-welted-leather-oxford-shoes',
    brand_id: 1,
    brand_name: 'Massimo Dutti',
    category_id: 5,
    category_name: 'Footwear',
    base_price: 245.0,
    currency: 'USD',
    material: '100% Full-Grain Calfskin',
    care_instructions: 'Polish with Natural Wax',
    color_family: 'Obsidian Black',
    dominant_hex: '#111111',
    thumbnail_url: 'https://images.unsplash.com/photo-1614252235316-8c857d38b5f4?w=700',
    images: ['https://images.unsplash.com/photo-1614252235316-8c857d38b5f4?w=700'],
    style_tags: ['formal', 'tailored', 'smart_casual'],
    occasion_tags: ['wedding', 'work', 'business', 'dinner'],
    rating: 4.9,
    style_compatibility_score: 97,
    is_featured: false,
    skus: [
      { id: 12, sku_code: 'MD-OXF-BLK-41', size: '41', color: 'Obsidian Black', color_hex: '#111111', stock_level: 8 },
      { id: 13, sku_code: 'MD-OXF-BLK-42', size: '42', color: 'Obsidian Black', color_hex: '#111111', stock_level: 12 },
    ],
  },
  {
    id: 7,
    title: 'Strappy Metallic Leather Heeled Sandals',
    title_ar: 'صندل بكعب وسيور جلدية ميتاليك',
    slug: 'strappy-metallic-leather-heeled-sandals',
    brand_id: 3,
    brand_name: 'Reiss',
    category_id: 5,
    category_name: 'Footwear',
    base_price: 250.0,
    currency: 'USD',
    material: '100% Metallic Leather',
    care_instructions: 'Store in Dust Bag',
    color_family: 'Metallic Gold',
    dominant_hex: '#C5A059',
    thumbnail_url: 'https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=700',
    images: ['https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=700'],
    style_tags: ['evening', 'formal', 'glamour'],
    occasion_tags: ['wedding', 'party', 'gala', 'dinner'],
    rating: 4.8,
    style_compatibility_score: 96,
    is_featured: false,
    skus: [
      { id: 14, sku_code: 'REISS-SND-GLD-38', size: '38', color: 'Metallic Gold', color_hex: '#C5A059', stock_level: 7 },
      { id: 15, sku_code: 'REISS-SND-GLD-39', size: '39', color: 'Metallic Gold', color_hex: '#C5A059', stock_level: 11 },
    ],
  },
  {
    id: 8,
    title: 'Silk Jacquard Evening Necktie',
    title_ar: 'ربطة عنق حريرية جاكار للمناسبات',
    slug: 'silk-jacquard-evening-necktie',
    brand_id: 3,
    brand_name: 'Reiss',
    category_id: 6,
    category_name: 'Accessories',
    base_price: 75.0,
    currency: 'USD',
    material: '100% Mulberry Silk',
    care_instructions: 'Dry Clean Only',
    color_family: 'Emerald Green',
    dominant_hex: '#2D4A3E',
    thumbnail_url: 'https://images.unsplash.com/photo-1589756823695-278bc923f962?w=700',
    images: ['https://images.unsplash.com/photo-1589756823695-278bc923f962?w=700'],
    style_tags: ['formal', 'tailored', 'smart_casual'],
    occasion_tags: ['wedding', 'work', 'business', 'dinner'],
    rating: 4.9,
    style_compatibility_score: 97,
    is_featured: false,
    skus: [
      { id: 16, sku_code: 'REISS-TIE-EMR-OS', size: 'One Size', color: 'Emerald Green', color_hex: '#2D4A3E', stock_level: 25 },
    ],
  },
  {
    id: 9,
    title: 'Structured Metallic Evening Box Clutch',
    title_ar: 'حقيبة يد كلاتش مسائية ميتاليك',
    slug: 'structured-metallic-evening-box-clutch',
    brand_id: 3,
    brand_name: 'Reiss',
    category_id: 6,
    category_name: 'Accessories',
    base_price: 180.0,
    currency: 'USD',
    material: '100% Embossed Leather & Gold Plated Brass',
    care_instructions: 'Store in Dust Bag',
    color_family: 'Black & Gold',
    dominant_hex: '#C5A059',
    thumbnail_url: 'https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=700',
    images: ['https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=700'],
    style_tags: ['quiet_luxury', 'evening', 'formal'],
    occasion_tags: ['wedding', 'party', 'gala', 'dinner'],
    rating: 4.9,
    style_compatibility_score: 97,
    is_featured: false,
    skus: [
      { id: 17, sku_code: 'REISS-CLT-GLD-OS', size: 'One Size', color: 'Black & Gold', color_hex: '#C5A059', stock_level: 12 },
    ],
  },
];

const FALLBACK_CATEGORIES = [
  { id: 1, name: 'Outerwear', name_ar: 'الملابس الخارجية', slug: 'outerwear', icon_name: 'sparkle' },
  { id: 2, name: 'Tops & Shirts', name_ar: 'القمصان والبلوزات', slug: 'tops', icon_name: 'hanger' },
  { id: 3, name: 'Bottoms & Trousers', name_ar: 'البناطيل والتنانير', slug: 'bottoms', icon_name: 'hanger' },
  { id: 4, name: 'Dresses', name_ar: 'الفساتين', slug: 'dresses', icon_name: 'sparkle' },
  { id: 5, name: 'Footwear', name_ar: 'الأحذية', slug: 'footwear', icon_name: 'ruler' },
  { id: 6, name: 'Accessories', name_ar: 'الإكسسوارات', slug: 'accessories', icon_name: 'sparkle' },
];

const FALLBACK_BRANDS = [
  { id: 1, brand_name: 'Massimo Dutti', slug: 'massimo-dutti', description: 'Refined urban elegance crafted with premium Italian fabrics.' },
  { id: 2, brand_name: 'COS', slug: 'cos', description: 'Contemporary, reinvented classics and wardrobe essentials.' },
  { id: 3, brand_name: 'Reiss', slug: 'reiss', description: 'Modern British tailoring with an uncompromising eye on detail.' },
  { id: 4, brand_name: 'Arket', slug: 'arket', description: 'Nordic simplicity and sustainable, durable wardrobe foundations.' },
];

/**
 * Client-Side Edge Fallback Handler for Vercel Static Hosting & Offline Resilience.
 */
function handleEdgeFallback<T>(endpoint: string, options: RequestInit): T | null {
  try {
    const bodyObj = typeof options.body === 'string' ? JSON.parse(options.body) : {};

    // 0. Catalog Endpoints Fallback
    if (endpoint.includes('/catalog/products/')) {
      const slug = endpoint.split('/catalog/products/')[1]?.split('?')[0];
      const prod = FALLBACK_PRODUCTS.find((p) => p.slug === slug || String(p.id) === slug) || FALLBACK_PRODUCTS[0];
      return prod as unknown as T;
    }

    if (endpoint.includes('/catalog/products') || endpoint.includes('/products')) {
      return FALLBACK_PRODUCTS as unknown as T;
    }

    if (endpoint.includes('/catalog/categories') || endpoint.includes('/categories')) {
      return FALLBACK_CATEGORIES as unknown as T;
    }

    if (endpoint.includes('/catalog/brands') || endpoint.includes('/brands')) {
      return FALLBACK_BRANDS as unknown as T;
    }

    // Fabricated mock fallbacks were REMOVED deliberately (security audit S1):
    // - auth login/register + /auth/me fabricated sessions — including a
    //   client-side 'admin' role for any email containing "admin".
    // - stylist chat invented AI answers; commerce checkout confirmed PAID
    //   orders with fake tracking numbers while the API was down; wardrobe,
    //   profile and BOPIS blocks invented user data and store stock.
    // Only reference-data fallbacks (catalogue products/categories/brands)
    // remain. Everything else now fails visibly with the real ApiError.
    //
    // 2. Try-On Jobs & Multi-Render — NO fallback by design.
    // A generation feature must never convert a failed generation into a
    // successful response: fabricating a completed try-on job here previously
    // presented the user's own unmodified photo as the "dressed" result with
    // invented fit scores and traceability hashes. The real ApiError now
    // propagates so the UI can show an honest failure state.

  } catch (err) {
    console.warn('Fallback error:', err);
  }

  return null;
}
