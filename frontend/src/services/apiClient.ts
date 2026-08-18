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

// Generate or retrieve persistent guest session token
export const getSessionToken = (): string => {
  let token = localStorage.getItem('confit_session_token');
  if (!token) {
    token = 'sess_' + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
    localStorage.setItem('confit_session_token', token);
  }
  return token;
};

export const getAuthToken = (): string | null => {
  const token = localStorage.getItem('confit_access_token');
  if (!token || token === 'null' || token === 'undefined' || token.trim() === '') {
    return null;
  }
  return token.trim();
};

export const setAuthTokens = (access: string, refresh: string) => {
  localStorage.setItem('confit_access_token', access);
  localStorage.setItem('confit_refresh_token', refresh);
};

export const clearAuthTokens = () => {
  localStorage.removeItem('confit_access_token');
  localStorage.removeItem('confit_refresh_token');
  localStorage.removeItem('confit_user');
};

export async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  // Inject session token for guest carts and anonymous session identification
  headers.set('X-Session-Token', getSessionToken());

  // Attach Authorization Bearer token strictly when a valid token exists
  const token = getAuthToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (!res.ok) {
      let errJson: any = {};
      try {
        errJson = await res.json();
      } catch (e) {
        // Non-JSON response
      }
      const err = errJson.error || {};
      let userFriendlyMessage = err.message || `Request failed with status ${res.status}`;

      // Normalize raw auth errors into polite, human-readable microcopy (Section 5.4)
      if (res.status === 401 || (userFriendlyMessage && userFriendlyMessage.toLowerCase().includes('bearer token'))) {
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
    throw new ApiError(err.message || 'Network communication failure', 'NETWORK_ERROR', 0);
  }
}
