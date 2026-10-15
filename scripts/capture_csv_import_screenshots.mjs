import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import fs from 'fs';
import path from 'path';

const OUTPUT_DIR = '/home/user/CONFIT_A/shots_csv_import';
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
    country: 'Egypt',
    latitude: 30.0561,
    longitude: 31.2215,
    phone: '+20 2 2735 0000',
    is_bopis_enabled: true,
    is_active: true,
  },
  {
    id: 2,
    brand_id: 1,
    name: 'Mall of Arabia Boutique',
    name_ar: 'فرع مول العرب',
    store_code: 'MOA-02',
    address: 'Juhayna Square, 6th of October',
    city: 'Giza',
    country: 'Egypt',
    latitude: 30.0074,
    longitude: 30.9733,
    phone: '+20 2 3826 0000',
    is_bopis_enabled: true,
    is_active: true,
  },
];

const mockProducts = [
  {
    id: 101,
    title: 'Tailored Cashmere-Wool Coat',
    category_name: 'Outerwear',
    base_price: 3450,
    currency: 'EGP',
    thumbnail_url: 'https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg',
    skus: [
      { id: 201, sku_code: 'MD-COAT-CAMEL-S', size: 'S', color: 'Camel', stock_level: 8, is_in_stock: true, price_override: null },
      { id: 202, sku_code: 'MD-COAT-CAMEL-M', size: 'M', color: 'Camel', stock_level: 14, is_in_stock: true, price_override: null },
      { id: 203, sku_code: 'MD-COAT-NAVY-L', size: 'L', color: 'Navy', stock_level: 6, is_in_stock: true, price_override: null },
    ],
  },
  {
    id: 102,
    title: 'Italian Linen Spread-Collar Shirt',
    category_name: 'Shirts',
    base_price: 950,
    currency: 'EGP',
    thumbnail_url: 'https://images.pexels.com/photos/297933/pexels-photo-297933.jpeg',
    skus: [
      { id: 204, sku_code: 'MD-SHIRT-WHT-39', size: '39', color: 'Optic White', stock_level: 22, is_in_stock: true, price_override: null },
      { id: 205, sku_code: 'MD-SHIRT-BLU-40', size: '40', color: 'Sky Blue', stock_level: 19, is_in_stock: true, price_override: null },
    ],
  },
  {
    id: 103,
    title: 'Pleated Tapered Wool Trousers',
    category_name: 'Trousers',
    base_price: 1350,
    currency: 'EGP',
    thumbnail_url: 'https://images.pexels.com/photos/1598507/pexels-photo-1598507.jpeg',
    skus: [
      { id: 206, sku_code: 'MD-TRSR-CHAR-32', size: '32', color: 'Charcoal', stock_level: 11, is_in_stock: true, price_override: null },
      { id: 207, sku_code: 'MD-TRSR-BEI-34', size: '34', color: 'Sand Beige', stock_level: 15, is_in_stock: true, price_override: null },
    ],
  },
];

const mockInventoryStoreBreakdown = [
  {
    product_id: 101,
    title: 'Tailored Cashmere-Wool Coat',
    category_name: 'Outerwear',
    skus: [
      {
        sku_id: 201,
        sku_code: 'MD-COAT-CAMEL-S',
        size: 'S',
        color: 'Camel',
        warehouse_stock: 8,
        store_inventories: [
          { store_id: 1, store_name: 'Zamalek Flagship Boutique', quantity: 5, reserved: 0, available: 5 },
          { store_id: 2, store_name: 'Mall of Arabia Boutique', quantity: 3, reserved: 0, available: 3 },
        ],
      },
      {
        sku_id: 202,
        sku_code: 'MD-COAT-CAMEL-M',
        size: 'M',
        color: 'Camel',
        warehouse_stock: 14,
        store_inventories: [
          { store_id: 1, store_name: 'Zamalek Flagship Boutique', quantity: 8, reserved: 1, available: 7 },
          { store_id: 2, store_name: 'Mall of Arabia Boutique', quantity: 6, reserved: 0, available: 6 },
        ],
      },
    ],
  },
];

