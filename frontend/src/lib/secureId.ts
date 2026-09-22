/**
 * Cryptographically secure identifiers for values that act as capabilities.
 *
 * WHY THIS EXISTS (consumer-role closure 2026-09-22)
 * --------------------------------------------------
 * The guest session token — the bearer capability for a shopper's cart — was
 * generated with `Math.random()`:
 *
 *     token = 'sess_' + Math.random().toString(36).substring(2, 15)
 *                    + Date.now().toString(36);
 *
 * `Math.random()` is a non-cryptographic PRNG (V8: xorshift128+). Its internal
 * state is recoverable from a modest number of observed outputs, so tokens are
 * *predictable*, not merely low-entropy. `Date.now()` adds no entropy an
 * attacker targeting one account does not already have (it is observable to
 * within a few milliseconds).
 *
 * That matters because the token is not a cache key — it is a credential, and
 * the backend treats it as one:
 *
 *   * `CommerceRepository.get_or_create_cart(session_token, user_id)` looks the
 *     cart up by `session_token` **when there is no authenticated user**, so
 *     possession of the token is sufficient to read and mutate that cart;
 *   * `Order.guest_session_token`, `TryOnSession.guest_session_token` and
 *     `TryOnJob.guest_session_token` are indexed, durable join keys
 *     (`backend/app/models/commerce.py`, `backend/app/models/tryon.py`), so the
 *     same value also reaches order and try-on history.
 *
 * A predictable capability is an IDOR waiting for an attacker to do the
 * arithmetic, so the entropy requirement is a security property, not a style
 * preference. This module is the one place that property is met.
 *
 * FAIL CLOSED, NOT SILENTLY INSECURE
 * ----------------------------------
 * `crypto.getRandomValues` exists in every browser since 2012 and in every
 * supported Node runtime, so the throw below should be unreachable in practice.
 * It exists deliberately: the alternative — silently falling back to
 * `Math.random()` — is how the original defect would survive a refactor, and a
 * capability token that is only *sometimes* unpredictable is not a control.
 * A loud failure is recoverable; a silent one is not.
 */

/** Which CSPRNG source produced (or would produce) an identifier. */
export type SecureRandomSource = "randomUUID" | "getRandomValues";

/**
 * The CSPRNG available in this runtime, or `null` when there is none.
 *
 * `randomUUID` is only defined in secure contexts (https, localhost), so a
 * non-secure-context deployment falls through to `getRandomValues`, which is
 * not secure-context restricted.
 */
export function secureRandomSource(): SecureRandomSource | null {
  const c = typeof globalThis !== "undefined" ? globalThis.crypto : undefined;
  if (!c) return null;
  if (typeof c.randomUUID === "function") return "randomUUID";
  if (typeof c.getRandomValues === "function") return "getRandomValues";
  return null;
}

/** 128 bits of CSPRNG output as lowercase hex (32 chars). */
function randomHex128(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * A `${prefix}_${128-bit-random}` identifier.
 *
 * The prefix is preserved for the callers that already rely on it (the session
 * token is `sess_…` and the backend column is `String(100)`), and the random
 * component is 128 bits in both branches so entropy does not depend on which
 * CSPRNG the runtime happened to expose.
 *
 * @throws Error when the runtime exposes no CSPRNG — never falls back to a
 *   non-cryptographic generator for a value that acts as a credential.
 */
export function randomSecureId(prefix: string): string {
  const source = secureRandomSource();
  if (source === "randomUUID") {
    // Dash-free for a compact, URL-safe token that matches the hex branch.
    return `${prefix}_${globalThis.crypto.randomUUID().replace(/-/g, "")}`;
  }
  if (source === "getRandomValues") {
    return `${prefix}_${randomHex128()}`;
  }
  throw new Error(
    "No cryptographically secure random source is available " +
      "(crypto.randomUUID / crypto.getRandomValues). Refusing to generate a " +
      "session capability from a non-cryptographic PRNG.",
  );
}

/**
 * The guest session token. Kept as a named export because the shape (`sess_`)
 * and the persistence key are part of the existing contract.
 */
export function generateSessionToken(): string {
  return randomSecureId("sess");
}

/**
 * A client-generated idempotency key for checkout.
 *
 * Checkout previously used `randomUUID()` when available and `Math.random()`
 * otherwise. The key is what tells the payment/order layer that a retry is the
 * *same* purchase rather than a second one, so a collision is a correctness
 * bug (a replay could be answered with the wrong order) as well as a
 * predictability one. Same source, no non-crypto path.
 */
export function generateIdempotencyKey(): string {
  return randomSecureId("chk");
}
