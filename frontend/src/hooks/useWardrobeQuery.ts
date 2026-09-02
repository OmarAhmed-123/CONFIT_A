import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { wardrobeService } from '../services/apiServices';
import { queryKeys } from '../lib/queryClient';
import { useAuthStore } from '../stores/authStore';
import { WardrobeItem } from '../models';

/**
 * C22 FIX: React Query implementation for wardrobe
 * - User-isolated query keys (includes userId)
 * - Proper cache invalidation on mutations
 * - Optimistic updates with rollback
 * - No cross-user leakage
 */

export function useWardrobeItems(category: string = 'All') {
  const user = useAuthStore((s) => s.user);
  const userId = user?.id;

  return useQuery({
    queryKey: queryKeys.wardrobe.items(userId, category),
    queryFn: () => wardrobeService.getItems(category),
    enabled: !!userId, // Only fetch if authenticated
    staleTime: 1000 * 60 * 3, // 3 min
    gcTime: 1000 * 60 * 15,
  });
}

export function useWardrobeGaps() {
  const user = useAuthStore((s) => s.user);
  const userId = user?.id;

  return useQuery({
    queryKey: queryKeys.wardrobe.gaps(userId),
    queryFn: () => wardrobeService.getGapAnalysis(),
    enabled: !!userId,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 15,
  });
}

export function useWardrobeOutfitSuggestion(occasion: string = 'Smart Casual') {
  const user = useAuthStore((s) => s.user);
  const userId = user?.id;

  return useQuery({
    queryKey: queryKeys.wardrobe.outfitSuggestions(userId, occasion),
    queryFn: () => wardrobeService.getOutfitSuggestions(occasion),
    enabled: !!userId && !!occasion,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 15,
  });
}

export function useUploadWardrobe() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const userId = user?.id;

  return useMutation({
    mutationFn: (files: File[]) => {
      return files.length === 1
        ? wardrobeService.uploadImage(files[0])
        : wardrobeService.uploadBulk(files);
    },
    onSuccess: (data) => {
      // Invalidate wardrobe items to refetch with new items
      queryClient.invalidateQueries({ queryKey: queryKeys.wardrobe.all(userId) });
      // Also invalidate gaps and outfit suggestions
      queryClient.invalidateQueries({ queryKey: queryKeys.wardrobe.gaps(userId) });
    },
    // No retry for mutations - prevents duplicate uploads
    retry: false,
  });
}

export function useDeleteWardrobeItem() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const userId = user?.id;

  return useMutation({
    mutationFn: (itemId: number) => wardrobeService.deleteItem(itemId),
    // Optimistic update with rollback
    onMutate: async (itemId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.wardrobe.all(userId) });

      // Snapshot previous value
      const previousItems = queryClient.getQueryData(queryKeys.wardrobe.items(userId, 'All'));

      // Optimistically remove item
      queryClient.setQueriesData(
        { queryKey: queryKeys.wardrobe.all(userId) },
        (old: any) => {
          if (!old) return old;
          if (Array.isArray(old)) {
            return old.filter((item: WardrobeItem) => item.id !== itemId);
          }
          return old;
        }
      );

      return { previousItems };
    },
    onError: (err, itemId, context) => {
      // Rollback on error
      if (context?.previousItems) {
        queryClient.setQueryData(queryKeys.wardrobe.items(userId, 'All'), context.previousItems);
      }
    },
    onSettled: () => {
      // Always refetch after error or success to ensure authoritative state
      queryClient.invalidateQueries({ queryKey: queryKeys.wardrobe.all(userId) });
    },
    retry: false,
  });
}

export function useUpdateWardrobeItem() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const userId = user?.id;

  return useMutation({
    mutationFn: ({ itemId, data }: { itemId: number; data: Partial<WardrobeItem> }) =>
      wardrobeService.updateItem(itemId, data),
    onMutate: async ({ itemId, data }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.wardrobe.all(userId) });
      const previousItems = queryClient.getQueryData(queryKeys.wardrobe.items(userId, 'All'));

      queryClient.setQueriesData(
        { queryKey: queryKeys.wardrobe.all(userId) },
        (old: any) => {
          if (!old || !Array.isArray(old)) return old;
          return old.map((item: WardrobeItem) =>
            item.id === itemId ? { ...item, ...data } : item
          );
        }
      );

      return { previousItems };
    },
    onError: (err, variables, context) => {
      if (context?.previousItems) {
        queryClient.setQueryData(queryKeys.wardrobe.items(userId, 'All'), context.previousItems);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.wardrobe.all(userId) });
    },
    retry: false,
  });
}

export function useAnalyzeWardrobeItem() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const userId = user?.id;

  return useMutation({
    mutationFn: (itemId: number) => wardrobeService.analyzeItem(itemId),
    onSuccess: (updatedItem) => {
      // Update the specific item in cache
      queryClient.setQueriesData(
        { queryKey: queryKeys.wardrobe.all(userId) },
        (old: any) => {
          if (!old || !Array.isArray(old)) return old;
          return old.map((item: WardrobeItem) =>
            item.id === updatedItem.id ? updatedItem : item
          );
        }
      );
    },
    retry: false,
  });
}
