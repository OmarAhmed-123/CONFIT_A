/**
 * Logo #3 brand + state contract for Order tracking (/orders, /orders/:orderNumber).
 *
 * Source-level checks, same style as myLooksBrand.contract.test.tsx.
 * Runtime state behaviour is covered by orderTrackingStates.test.tsx.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const read = (rel: string) => readFileSync(resolve(__dirname, rel), 'utf8');
const strip = (src: string) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((l) => !/^\s*\/\//.test(l))
    .join('\n');

const VIEW = strip(read('../consumer/OrderTrackingView.tsx'));
const EN = JSON.parse(read('../../i18n/en.json')) as { order: Record<string, string> };
const AR = JSON.parse(read('../../i18n/ar.json')) as { order: Record<string, string> };

const NEW_KEYS = [
  'loading',
  'no_number',
  'load_failed',
  'retry',
  'story_eyebrow',
  'story_description',
  'list_title',
  'list_subtitle',
  'list_empty_title',
  'list_empty',
  'list_error_title',
  'not_found_desc',
  'access_denied',
  'load_failed_title',
];

describe('OrderTrackingView brand contract (Logo #3)', () => {
  it('has no legacy navy, gold, cream, or slate chrome in code', () => {
    for (const legacy of ['#1B1F3B', '#0C0E1E', '#C5A059', '#A37E44', '#B8935A', '#FDF8EE', '#0F172A']) {
      expect(VIEW, legacy).not.toContain(legacy);
    }
    expect(VIEW).not.toMatch(/\bslate-\d{2,3}\b/);
  });

  it('the return CTA uses a charcoal focus ring, not the global gold ring', () => {
    expect(VIEW).toContain('focus-visible:outline-brand-charcoal');
    const label = VIEW.indexOf("{t('commerce.return_item')}");
    expect(label, 'return CTA label').toBeGreaterThan(-1);
    const cta = VIEW.slice(VIEW.lastIndexOf('<button', label), label);
    expect(cta).toContain('focus-visible:outline-brand-charcoal');
  });

  it('no hard-coded English user-facing copy remains', () => {
    for (const literal of [
      'Loading order tracking',
      'No order number was provided',
      'Fulfillment Story Stack',
      'The order experience uses the card stack',
      'We could not load this order',
      'Order could not be loaded',
    ]) {
      expect(VIEW, literal).not.toContain(literal);
    }
  });

  it('5xx and network failures never show the guest verification form', () => {
    expect(VIEW).toContain('isServerFault');
    // The verify branch must sit behind the server-fault branch, not before it.
    const serverIdx = VIEW.indexOf('if (isServerFault)');
    const guestIdx = VIEW.indexOf('} else if (!isAuthenticated)');
    expect(serverIdx).toBeGreaterThan(-1);
    expect(guestIdx).toBeGreaterThan(serverIdx);
  });

  it('signed-in 404 uses order.not_found and does not show the guest prompt', () => {
    expect(VIEW).toMatch(/else if \(isNotFound\) \{[\s\S]*?t\('order\.not_found'\)/);
  });

  it('dates use the app language, not the browser locale', () => {
    expect(VIEW).not.toContain('toLocaleDateString');
    expect(VIEW).not.toContain('toLocaleString');
    expect(VIEW).toContain('formatDate(order.created_at, lang)');
  });

  it('signed-in /orders lists the customer orders and links each to its detail page', () => {
    expect(VIEW).toContain('commerceService\n      .getOrders()'.replace('\n      ', '\n      '));
    expect(VIEW).toContain('`/orders/${encodeURIComponent(o.order_number)}`');
  });
});

describe('Order tracking copy has EN and AR values for every new key', () => {
  it.each(NEW_KEYS)('%s exists in both locales and AR is not the English text', (key) => {
    const en = EN.order[key];
    const ar = AR.order[key];
    expect(en, `en order.${key}`).toBeTruthy();
    expect(ar, `ar order.${key}`).toBeTruthy();
    expect(ar).not.toBe(en);
    expect(/[\u0600-\u06FF]/.test(ar), `ar order.${key} has Arabic script`).toBe(true);
  });
});
