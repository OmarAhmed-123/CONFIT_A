import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import fs from 'fs';
import path from 'path';

const OUTPUT_DIR = '/home/user/CONFIT_A/shots_brand_discovery';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const mockUser = {
  id: 42,
  email: 'director@massimodutti.com',
  full_name: 'Massimo Dutti Brand Director',
  role: 'brand_owner',
  preferred_language: 'en',
  is_active: true,
  is_verified: true,
  mfa_enabled: false,
  created_at: '2026-01-01T00:00:00Z',
  has_profile: true,
  brand_id: 1,
};

const mockStores = [
  {
    id: 1,
    brand_id: 1,
    name: 'Zamalek Flagship Boutique',
    name_ar: 'بوتيك الزمالك الرئيسي',
    store_code: 'ZAM-01',
    address: '15 Brazil Street',
    city: 'Cairo',
    state: 'Cairo Governorate',
    postal_code: '11211',
    country: 'Egypt',
    latitude: 30.0561,
    longitude: 31.2215,
    phone: '+20 2 2735 0000',
    email: 'zamalek@massimodutti.com',
    google_maps_url: 'https://www.google.com/maps/search/?api=1&query=30.0561,31.2215',
    is_bopis_enabled: true,
    is_active: true,
    is_location_verified: true,
    inventory_items_count: 28,
    total_stock_units: 142,
    pickup_instructions: 'Proceed to concierge desk on ground floor with verification code.',
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    brand_id: 1,
    name: 'Mall of Arabia Boutique',
    name_ar: 'فرع مول العرب',
    store_code: 'MOA-02',
    address: 'Juhayna Square, 6th of October',
    city: 'Giza',
    state: 'Giza Governorate',
    postal_code: '12568',
    country: 'Egypt',
    latitude: 30.0074,
    longitude: 30.9733,
    phone: '+20 2 3826 0000',
    email: 'mallofarabia@massimodutti.com',
    google_maps_url: 'https://www.google.com/maps/search/?api=1&query=30.0074,30.9733',
    is_bopis_enabled: true,
    is_active: true,
    is_location_verified: true,
    inventory_items_count: 34,
    total_stock_units: 198,
    pickup_instructions: 'Dedicated Click & Collect counter next to fitting rooms.',
    created_at: '2026-01-15T00:00:00Z',
  },
];

const mockOnboarding = {
  brand_id: 1,
  brand_name: 'Massimo Dutti',
  is_verified: true,
  is_published: true,
  publication_status: 'active',
  completion_percentage: 86,
  total_steps_count: 7,
  completed_steps_count: 6,
  stores_count: 2,
  products_count: 48,
  active_promotions_count: 3,
  welcome_message: 'Welcome back! Your brand is registered and visible to customers. Keep your store locations and product availability up to date.',
  primary_cta_label: 'Manage Catalog & Availability',
  primary_cta_url: '/b2b/catalog',
  steps: [
    {
      key: 'brand_profile',
      title: 'Brand Profile Identity',
      description: 'Official brand name, logo, aesthetic bio, and contact.',
      is_completed: true,
      action_url: '/b2b/profile',
    },
    {
      key: 'first_branch',
      title: 'First Physical Branch Location',
      description: 'Store location with verified street address and GPS coordinates.',
      is_completed: true,
      action_url: '/b2b/branches',
    },
    {
      key: 'bopis_readiness',
      title: 'BOPIS Click & Collect Setup',
      description: 'In-store pickup instructions and estimated fulfillment lead time.',
      is_completed: true,
      action_url: '/b2b/branches',
    },
    {
      key: 'product_catalog',
      title: 'Product Catalog Ingestion',
      description: 'At least one verified product in the brand catalog.',
      is_completed: true,
      action_url: '/b2b/catalog',
    },
    {
      key: 'branch_inventory',
      title: 'Branch Inventory Availability',
      description: 'Stock levels synced to physical branch boutiques.',
      is_completed: true,
      action_url: '/b2b/inventory',
    },
    {
      key: 'sponsored_placements',
      title: 'Discovery & Sponsored Placements',
      description: 'Promotional campaigns or verified artisan showcase.',
      is_completed: true,
      action_url: '/b2b/placements',
    },
    {
      key: 'publication_review',
      title: 'Customer Discovery Publication',
      description: 'Verified status approved by platform moderation.',
      is_completed: true,
      action_url: '/brands/massimo-dutti',
    },
  ],
};

