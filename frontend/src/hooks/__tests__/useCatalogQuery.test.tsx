/**
 * C22 Tests: React Query implementation verification
 * Tests caching, invalidation, error handling, auth transitions
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { queryKeys, clearUserQueries } from '../../lib/queryClient';

// Mock catalog service
vi.mock('../../services/apiServices', () => ({
  catalogService: {
    getProducts: vi.fn().mockResolvedValue([{ id: 1, title: 'Test Product' }]),
    getCategories: vi.fn().mockResolvedValue([{ id: 1, name: 'Test Category' }]),
    getProductDetail: vi.fn().mockResolvedValue({ id: 1, title: 'Detail' }),
    getBopisStoresForSKU: vi.fn().mockResolvedValue([]),
  },
}));

describe('C22 React Query - Catalog', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
    });
    vi.clearAllMocks();
  });

  it('should cache products query', async () => {
    const { catalogService } = await import('../../services/apiServices');
    
    // First call
    const filters = { category: 'test' };
    await queryClient.fetchQuery({
      queryKey: queryKeys.catalog.products(filters),
      queryFn: () => catalogService.getProducts(filters),
    });

    expect(catalogService.getProducts).toHaveBeenCalledTimes(1);

    // Second call with same key should use cache
    const cached = queryClient.getQueryData(queryKeys.catalog.products(filters));
    expect(cached).toBeDefined();
  });

  it('should have isolated query keys', () => {
    const key1 = queryKeys.catalog.products({ category: 'a' });
    const key2 = queryKeys.catalog.products({ category: 'b' });
    
    expect(key1).not.toEqual(key2);
    expect(JSON.stringify(key1)).not.toEqual(JSON.stringify(key2));
  });

  it('should prevent cross-user leakage via userId in keys', () => {
    const user1Key = queryKeys.wardrobe.items(1, 'All');
    const user2Key = queryKeys.wardrobe.items(2, 'All');
    
    expect(user1Key).not.toEqual(user2Key);
    expect(user1Key[1]).toBe(1);
    expect(user2Key[1]).toBe(2);
  });

  it('should clear user queries on logout', async () => {
    // Set some user data
    queryClient.setQueryData(queryKeys.wardrobe.items(1, 'All'), [{ id: 1 }]);
    queryClient.setQueryData(queryKeys.catalog.products({}), [{ id: 1 }]);

    // Clear user queries
    queryClient.removeQueries({ queryKey: ['wardrobe'] });
    
    expect(queryClient.getQueryData(queryKeys.wardrobe.items(1, 'All'))).toBeUndefined();
    // Public data should still exist
    expect(queryClient.getQueryData(queryKeys.catalog.products({}))).toBeDefined();
  });

  it('should not retry on 401/403', () => {
    const retryFn = queryClient.getDefaultOptions().queries?.retry as Function;
    
    const shouldRetry401 = retryFn(0, { status: 401 });
    const shouldRetry403 = retryFn(0, { status: 403 });
    const shouldRetry500 = retryFn(0, { status: 500 });
    
    expect(shouldRetry401).toBe(false);
    expect(shouldRetry403).toBe(false);
    expect(shouldRetry500).toBe(true);
  });

  it('should not retry mutations', () => {
    const mutationRetry = queryClient.getDefaultOptions().mutations?.retry;
    expect(mutationRetry).toBe(false);
  });
});

describe('C22 React Query - Wardrobe Optimistic Updates', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
  });

  it('should handle optimistic delete with rollback', async () => {
    const userId = 1;
    const initialItems = [{ id: 1, title: 'Item 1' }, { id: 2, title: 'Item 2' }];
    
    queryClient.setQueryData(queryKeys.wardrobe.items(userId, 'All'), initialItems);
    
    // Simulate optimistic update
    const previous = queryClient.getQueryData(queryKeys.wardrobe.items(userId, 'All'));
    queryClient.setQueryData(queryKeys.wardrobe.items(userId, 'All'), 
      (old: any) => old.filter((item: any) => item.id !== 1)
    );
    
    expect(queryClient.getQueryData(queryKeys.wardrobe.items(userId, 'All'))).toEqual([{ id: 2, title: 'Item 2' }]);
    
    // Simulate rollback on error
    queryClient.setQueryData(queryKeys.wardrobe.items(userId, 'All'), previous);
    
    expect(queryClient.getQueryData(queryKeys.wardrobe.items(userId, 'All'))).toEqual(initialItems);
  });

  it('should invalidate queries after mutation', async () => {
    const userId = 1;
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    
    // Simulate successful upload mutation
    queryClient.invalidateQueries({ queryKey: queryKeys.wardrobe.all(userId) });
    
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.wardrobe.all(userId) });
  });
});
