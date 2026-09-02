import { QueryClient } from '@tanstack/react-query';

/**
 * C22 FIX: Production-grade QueryClient configuration
 * - Prevents infinite retries
 * - Prevents cross-user cache leakage via proper key isolation
 * - Configures staleTime and gcTime for optimal UX
 * - Ensures auth transitions clear sensitive cache
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Prevent infinite retry loops
      retry: (failureCount, error: any) => {
        // Don't retry on auth errors (401/403) - prevents retry storm
        if (error?.status === 401 || error?.status === 403) {
          return false;
        }
        // Don't retry on client errors (4xx) except 408/429
        if (error?.status >= 400 && error?.status < 500) {
          if (error?.status === 408 || error?.status === 429) {
            return failureCount < 2;
          }
          return false;
        }
        // Retry server errors up to 2 times
        return failureCount < 2;
      },
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      // Cache config - prevents unnecessary refetch loops
      staleTime: 1000 * 60 * 5, // 5 minutes - data considered fresh
      gcTime: 1000 * 60 * 30, // 30 minutes - cache retention
      refetchOnWindowFocus: false, // Prevent refetch storm on focus
      refetchOnReconnect: true, // Refetch on reconnect is useful
      refetchOnMount: false, // Don't refetch on mount if fresh
    },
    mutations: {
      retry: false, // Never retry mutations - prevents duplicate operations
    },
  },
});

/**
 * Clear all cached data on logout/auth transition
 * Prevents cross-user cache leakage
 */
export const clearQueryCacheOnLogout = () => {
  queryClient.clear();
};

/**
 * Clear user-specific queries only (for auth transitions)
 * Preserves public data like catalog
 */
export const clearUserQueries = () => {
  // Remove all queries that contain user-specific data
  queryClient.removeQueries({ queryKey: ['wardrobe'] });
  queryClient.removeQueries({ queryKey: ['profile'] });
  queryClient.removeQueries({ queryKey: ['cart'] });
  queryClient.removeQueries({ queryKey: ['orders'] });
  queryClient.removeQueries({ queryKey: ['tryon'] });
  queryClient.removeQueries({ queryKey: ['user'] });
};

/**
 * Query key factory - ensures consistent, isolated keys
 * Prevents key collisions and cross-user leakage
 */
export const queryKeys = {
  // Public - no user isolation needed
  catalog: {
    all: ['catalog'] as const,
    products: (filters?: Record<string, any>) => ['catalog', 'products', filters] as const,
    categories: () => ['catalog', 'categories'] as const,
    brands: () => ['catalog', 'brands'] as const,
    productDetail: (slug: string) => ['catalog', 'product', slug] as const,
    bopis: (skuId: number) => ['catalog', 'bopis', skuId] as const,
  },
  // User-specific - MUST include userId for isolation
  wardrobe: {
    all: (userId?: number) => ['wardrobe', userId] as const,
    items: (userId?: number, category?: string) => ['wardrobe', userId, 'items', category] as const,
    gaps: (userId?: number) => ['wardrobe', userId, 'gaps'] as const,
    outfitSuggestions: (userId?: number, occasion?: string) => ['wardrobe', userId, 'outfit', occasion] as const,
  },
  profile: {
    all: (userId?: number) => ['profile', userId] as const,
    me: (userId?: number) => ['profile', userId, 'me'] as const,
    style: (userId?: number) => ['profile', userId, 'style'] as const,
  },
  cart: {
    all: (sessionToken?: string, userId?: number) => ['cart', sessionToken, userId] as const,
    detail: (sessionToken?: string, userId?: number) => ['cart', 'detail', sessionToken, userId] as const,
  },
  orders: {
    all: (userId?: number) => ['orders', userId] as const,
    detail: (orderId: string, userId?: number) => ['orders', userId, 'detail', orderId] as const,
  },
  tryon: {
    all: (userId?: number) => ['tryon', userId] as const,
    session: (sessionId: number, userId?: number) => ['tryon', userId, 'session', sessionId] as const,
    job: (jobId: string) => ['tryon', 'job', jobId] as const,
  },
};
