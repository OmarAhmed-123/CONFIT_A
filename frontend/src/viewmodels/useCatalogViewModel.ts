import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { catalogService } from '../services/apiServices';
import { queryKeys } from '../lib/queryClient';
import { Product, Category } from '../models';

/**
 * C22 FIX: React Query implementation
 * - Server state managed by React Query with proper caching
 * - No manual useEffect for data fetching
 * - Query keys prevent duplicate requests and enable caching
 * - StaleTime prevents refetch loops
 */
export function useCatalogViewModel() {
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedOccasion, setSelectedOccasion] = useState<string>('');
  const [selectedColor, setSelectedColor] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('recommended');

  const filters = {
    category: selectedCategory || undefined,
    occasion: selectedOccasion || undefined,
    color: selectedColor || undefined,
    search: searchQuery || undefined,
    sort_by: sortBy,
  };

  const productsQuery = useQuery({
    queryKey: queryKeys.catalog.products(filters),
    queryFn: () => catalogService.getProducts(filters),
    staleTime: 1000 * 60 * 5, // 5 min
    gcTime: 1000 * 60 * 30,
    placeholderData: (prev) => prev, // Keep previous data while fetching
  });

  const categoriesQuery = useQuery({
    queryKey: queryKeys.catalog.categories(),
    queryFn: () => catalogService.getCategories(),
    staleTime: 1000 * 60 * 10, // 10 min - categories rarely change
    gcTime: 1000 * 60 * 60,
  });

  return {
    products: productsQuery.data || [],
    categories: categoriesQuery.data || [],
    selectedCategory,
    setSelectedCategory,
    selectedOccasion,
    setSelectedOccasion,
    selectedColor,
    setSelectedColor,
    searchQuery,
    setSearchQuery,
    sortBy,
    setSortBy,
    isLoading: productsQuery.isLoading || categoriesQuery.isLoading,
    isFetching: productsQuery.isFetching,
    error: productsQuery.error ? (productsQuery.error as any).message : categoriesQuery.error ? (categoriesQuery.error as any).message : null,
    refresh: () => {
      productsQuery.refetch();
      categoriesQuery.refetch();
    },
  };
}
