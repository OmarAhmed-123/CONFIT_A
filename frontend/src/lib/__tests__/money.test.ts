import { describe, it, expect } from 'vitest';
import { formatMoney } from '../money';

describe('formatMoney', () => {
  it('renders USD with the dollar symbol', () => {
    expect(formatMoney(1234.5, 'USD')).toBe('$1,234.50');
  });

  it('renders EGP with the ISO code, never a fabricated $', () => {
    expect(formatMoney(3000.0, 'EGP')).toBe('3,000.00 EGP');
  });

  it('renders AED with the ISO code', () => {
    expect(formatMoney(1499, 'AED')).toBe('1,499.00 AED');
  });

  it('falls back to USD when currency is missing', () => {
    expect(formatMoney(10, undefined)).toBe('$10.00');
    expect(formatMoney(10, null)).toBe('$10.00');
  });

  it('treats unknown currencies by showing their code', () => {
    expect(formatMoney(5, 'XYZ')).toBe('5.00 XYZ');
  });

  it('guards against non-finite input', () => {
    expect(formatMoney(Number.NaN, 'USD')).toBe('$0.00');
  });
});