const mockPreviewResponse = {
  total_rows: 8,
  valid_rows_count: 7,
  error_rows_count: 1,
  warning_rows_count: 0,
  duplicate_rows_count: 0,
  can_import: true,
  preview_records: [
    {
      row_number: 2,
      status: 'valid',
      action: 'create',
      product_name: 'Structured Double-Breasted Blazer',
      sku: 'MD-BLZ-NAVY-48',
      category: 'blazers',
      price: '2850.00',
      currency: 'EGP',
      stock: 18,
      size: '48',
      color: 'Midnight Navy',
    },
    {
      row_number: 3,
      status: 'valid',
      action: 'create',
      product_name: 'Structured Double-Breasted Blazer',
      sku: 'MD-BLZ-NAVY-50',
      category: 'blazers',
      price: '2850.00',
      currency: 'EGP',
      stock: 24,
      size: '50',
      color: 'Midnight Navy',
    },
    {
      row_number: 4,
      status: 'valid',
      action: 'create',
      product_name: 'Mulberry Silk Evening Blouse',
      sku: 'MD-BLS-IVORY-M',
      category: 'tops',
      price: '1650.00',
      currency: 'EGP',
      stock: 12,
      size: 'M',
      color: 'Ivory Cream',
    },
    {
      row_number: 5,
      status: 'valid',
      action: 'create',
      product_name: 'Suede Belgian Loafers',
      sku: 'MD-SHOE-CHOCO-42',
      category: 'shoes',
      price: '2100.00',
      currency: 'EGP',
      stock: 15,
      size: '42',
      color: 'Dark Chocolate',
    },
    {
      row_number: 6,
      status: 'valid',
      action: 'create',
      product_name: 'Cashmere Ribbed Knit Cardigan',
      sku: 'MD-KNT-OAT-L',
      category: 'knitwear',
      price: '1850.00',
      currency: 'EGP',
      stock: 9,
      size: 'L',
      color: 'Oatmeal Heather',
    },
    {
      row_number: 7,
      status: 'valid',
      action: 'create',
      product_name: 'Selvedge Cotton Denim Trousers',
      sku: 'MD-JEAN-RAW-32',
      category: 'trousers',
      price: '1450.00',
      currency: 'EGP',
      stock: 30,
      size: '32',
      color: 'Raw Indigo',
    },
    {
      row_number: 8,
      status: 'valid',
      action: 'create',
      product_name: 'Monogram Leather Reversible Belt',
      sku: 'MD-BELT-BLK-95',
      category: 'accessories',
      price: '750.00',
      currency: 'EGP',
      stock: 40,
      size: '95',
      color: 'Black/Espresso',
    },
    {
      row_number: 9,
      status: 'error',
      action: 'error',
      product_name: 'Sample Defective Trench',
      sku: 'MD-TRNCH-ERR-09',
      category: 'outerwear',
      price: '-120.00',
      currency: 'EGP',
      stock: -5,
      size: 'XL',
      color: 'Khaki',
      error_message: 'base_price: Price must be positive; stock_quantity: Cannot be negative',
    },
  ],
  errors: [
    {
      row: 9,
      field: 'base_price',
      message: 'base_price: Price must be positive; stock_quantity: Cannot be negative',
      value: '-120.00',
      suggestion: 'Set a positive retail price and non-negative inventory',
    },
  ],
  warnings: [],
};

const mockImportSuccessResponse = {
  job_id: 142,
  status: 'completed',
  total_rows: 8,
  accepted_rows: 7,
  rejected_rows: 1,
  duplicate_rows: 0,
  notifications_queued: 48,
  notification_recipients_count: 48,
  errors: [
    {
      row: 9,
      field: 'base_price',
      message: 'base_price: Price must be positive; stock_quantity: Cannot be negative',
      value: '-120.00',
      suggestion: 'Set a positive retail price and non-negative inventory',
    },
  ],
};

