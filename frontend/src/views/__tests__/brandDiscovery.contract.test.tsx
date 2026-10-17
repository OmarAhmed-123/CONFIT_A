import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');

const BRANDS_VIEW = read('src/views/consumer/BrandsView.tsx');
const BRAND_CARD = read('src/components/brands/BrandCard.tsx');
const STORE_BRANCH_CARD = read('src/components/brands/StoreBranchCard.tsx');
const BRANCH_INVENTORY_GRID = read('src/components/brands/BranchInventoryGrid.tsx');
const STORE_MAP_CANVAS = read('src/components/brands/StoreMapCanvas.tsx');
const PROMO_BANNER = read('src/components/brands/PromotionBanner.tsx');

const LEGACY = [
  /1B1F3B/i,
  /0C0E1E/i,
  /C5A059/i,
  /E2BF70/i,
  /A37E44/i,
  /FDF8EE/i,
  /7A5C28/i,
  /FAF9F6/i,
  /slate-950/,
];

describe('Brand Discovery & Store Locator Contracts', () => {
  it('carries no legacy navy/gold/cream palette tokens across all new brand locator components', () => {
    const files = [
      BRANDS_VIEW,
      BRAND_CARD,
      STORE_BRANCH_CARD,
      BRANCH_INVENTORY_GRID,
      STORE_MAP_CANVAS,
      PROMO_BANNER,
    ];

    files.forEach((fileContent) => {
      for (const re of LEGACY) {
        expect(fileContent).not.toMatch(re);
      }
    });
  });

  it('uses brand-charcoal, brand-coral, brand-mint, or brand-lilac styling tokens', () => {
    expect(BRANDS_VIEW).toMatch(/text-brand-charcoal/);
    expect(BRANDS_VIEW).toMatch(/text-brand-coral/);
    expect(STORE_BRANCH_CARD).toMatch(/bg-brand-coral/);
    expect(STORE_MAP_CANVAS).toMatch(/bg-brand-coral/);
  });

  it('binds universal Google Maps navigation URLs to route actions', () => {
    expect(STORE_BRANCH_CARD).toContain('branch.google_maps_url');
    expect(STORE_MAP_CANVAS).toContain('selectedBranch.google_maps_url');
  });

  it('supports BOPIS reservation flow and size-level breakdown', () => {
    expect(BRANCH_INVENTORY_GRID).toMatch(/quantity_available/);
    expect(BRANCH_INVENTORY_GRID).toMatch(/branch_stock_by_size/);
    expect(BRANDS_VIEW).toMatch(/bopis_hold_requested/);
  });
});
