import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const LEGACY = [/1B1F3B/i, /0C0E1E/i, /C5A059/i, /E2BF70/i, /A37E44/i, /FAF9F6/i, /C9A227/i, /B8935A/i, /FDF8EE/i];

function readComponent(relPath: string) {
  return fs.readFileSync(path.resolve(__dirname, '../../..', relPath), 'utf8');
}

describe('Shared primitives and global components brand token contracts', () => {
  it('AccessiblePrimitives uses brand-charcoal and no legacy gold/navy', () => {
    const src = readComponent('components/common/AccessiblePrimitives.tsx');
    for (const re of LEGACY) {
      expect(src).not.toMatch(re);
    }
    expect(src).toContain('ring-brand-charcoal');
  });

  it('CommonComponents uses brand tokens and no legacy gold/navy', () => {
    const src = readComponent('components/common/CommonComponents.tsx');
    for (const re of LEGACY) {
      expect(src).not.toMatch(re);
    }
  });

  it('VirtualStylistDrawer uses brand tokens and charcoal focus rings', () => {
    const src = readComponent('components/stylist/VirtualStylistDrawer.tsx');
    for (const re of LEGACY) {
      expect(src).not.toMatch(re);
    }
    expect(src).toContain('ring-brand-charcoal');
  });

  it('CartDrawer uses brand tokens and no legacy cream/navy', () => {
    const src = readComponent('components/commerce/CartDrawer.tsx');
    for (const re of LEGACY) {
      expect(src).not.toMatch(re);
    }
  });

  it('DuplicateAlertModal uses brand tokens and no legacy cream/navy/gold', () => {
    const src = readComponent('components/wardrobe/DuplicateAlertModal.tsx');
    for (const re of LEGACY) {
      expect(src).not.toMatch(re);
    }
  });

  it('AnnouncementBar and CollectionRail use brand tokens', () => {
    const ann = readComponent('components/home/AnnouncementBar.tsx');
    const rail = readComponent('components/home/CollectionRail.tsx');
    for (const re of LEGACY) {
      expect(ann).not.toMatch(re);
      expect(rail).not.toMatch(re);
    }
  });
});