async function run() {
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

  // Setup mock network routes
  await context.route('**/*', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes('/api/')) {
      console.log('INTERCEPT API:', method, url);
    }

    if (url.includes('/api/v1/auth/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockUser) });
    }
    if (url.includes('/partner/stores') || url.includes('/brand/stores')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockStores) });
    }
    if (url.includes('/brand/products') || url.includes('/partner/products')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockProducts) });
    }
    if (url.includes('/partner/inventory')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockInventoryStoreBreakdown) });
    }
    if (url.includes('/brand/profile') || url.includes('/partner/profile')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, brand_name: 'Massimo Dutti', slug: 'massimo-dutti', is_verified: true }),
      });
    }
    if (url.includes('/brand/analytics') || url.includes('/partner/analytics')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total_products_count: 48, total_skus_count: 184, total_views: 14200 }),
      });
    }
    if (url.includes('/partner/catalog/preview-csv')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockPreviewResponse) });
    }
    if (url.includes('/partner/catalog/confirm-import')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockImportSuccessResponse) });
    }
    if (url.includes('/partner/catalog/imports')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            job_id: 142,
            file_name: 'autumn_winter_2026_capsule.csv',
            status: 'completed',
            total_rows: 8,
            accepted_rows: 7,
            rejected_rows: 1,
            duplicate_rows: 0,
            notifications_queued: 48,
            created_at: '2026-10-15T09:30:00Z',
          },
        ]),
      });
    }
    if (url.includes('/partner/catalog/export-errors')) {
      return route.fulfill({
        status: 200,
        contentType: 'text/csv',
        body: 'Row Number,Field,Submitted Value,Error Reason,Corrective Action\n9,base_price,-120.00,Price must be positive,Set a positive retail price',
      });
    }
    if (url.includes('/partner/catalog/template.csv')) {
      return route.fulfill({
        status: 200,
        contentType: 'text/csv',
        body: 'product_name,sku,description,category,price,currency,stock_quantity,size,color\nStructured Blazer,BLZ-001,Pure wool,blazers,2850.00,EGP,10,48,Navy',
      });
    }
    return route.continue();
  });

  const page = await context.newPage();
  page.on('console', (msg) => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', (err) => console.error('PAGE ERROR:', err.message));

  console.log('1. Capturing Brand Catalog with CSV Import Action...');
  await page.goto('http://localhost:43123/b2b/catalog', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, '01_brand_catalog_with_csv_action.png'),
    fullPage: false,
  });

  console.log('2. Opening CSV Import Modal (Upload Step)...');
  await page.click('button:has-text("Import Products from CSV")');
  await page.waitForTimeout(800);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, '02_csv_import_modal_step1_upload.png'),
    fullPage: false,
  });

  console.log('3. Simulating CSV Upload & Capturing Validation Preview...');
  // Upload a mock file into the file input inside the modal
  const sampleCSV = `product_name,sku,description,category,price,currency,stock_quantity,size,color
Structured Double-Breasted Blazer,MD-BLZ-NAVY-48,Super 130s wool double breasted jacket,blazers,2850.00,EGP,18,48,Midnight Navy
Structured Double-Breasted Blazer,MD-BLZ-NAVY-50,Super 130s wool double breasted jacket,blazers,2850.00,EGP,24,50,Midnight Navy
Mulberry Silk Evening Blouse,MD-BLS-IVORY-M,Pure mulberry silk blouse with mother-of-pearl buttons,tops,1650.00,EGP,12,M,Ivory Cream
Suede Belgian Loafers,MD-SHOE-CHOCO-42,Handmade chocolate suede slip-ons,shoes,2100.00,EGP,15,42,Dark Chocolate
Cashmere Ribbed Knit Cardigan,MD-KNT-OAT-L,Finest Mongolian cashmere knit,knitwear,1850.00,EGP,9,L,Oatmeal Heather
Selvedge Cotton Denim Trousers,MD-JEAN-RAW-32,Japanese 14oz selvedge raw denim,trousers,1450.00,EGP,30,32,Raw Indigo
Monogram Leather Reversible Belt,MD-BELT-BLK-95,Full-grain calfskin reversible belt,accessories,750.00,EGP,40,95,Black/Espresso
Sample Defective Trench,MD-TRNCH-ERR-09,Defective row for validation check,outerwear,-120.00,EGP,-5,XL,Khaki`;

  const inputSelector = 'input[type="file"]';
  await page.setInputFiles(inputSelector, {
    name: 'autumn_winter_2026_capsule.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(sampleCSV, 'utf-8'),
  });

  await page.waitForTimeout(1000);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, '03_csv_import_modal_step2_validation_preview.png'),
    fullPage: false,
  });

  console.log('4. Confirming Import & Capturing Success State...');
  // Click Confirm & Import button
  const confirmBtn = page.locator('button:has-text("Confirm & Import")');
  await confirmBtn.click();
  await page.waitForTimeout(2000);
  const modalText = await page.locator('[role="dialog"]').innerText();
  console.log('MODAL INNER TEXT AFTER CONFIRM CLICK:', modalText);

  await page.screenshot({
    path: path.join(OUTPUT_DIR, '04_csv_import_modal_step3_success_summary.png'),
    fullPage: false,
  });

  // Close modal
  await page.click('button:has-text("View in Catalog Table")');
  await page.waitForTimeout(800);

  console.log('5. Capturing Brand Inventory BOPIS View with CSV Action...');
  await page.goto('http://localhost:43123/b2b/inventory', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, '05_brand_inventory_bopis_csv_action.png'),
    fullPage: false,
  });

  await browser.close();
  console.log('All screenshots captured in:', OUTPUT_DIR);
}

run().catch((err) => {
  console.error('Error capturing screenshots:', err);
  process.exit(1);
});
