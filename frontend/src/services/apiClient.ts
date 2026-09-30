import { generateSessionToken } from '../lib/secureId';
import { currencyHeaders } from '../lib/currency';

const API_BASE_URL = '/api/v1';

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, any>;

  constructor(message: string, code = 'API_ERROR', status = 500, details = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

// Generate or retrieve the persistent guest session token.
//
// This value is a CREDENTIAL, not a cache key: the backend resolves the cart by
// `session_token` for unauthenticated callers, and the same value is an indexed
// join key on orders and try-on sessions. It was previously derived from
// `Math.random()` + `Date.now()`, which is predictable; see lib/secureId.ts for
// the reasoning and the fail-closed policy. (2026-09-22 consumer closure.)
export const getSessionToken = (): string => {
  let token = localStorage.getItem('confit_session_token');
  if (!token) {
    token = generateSessionToken();
    localStorage.setItem('confit_session_token', token);
  }
  return token;
};

// Session tokens live in an httpOnly cookie (set by the backend at login) —
// they are intentionally NOT readable from JavaScript, so an XSS payload
// cannot exfiltrate a session. getAuthToken remains only for API-client
// compatibility and always returns null in the browser.
export const getAuthToken = (): string | null => null;

// The backend sets the session cookie itself; nothing token-shaped is ever
// written to web storage. Kept as a no-op so existing call sites compile.
export const setAuthTokens = (_access: string, _refresh: string) => {};

export const clearAuthTokens = () => {
  localStorage.removeItem('confit_user');
  localStorage.removeItem('confit_access_token'); // purge any pre-migration leftovers
  localStorage.removeItem('confit_refresh_token');
  document.cookie = 'confit_csrf=; Max-Age=0; path=/';
};

// Double-submit CSRF token: the readable confit_csrf cookie, echoed back as a
// header on mutating requests (the backend compares header vs cookie).
const getCsrfToken = (): string | null => {
  const m = document.cookie.match(/(?:^|;\s*)confit_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
};

// SEARCH-01 hardening: no frontend state may hang forever on a stalled
// request (the audit's eternal 'Analyzing...' class). 30s covers serverless
// cold starts + VTON's long-poll budget; per-call overrides via
// options.signal still win (AbortSignal.any keeps both cancellable).
const DEFAULT_TIMEOUT_MS = 30_000;

/**
 * Endpoints that legitimately run longer than the default, with the budget
 * they actually need.
 *
 * WHY THIS EXISTS
 * ---------------
 * Every request shared one 30s ceiling. A virtual try-on render measured
 * ~22s for a SINGLE garment layer, and a multi-layer outfit applies each
 * layer in turn — so a two-piece look needs ~40s before the queue is even
 * counted. The client aborted at 30s and surfaced
 * "The request timed out. Please try again.", which reads as a backend
 * failure when in fact the server was still working and Vercel allows the
 * function 300s (vercel.json maxDuration).
 *
 * The budget lives here, keyed by endpoint prefix, rather than as a magic
 * number passed at each call site: a per-call override drifts, and the
 * render paths are reached from four different view-models.
 *
 * Kept BELOW the 300s server ceiling so the client never gives up on work
 * the server would still have delivered.
 */
const LONG_RUNNING_TIMEOUTS_MS: ReadonlyArray<readonly [string, number]> = [
  // Multi-garment: one diffusion pass per layer, sequentially.
  ['/tryon/animation-render', 240_000],
  ['/tryon/multi-render', 240_000],
  // Single garment, still a full diffusion pass.
  ['/tryon/render', 150_000],
  ['/try-on/jobs', 150_000],
  // Vision analysis: slower than a CRUD call, far faster than a render.
  ['/tryon/visual-search', 60_000],
  ['/tryon/validate-image', 60_000],
];

/** Timeout budget for an endpoint. Longest matching prefix wins. */
export function timeoutForEndpoint(endpoint: string): number {
  let best = DEFAULT_TIMEOUT_MS;
  let bestLen = -1;
  for (const [prefix, ms] of LONG_RUNNING_TIMEOUTS_MS) {
    if (endpoint.startsWith(prefix) && prefix.length > bestLen) {
      best = ms;
      bestLen = prefix.length;
    }
  }
  return best;
}

async function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const signal = options.signal
      ? (typeof AbortSignal.any === 'function' ? AbortSignal.any([options.signal, controller.signal]) : options.signal)
      : controller.signal;
    return await fetch(url, { ...options, signal });
  } finally {
    clearTimeout(timer);
  }
}

// CYCLE-3 (BLOCKER J): transparent session renewal. The access cookie is
// short-lived; when it expires the backend answers 401. The browser holds an
// httpOnly refresh cookie (set at login, rotated on every refresh), so ONE
// refresh attempt + ONE retry of the original request keeps the user signed
// in without any token ever reaching web storage. If renewal fails, the
// session is honestly expired: local user state is purged and a
// 'confit:session-expired' event lets the auth store clear itself.
let refreshInFlight: Promise<boolean> | null = null;

export const SESSION_EXPIRED_EVENT = 'confit:session-expired';

async function trySessionRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
          credentials: 'same-origin',
        });
        if (res.ok) return true;
        return false;
      } catch {
        return false;
      } finally {
        // Release the slot the moment the outcome is known. Callers that
        // raced in WHILE the refresh was pending already hold the shared
        // promise reference, so they keep the single-flight guarantee; a
        // LATER 401 (e.g. after a retry also expired) may open a fresh,
        // bounded refresh attempt. No timer delay — a lingering resolved
        // promise would serve stale results to unrelated later calls.
        refreshInFlight = null;
      }
    })();
    const ok = await refreshInFlight;
    if (!ok) {
      try { localStorage.removeItem('confit_user'); } catch {}
      try { window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT)); } catch {}
    }
    return ok;
  }
  return refreshInFlight;
}

