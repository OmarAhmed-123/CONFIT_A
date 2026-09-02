import { useQuery, useQueryClient } from '@tanstack/react-query';
import { catalogService } from '../services/apiServices';
import { queryKeys } from '../lib/queryClient';
import { Product, Category } from '../models';

/**
 * C22 FIX: React Query implementation for catalog
 * - Server state managed by React Query
 * - Proper caching with staleTime
 * - No manual useEffect/useState for server data
 * - Query keys prevent cross-user leakage (public data, no user ID needed)
 */

interface CatalogFilters {
  category?: string;
  occasion?: string;
  color?: string;
  search?: string;
  sort_by?: string;
}

export function useCatalogProducts(filters: CatalogFilters) {
  return useQuery({
    queryKey: queryKeys.catalog.products(filters),
    queryFn: () => catalogService.getProducts(filters),
    staleTime: 1000 * 60 * 5, // 5 min fresh
    gcTime: 1000 * 60 * 30, // 30 min cache
    placeholderData: (previousData) => previousData, // Keep previous data while fetching new
  });
}

export function useCatalogCategories() {
  return useQuery({
    queryKey: queryKeys.catalog.categories(),
    queryFn: () => catalogService.getCategories(),
    staleTime: 1000 * 60 * 10, // 10 min - categories rarely change
    gcTime: 1000 * 60 * 60, // 1 hour cache
  });
}

export function useProductDetail(slug: string) {
  return useQuery({
    queryKey: queryKeys.catalog.productDetail(slug),
    queryFn: () => catalogService.getProductDetail(slug),
    enabled: !!slug,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
  });
}

export function useBopisStores(skuId: number | null) {
  return useQuery({
    queryKey: queryKeys.catalog.bopis(skuId || 0),
    queryFn: () => catalogService.getBopisStoresForSKU(skuId!),
    enabled: !!skuId,
    staleTime: 1000 * 60 * 2, // 2 min - inventory changes
    gcTime: 1000 * 60 * 10,
    retry: 1, // Don't retry too much for BOPIS
  });
}

/**
 * Combined catalog ViewModel using React Query
 * Replaces manual useEffect/useState implementation
 */
export function useCatalogQueryViewModel() {
  const [filters, setFilters] = useState<FiltersState>({
    category: '',
    occasion: '',
    color: '',
    search: '',
    sortBy: 'recommended',
  });

  const productsQuery = useCatalogProducts({
    category: filters.category || undefined,
    occasion: filters.occasion || undefined,
    color: filters.color || undefined,
    search: filters.search || undefined,
    sort_by: filters.sortBy,
  });

  const categoriesQuery = useCatalogCategories();

  return {
    products: productsQuery.data || [],
    categories: categoriesQuery.data || [],
    isLoading: productsQuery.isLoading || categoriesQuery.isLoading,
    isFetching: productsQuery.isFetching,
    error: productsQuery.error || categoriesQuery.error,
    filters,
    setFilters,
    // For backward compatibility with existing code
    selectedCategory: filters.category,
    setSelectedCategory: (cat: string) => setFilters((f) => ({ ...f, category: cat })),
    selectedOccasion: filters.occasion,
    setSelectedOccasion: (occ: string) => setFilters((f) => ({ ...f, occasion: occ })),
    searchQuery: filters.search,
    setSearchQuery: (q: string) => setFilters((f) => ({ ...f, search: q })),
    sortBy: filters.sortBy,
    setSortBy: (s: string) => setFilters((f) => ({ ...f, sortBy: s })),
    refresh: () => {
      productsQuery.refetch();
      categoriesQuery.refetch();
    },
  };
}

interface FiltersState {
  category: string;
  occasion: string;
  color: string;
  search: string;
  sortBy: string;
}

import { useState } from 'react';
