/**
 * API error code → localized shopper-facing copy (2026-09-23).
 *
 * The rule (audit prompt §26): «كل machine state يجب أن يتحول إلى localized
 * copy. لا تعرض backend English diagnostic message مباشرة كواجهة مستخدم.»
 *
 * Ten consumer views render `err.message` straight into a toast, so an Arabic
 * shopper reads English server diagnostics — including for codes this project
 * itself introduced (`IDEMPOTENCY_KEY_CONFLICT`). The backend message stays the
 * source of truth for the *server*, but the SHOpper needs a sentence in their
 * own language.
 *
 * Deliberate scope: only codes the consumer surface can actually receive are
 * mapped, and an unmapped code falls back to the server's message rather than a
 * generic "something went wrong" — a specific English sentence beats a vague
 * localized one, and inventing a translation for a code this build does not
 * know would be a guess presented as product copy.
 */
import type { TFunction } from 'i18next';

/** code -> i18n key. Keys are literals so the state space is reviewable. */
export const API_ERROR_KEYS: Record<string, string> = {
  IDEMPOTENCY_KEY_CONFLICT: 'errors.idempotency_conflict',
  INSUFFICIENT_STOCK: 'errors.insufficient_stock',
  PAYMENT_FAILED: 'errors.payment_failed',
  BNPL_REJECTED: 'errors.bnpl_rejected',
  PROMO_INELIGIBLE: 'errors.promo_ineligible',
  RETURN_INELIGIBLE: 'errors.return_ineligible',
  FULFILLMENT_PAYMENT_REQUIRED: 'errors.fulfillment_payment_required',
  INVALID_STATE_TRANSITION: 'errors.invalid_state_transition',
  VALIDATION_ERROR: 'errors.validation',
  AUTH_FAILED: 'errors.auth_failed',
  FORBIDDEN_ACCESS: 'errors.forbidden',
  RESOURCE_NOT_FOUND: 'errors.not_found',
  FEATURE_NOT_CONFIGURED: 'errors.not_configured',
  VTON_ENGINE_UNAVAILABLE: 'errors.vton_unavailable',
  VTON_RESULT_GONE: 'errors.vton_result_gone',
  PROVIDER_ERROR: 'errors.provider_error',
  ENCRYPTION_ERROR: 'errors.encryption',
  STYLING_RULE_VIOLATION: 'errors.styling_rule',
  // The client's own HTTP fallback. MEASURED 2026-09-24: with no server message the
  // api client put the transport string `Request failed with status 500` in
  // `message`, and the stylist drawer rendered it verbatim — an Arabic shopper was
  // shown an English transport string and an HTTP status code. The code was already
  // there; only the mapping was missing.
  HTTP_ERROR: 'errors.request_failed',
  // Client-side codes raised by apiClient before/around the response.
  REQUEST_TIMEOUT: 'errors.timeout',
  NETWORK_ERROR: 'errors.network',
  API_NOT_REACHABLE: 'errors.api_unreachable',
  IMAGE_TOO_LARGE: 'errors.image_too_large',
};

type ApiErrorLike = {
  code?: string | null;
  message?: string | null;
  status?: number | null;
};

/**
 * Prefer the localized sentence for a known code; otherwise keep the server's
 * own wording. Never returns an empty string: a silent failure would be worse
 * than an untranslated one.
 */
export function localizeApiError(
  error: unknown,
  t: TFunction | ((key: string) => string),
  fallbackKey = 'errors.generic',
): string {
  const err = (error ?? {}) as ApiErrorLike;
  const code = (err.code ?? '').toString();
  const key = API_ERROR_KEYS[code];
  if (key) {
    const translated = (t as (k: string) => string)(key);
    // i18next returns the key itself when a translation is missing; falling
    // back to the server message is honest, the key path is not.
    if (translated && translated !== key) return translated;
  }
  const serverMessage = (err.message ?? '').toString().trim();
  if (serverMessage) return serverMessage;
  return (t as (k: string) => string)(fallbackKey);
}


/** Codes for which pressing "Retry" cannot possibly help. */
export const NON_RETRYABLE_CODES = new Set([
  'VALIDATION_ERROR',
  'FORBIDDEN_ACCESS',
  'RESOURCE_NOT_FOUND',
  'FEATURE_NOT_CONFIGURED',
  'IMAGE_TOO_LARGE',
  'AUTH_FAILED',
]);

/**
 * Is retrying this failure meaningful?
 *
 * The stylist drawer showed a Retry button for every failure, including a 422
 * validation rejection that no amount of retrying can fix. A control that cannot
 * work is worse than no control: it invites the shopper to loop.
 */
export function isRetryable(error: unknown): boolean {
  const err = (error ?? {}) as ApiErrorLike;
  const code = (err.code ?? '').toString();
  if (NON_RETRYABLE_CODES.has(code)) return false;
  return true;
}

/**
 * The same mapping as `localizeApiError`, expressed as a message DESCRIPTOR so a
 * view-model (which has no i18n context) can hand it to the render boundary —
 * `resolveMessage` then translates it in the active language. Unknown codes keep
 * their server message as a fallback, including the code itself for diagnostics.
 */
export function apiErrorDescriptor(
  error: unknown,
  fallbackKey = 'errors.request_failed',
): { key: string; fallback?: string } {
  const err = (error ?? {}) as ApiErrorLike;
  const code = (err.code ?? '').toString();
  const key = API_ERROR_KEYS[code];
  // The code is carried for logs, never for the screen: `fallback` is only used if
  // the key is missing from every locale, and even then it is a sentence, not a
  // status line.
  return key ? { key } : { key: fallbackKey };
}
