import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  CURRENCY_CHANGED_EVENT,
  currencyHeaders,
  getPreferredCurrency,
  setPreferredCurrency,
} from '../currency';

/**
 * The contract these tests protect: the browser stores a CHOICE and nothing
 * else. If a rate or a conversion ever appears on the client, the storefront
 * can disagree with the checkout — which is the exact production defect
 * (cart "USD" vs payment-methods "EGP") this feature was built to remove.
 */
describe('presentation currency (client)', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('has no preference by default, which is NOT the same as USD', () => {
    expect(getPreferredCurrency()).toBeNull();
    // No header at all => the backend applies the market default. Sending
    // "USD" here would override an Egyptian shopper's correct EGP default.
    expect(currencyHeaders()).toEqual({});
  });

  it('round-trips a valid choice and sends it as X-Currency', () => {
    setPreferredCurrency('EGP');
    expect(getPreferredCurrency()).toBe('EGP');
    expect(currencyHeaders()).toEqual({ 'X-Currency': 'EGP' });
  });

  it('clears back to the market default', () => {
    setPreferredCurrency('SAR');
    setPreferredCurrency(null);
    expect(getPreferredCurrency()).toBeNull();
    expect(currencyHeaders()).toEqual({});
  });

  it('refuses a malformed code instead of putting garbage on the wire', () => {
    setPreferredCurrency('EGP');
    setPreferredCurrency('not-a-currency');
    expect(getPreferredCurrency()).toBe('EGP');
  });

  it('ignores a corrupted storage value', () => {
    localStorage.setItem('confit_currency', '{"x":1}');
    expect(getPreferredCurrency()).toBeNull();
  });

  it('announces the change so cached prices can be invalidated', () => {
    const listener = vi.fn();
    window.addEventListener(CURRENCY_CHANGED_EVENT, listener);
    setPreferredCurrency('AED');
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(CURRENCY_CHANGED_EVENT, listener);
  });

  it('survives storage being unavailable (private browsing)', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    expect(() => getPreferredCurrency()).not.toThrow();
    expect(getPreferredCurrency()).toBeNull();
    getItem.mockRestore();
  });

  it('exports no conversion helper — rates are server-side only', async () => {
    const mod = await import('../currency');
    const exported = Object.keys(mod);
    expect(exported.some((name) => /convert|rate(?!_)/i.test(name))).toBe(false);
  });
});
