import { useState, useCallback, useEffect } from 'react';
import { catalogService } from '../services/apiServices';
import { Product, Category } from '../models';

export function useCatalogViewModel() {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedOccasion, setSelectedOccasion] = useState<string>('');
  const [selectedColor, setSelectedColor] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('recommended');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCatalog = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [prods, cats] = await Promise.all([
        catalogService.getProducts({
          category: selectedCategory || undefined,
          occasion: selectedOccasion || undefined,
          color: selectedColor || undefined,
          search: searchQuery || undefined,
          sort_by: sortBy,
        }),
        catalogService.getCategories(),
      ]);
      setProducts(prods);
      setCategories(cats);
      setIsLoading(false);
    } catch (err: any) {
      setError(err.message || 'Failed to load catalog');
      setIsLoading(false);
    }
  }, [selectedCategory, selectedOccasion, selectedColor, searchQuery, sortBy]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  return {
    products,
    categories,
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
    isLoading,
    error,
    refresh: fetchCatalog,
  };
}