export async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  isRetry = false
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  // Inject session token for guest carts and anonymous session identification
  headers.set('X-Session-Token', getSessionToken());

  // Presentation currency. Sent on EVERY request rather than on the price
  // endpoints only: the shopper's choice must reach any handler that returns
  // money, and adding it here means a new priced endpoint cannot forget it.
  // Absent header = "use the market default", which is a real answer, not a
  // missing one (see frontend/src/lib/currency.ts).
  for (const [key, value] of Object.entries(currencyHeaders())) {
    headers.set(key, value);
  }

  // Auth travels via the httpOnly session cookie (same-origin). No Bearer
  // header is attached from JS — there is deliberately no readable token.
  const method = (options.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = getCsrfToken();
    if (csrf) {
      headers.set('X-CSRF-Token', csrf);
    }
  }

  try {
    const res = await fetchWithTimeout(url, { ...options, headers }, timeoutForEndpoint(endpoint));

    // P0-02: surface gateway body-limit failures (HTTP 413) with an
    // actionable message instead of an opaque FUNCTION_PAYLOAD_TOO_LARGE.
    if (res.status === 413) {
      throw new ApiError(
        'That image is too large to upload. Please try a smaller photo.',
        'IMAGE_TOO_LARGE',
        413
      );
    }
    if (res.ok) {
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        return await res.json();
      }
      // A 200 with a non-JSON body means the request never reached the API
      // (e.g. static hosting returned index.html). That is an error — it must
      // never be parsed as a payload or routed into a fabricated fallback.
      throw new ApiError(
        'The server returned a non-JSON response. The API may not be deployed.',
        'API_NOT_REACHABLE',
        res.status
      );
    }

    // Session renewal: a 401 from anything OTHER than the auth endpoints
    // themselves means the access cookie expired. Try ONE transparent
    // refresh (single-flight, cookie-based) and replay the request once.
    // A second 401, or a failed refresh, falls through to the honest error
    // path below — never a loop.
    if (
      res.status === 401 &&
      !isRetry &&
      !/^\/auth\/(login|register|refresh|mfa|forgot-password|reset-password|social-login)/.test(endpoint)
    ) {
      if (await trySessionRefresh()) {
        return request<T>(endpoint, options, true);
      }
    }

    // If the endpoint returned an HTTP error (including 404/405 from a static
    // CDN), surface the real failure. The old client-side catalog fallback —
    // which fabricated products/categories/brands on ANY !res.ok — was removed
    // deliberately (N-1): fabricated catalogue data on a backend outage is a
    // dishonesty class the remediation contract prohibits. The UI renders an
    // honest error + retry state instead.
    if (!res.ok) {
      let errJson: any = {};
      try {
        errJson = await res.json();
      } catch (e) {}

      const err = errJson.error || {};
      let userFriendlyMessage = err.message || `Request failed with status ${res.status}`;

      // Audit round-2 (R9): an AUTH ATTEMPT must surface the server's own
      // message ("Invalid email or password."). Rewriting EVERY 401 into the
      // generic sign-in nudge hid real login failures — the user typed a
      // wrong password and was told to "sign in", with no error. The nudge
      // remains correct for OTHER endpoints, where 401 means the session is
      // missing/expired. Cycle 9: change-password 401s are re-authentication
      // failures ("Current password is incorrect."), not session expiry.
      const isAuthAttempt = /^\/auth\/(login|register|mfa|change-password)/.test(endpoint);
      if (
        (res.status === 401 ||
          (userFriendlyMessage && userFriendlyMessage.toLowerCase().includes('bearer token'))) &&
        !isAuthAttempt
      ) {
        userFriendlyMessage = 'Sign in to access your personal style profile and account features.';
      }

      throw new ApiError(
        userFriendlyMessage,
        err.code || (res.status === 401 ? 'AUTH_REQUIRED' : 'HTTP_ERROR'),
        res.status,
        err.details || {}
      );
    }

    return await res.json();
  } catch (err: any) {
    if (err instanceof ApiError) {
      throw err;
    }
    // Distinguish a user/timeout abort from a connection failure so callers
    // can render 'cancelled' vs 'network error' honestly.
    if (err?.name === 'AbortError') {
      throw new ApiError('The request timed out. Please try again.', 'REQUEST_TIMEOUT', 0);
    }
    throw new ApiError(err.message || 'Network communication failure', 'NETWORK_ERROR', 0);
  }
}

// N-1 (catalog fallback removal): the ~300-line client-side catalogue fallback
// (FALLBACK_PRODUCTS / FALLBACK_CATEGORIES / FALLBACK_BRANDS and
// handleEdgeFallback) was deleted. It silently served a hardcoded nine-product
// catalogue on ANY /catalog/* failure — a backend outage, a 500, or a static-
// hosting 405 all rendered as a fully stocked store (fabricated ratings,
// stock levels and style scores included). This is the same dishonesty class
// the security audit S1 already removed for auth/chat/checkout fallbacks;
// reference data deserved no exemption: a customer who "browses" products
// that do not exist is being lied to, and add-to-cart/try-on flows built on
// fabricated SKUs fail downstream in confusing ways.
//
// Contract now: /catalog/* failures throw the real ApiError
// (HTTP_ERROR / API_NOT_REACHABLE / NETWORK_ERROR / REQUEST_TIMEOUT) and the
// catalogue views render an explicit error state with a Retry action.
// No fabricated data may be reintroduced client-side.