const mockProfile = {
  id: 1,
  user_id: 42,
  brand_name: 'Massimo Dutti',
  slug: 'massimo-dutti',
  commission_rate: 14,
  return_rate_benchmark: 28.5,
  current_return_rate: 11.4,
  is_verified: true,
  created_at: '2026-01-01T00:00:00Z',
};

const mockAnalytics = {
  total_products_count: 48,
  total_skus_count: 184,
  total_views: 14200,
  total_tryons: 4850,
  total_purchases: 940,
  return_rate_before_vton: 31.8,
  return_rate_after_vton: 11.4,
  methodology: 'Verified telemetry comparing VTON session conversions against baseline cohorts.',
  outfit_appearance_rankings: [],
};

async function capture() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 2,
    locale: 'en',
  });

  await context.addInitScript((user) => {
    localStorage.setItem('confit_user', JSON.stringify(user));
  }, mockUser);

  // Intercept all API calls matching any prefix
  await context.route('**/*', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/v1/auth/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockUser) });
    }
    if (url.includes('/partner/stores') || url.includes('/brands/stores')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockStores) });
    }
    if (url.includes('/partner/onboarding-status') || url.includes('/brands/onboarding-status')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockOnboarding) });
    }
    if (url.includes('/brand/profile') || url.includes('/partner/profile')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockProfile) });
    }
    if (url.includes('/brand/analytics') || url.includes('/partner/analytics')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockAnalytics) });
    }
    if (url.includes('/brand/products') || url.includes('/partner/products')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    }
    if (url.includes('/brand/placements') || url.includes('/partner/placements')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    }
    if (url.includes('/partner/catalog/imports')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    }
    if (url.includes('/partner/analytics/conversion')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ per_sku: [] }) });
    }
    return route.continue();
  });

  const page = await context.newPage();

  console.log('1. Capturing Brand Registration Page...');
  await page.goto('http://localhost:43123/brand/register', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, '05_brand_registration_desktop.png'),
    fullPage: false,
  });

  console.log('2. Capturing Brand Branches Management Hub...');
  await page.goto('http://localhost:43123/b2b/branches', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, '06_brand_branches_management_desktop.png'),
    fullPage: false,
  });

  console.log('3. Capturing Add Boutique Branch Modal with GPS Coordinate Validation...');
  const addBtn = page.locator('button[aria-label="Add New Boutique Branch"]').first();
  if (await addBtn.isVisible()) {
    await addBtn.click();
    await page.waitForTimeout(600);
    const nameInput = page.locator('input[name="name"]');
    if (await nameInput.isVisible()) {
      await nameInput.fill('Fifth Avenue Flagship Boutique');
    }
    const addressInput = page.locator('input[name="address"]');
    if (await addressInput.isVisible()) {
      await addressInput.fill('711 5th Avenue, New York, NY 10022');
    }
    const latInput = page.locator('input[name="latitude"]');
    if (await latInput.isVisible()) {
      await latInput.fill('40.7614');
    }
    const lngInput = page.locator('input[name="longitude"]');
    if (await lngInput.isVisible()) {
      await lngInput.fill('-73.9744');
    }
    await page.waitForTimeout(400);
    await page.screenshot({
      path: path.join(OUTPUT_DIR, '07_brand_branch_modal_desktop.png'),
      fullPage: false,
    });
    // Close modal
    const cancelBtn = page.getByRole('button', { name: '✕' });
    if (await cancelBtn.isVisible()) await cancelBtn.click();
  }

  console.log('4. Capturing Owner Dashboard Guided Onboarding Hub...');
  await page.goto('http://localhost:43123/b2b', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, '08_brand_owner_dashboard_onboarding_desktop.png'),
    fullPage: false,
  });

  console.log('5. Capturing Mobile Viewport (390x844) for Brand Registration...');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('http://localhost:43123/brand/register', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, '09_brand_registration_mobile.png'),
    fullPage: false,
  });

  console.log('All 5 screenshots captured successfully!');
  await browser.close();
}

capture().catch((err) => {
  console.error('Screenshot capture failed:', err);
  process.exit(1);
});
