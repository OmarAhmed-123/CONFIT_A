import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for B2B views.
 * - No legacy navy, gold or cream tokens.
 * - Uses brand charcoal, brand wash, and proper neutral styling.
 */
const B2B_FILES = [
  'BrandDashboardView.tsx',
  'BrandCatalogView.tsx',
  'BrandInventoryView.tsx',
  'BrandOrdersView.tsx',
  'BrandAnalyticsView.tsx',
  'BrandPlacementsView.tsx',
  'PartnerGatewayView.tsx',
  'LeadForm.tsx',
];

const LEGACY = [/1B1F3B/i, /0C0E1E/i, /C5A059/i, /E2BF70/i, /A37E44/i, /FAF9F6/i, /C9A227/i, /B8935A/i, /FDF8EE/i];

describe('B2B views brand contract', () => {
  for (const filename of B2B_FILES) {
    it(`${filename} carries no legacy navy, gold or cream tokens`, () => {
      const src = readFileSync(
        resolve(process.cwd(), `src/views/b2b/${filename}`),
        'utf8'
      );
      for (const re of LEGACY) {
        expect(src, `${filename} still has ${re}`).not.toMatch(re);
      }
    });
  }
});
