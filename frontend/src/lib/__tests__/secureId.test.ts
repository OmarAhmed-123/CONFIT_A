/**
 * The guest session token is a CREDENTIAL — it must come from a CSPRNG.
 *
 * The defect (2026-09-22 consumer-role closure)
 * --------------------------------------------
 * `getSessionToken()` minted the token as:
 *
 *     'sess_' + Math.random().toString(36).substring(2, 15) + Date.now().toString(36)
 *
 * `Math.random()` is a non-cryptographic PRNG (V8: xorshift128+); its internal
 * state is recoverable from observed outputs, so the token is *predictable*
 * rather than merely low-entropy, and `Date.now()` adds nothing an attacker
 * targeting one account does not already know.
 *
 * That is a live access-control problem, not a style issue, because the backend
 * uses this value as the credential for an unauthenticated caller's cart —
 * `CommerceRepository.get_or_create_cart(session_token, user_id)` resolves the
 * cart by `session_token` when `user_id` is absent — and the same column is an
 * indexed join key on `Order.guest_session_token` and
 * `TryOnSession/TryOnJob.guest_session_token`.
 *
 * The decisive test below does not merely check "the value looks random". It
 * pins `Math.random()` to a constant and asserts tokens STILL differ, which
 * fails loudly for any implementation that goes back to a non-crypto source.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  generateSessionToken,
  generateIdempotencyKey,
  randomSecureId,
  secureRandomSource,
} from '../secureId';

/** The old, insecure derivation — used to prove the test actually discriminates. */
function legacyToken(): string {
  return (
    'sess_' +
    Math.random().toString(36).substring(2, 15) +
    Date.now().toString(36)
  );
}

describe('secureId — capability identifiers use a CSPRNG', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('exposes a cryptographically secure source in this runtime', () => {
    // jsdom + Node provide webcrypto; if this ever fails, the suite cannot
    // assert the property and should be treated as an environment problem.
    expect(secureRandomSource()).toMatch(/randomUUID|getRandomValues/);
  });

  it('generates the sess_ token shape the backend contract expects', () => {
    const token = generateSessionToken();
    expect(token.startsWith('sess_')).toBe(true);
    // `carts.session_token` is String(100); the random component is 128 bits
    // (32 hex chars) in both CSPRNG branches, so this bound is structural.
    expect(token.length).toBeLessThanOrEqual(100);
    expect(token.length).toBeGreaterThan(6);
  });

  it('is unpredictable even when Math.random is pinned to a constant', () => {
    // THE regression assertion. A non-crypto implementation returns identical
    // tokens here, because both its inputs (Math.random, Date.now) are pinned
    // or near-constant. This is what makes the test discriminating rather than
    // decorative.
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    const tokens = new Set(Array.from({ length: 50 }, () => generateSessionToken()));
    expect(tokens.size).toBe(50);
  });

  it('demonstrates the legacy derivation WAS predictable under the same pin', () => {
    // Guard against a vacuous test: proves the pin above is strong enough to
    // collapse a non-crypto token, so the uniqueness assertion is meaningful.
    //
    // Both inputs are pinned this time. On the first attempt only
    // `Math.random` was pinned and 50 calls produced 2 distinct values — the
    // sole source of variation was `Date.now()` crossing one millisecond
    // boundary. That is the defect stated precisely: with the PRNG pinned, the
    // token's entropy was a *clock reading*, so every token minted inside the
    // same millisecond was byte-identical.
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    vi.spyOn(Date, 'now').mockReturnValue(1_760_000_000_000);
    const legacy = new Set(Array.from({ length: 50 }, () => legacyToken()));
    expect(legacy.size).toBe(1);
  });

  it('produces distinct values across calls and prefixes', () => {
    const a = generateSessionToken();
    const b = generateSessionToken();
    expect(a).not.toBe(b);
    expect(generateIdempotencyKey().startsWith('chk_')).toBe(true);
    expect(generateSessionToken()).not.toBe(generateIdempotencyKey());
  });

  it('does not collide at the scale a session store would see', () => {
    const n = 5000;
    const seen = new Set<string>();
    for (let i = 0; i < n; i += 1) seen.add(generateSessionToken());
    expect(seen.size).toBe(n);
  });

  it('fails closed instead of silently using a non-crypto generator', () => {
    // The whole point: a capability token that is only sometimes unpredictable
    // is not a control. A loud failure is recoverable; a silent one is not.
    const original = globalThis.crypto;
    // Deliberately remove the crypto global for this test. Deleting through a
    // mutable view of the global avoids the `@ts-expect-error` that the
    // non-optional `crypto` property would otherwise require — an unused
    // directive is itself a type error under the project's tsc settings.
    const mutableGlobal = globalThis as unknown as Record<string, unknown>;
    delete mutableGlobal.crypto;
    try {
      expect(secureRandomSource()).toBeNull();
      expect(() => generateSessionToken()).toThrow(/secure random source/i);
    } finally {
      Object.defineProperty(globalThis, 'crypto', {
        value: original,
        configurable: true,
      });
    }
  });

  it('falls back to getRandomValues when randomUUID is unavailable', () => {
    // randomUUID requires a secure context; getRandomValues does not. A
    // deployment on plain http must still get crypto-grade tokens.
    const original = globalThis.crypto;
    Object.defineProperty(globalThis, 'crypto', {
      value: { getRandomValues: original.getRandomValues.bind(original) },
      configurable: true,
    });
    try {
      expect(secureRandomSource()).toBe('getRandomValues');
      const t1 = randomSecureId('t');
      const t2 = randomSecureId('t');
      expect(t1).not.toBe(t2);
      expect(t1).toMatch(/^t_[0-9a-f]{32}$/);
    } finally {
      Object.defineProperty(globalThis, 'crypto', {
        value: original,
        configurable: true,
      });
    }
  });

  it('uses 128 bits in both branches (entropy must not depend on the runtime)', () => {
    expect(randomSecureId('x')).toMatch(/^x_[0-9a-f]{32}$/);
  });
});

describe('getSessionToken — persistence contract is preserved', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it('persists once and returns the same token on every later call', async () => {
    const { getSessionToken } = await import('../../services/apiClient');
    const first = getSessionToken();
    const second = getSessionToken();
    expect(second).toBe(first);
    expect(localStorage.getItem('confit_session_token')).toBe(first);
  });

  it('keeps an existing token (no unnecessary re-mint on upgrade)', async () => {
    // A stored token from a previous version must keep working: re-minting
    // would orphan the guest's cart and order join keys.
    localStorage.setItem('confit_session_token', 'sess_existing_token_value');
    const { getSessionToken } = await import('../../services/apiClient');
    expect(getSessionToken()).toBe('sess_existing_token_value');
  });
});
