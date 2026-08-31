import { useState, useCallback, useEffect } from 'react';
import { wardrobeService, WardrobeUploadResponse, WardrobeFirstOutfit, AutoTagResponse } from '../services/apiServices';
import { WardrobeItem, GapAnalysisItem } from '../models';
import { useUIStore } from '../stores/uiStore';

export function useWardrobeViewModel() {
  const [items, setItems] = useState<WardrobeItem[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>('All');
  const [isLoading, setIsLoading] = useState(false);
  const [gapAnalyses, setGapAnalyses] = useState<GapAnalysisItem[]>([]);
  const [isGapLoading, setIsGapLoading] = useState(false);
  const [isAutoTagging, setIsAutoTagging] = useState(false);
  const [autoTagResult, setAutoTagResult] = useState<AutoTagResponse | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadReport, setUploadReport] = useState<WardrobeUploadResponse | null>(null);
  const [outfitSuggestion, setOutfitSuggestion] = useState<WardrobeFirstOutfit | null>(null);
  const [isOutfitLoading, setIsOutfitLoading] = useState(false);
  const [retryingItemId, setRetryingItemId] = useState<number | null>(null);

  const { showToast } = useUIStore();

  const fetchWardrobe = useCallback(async (cat?: string) => {
    setIsLoading(true);
    try {
      const data = await wardrobeService.getItems(cat || activeCategory);
      setItems(data);
      setIsLoading(false);
    } catch (err: any) {
      setIsLoading(false);
      showToast('Error loading wardrobe: ' + err.message, 'error');
    }
  }, [activeCategory, showToast]);

  const fetchGaps = useCallback(async () => {
    setIsGapLoading(true);
    try {
      const data = await wardrobeService.getGapAnalysis();
      setGapAnalyses(data);
      setIsGapLoading(false);
    } catch (err: any) {
      setIsGapLoading(false);
    }
  }, []);

  const fetchOutfitSuggestion = useCallback(async (occasion: string = 'Smart Casual') => {
    setIsOutfitLoading(true);
    try {
      const data = await wardrobeService.getOutfitSuggestions(occasion);
      setOutfitSuggestion(data);
    } catch (err: any) {
      showToast('Wardrobe-first styling failed: ' + err.message, 'error');
    } finally {
      setIsOutfitLoading(false);
    }
  }, [showToast]);

  const autoTagUpload = useCallback(async (imageUrl: string) => {
    setIsAutoTagging(true);
    try {
      const res = await wardrobeService.autoTagImage(imageUrl);
      setAutoTagResult(res);
      setIsAutoTagging(false);
      if (res.analysis_available) {
        showToast('AI auto-tagged garment attributes!', 'success');
      } else {
        showToast(res.detail || 'AI tagging unavailable — fill the fields manually.', 'info');
      }
      return res;
    } catch (err: any) {
      setIsAutoTagging(false);
      showToast('Auto-tagging failed: ' + err.message, 'error');
      return null;
    }
  }, [showToast]);

  const addNewItem = useCallback(async (itemData: Partial<WardrobeItem>) => {
    try {
      const created = await wardrobeService.addItem(itemData);
      setItems((prev) => [created, ...prev]);
      showToast('Piece added to your smart wardrobe!', 'success');
    } catch (err: any) {
      showToast('Failed to add item: ' + err.message, 'error');
    }
  }, [showToast]);

  /**
   * Real image upload: file -> /wardrobe/upload (single) or /upload/bulk.
   * Per-file results come back in the report so the UI can show exactly
   * which items failed and offer retry — one bad file never rolls back the
   * rest (BRD §13).
   */
  const uploadFiles = useCallback(async (files: File[]) => {
    if (!files.length) return null;
    setIsUploading(true);
    setUploadReport(null);
    try {
      const report = files.length === 1
        ? await wardrobeService.uploadImage(files[0])
        : await wardrobeService.uploadBulk(files);
      setUploadReport(report);

      const created = report.results
        .filter((r) => r.item)
        .map((r) => r.item as WardrobeItem);
      if (created.length) {
        setItems((prev) => [...created.reverse(), ...prev]);
      }

      const { succeeded, failed, duplicates_skipped } = report.summary;
      if (failed === 0 && duplicates_skipped === 0) {
        showToast(`${succeeded} piece(s) uploaded — AI analysis ${report.results.some((r) => r.item?.processing_status === 'ready') ? 'complete' : 'started'}.`, 'success');
      } else if (succeeded > 0) {
        showToast(`${succeeded} uploaded, ${failed} failed, ${duplicates_skipped} duplicate(s) skipped.`, 'info');
      } else {
        showToast('Upload failed — see details below.', 'error');
      }
      return report;
    } catch (err: any) {
      showToast('Upload failed: ' + err.message, 'error');
      return null;
    } finally {
      setIsUploading(false);
    }
  }, [showToast]);

  const retryAnalysis = useCallback(async (itemId: number) => {
    setRetryingItemId(itemId);
    try {
      const updated = await wardrobeService.analyzeItem(itemId);
      setItems((prev) => prev.map((i) => (i.id === itemId ? updated : i)));
      if (updated.processing_status === 'ready') {
        showToast('AI analysis complete!', 'success');
      } else {
        showToast(updated.processing_error || 'Analysis still unavailable.', 'info');
      }
    } catch (err: any) {
      showToast('Retry failed: ' + err.message, 'error');
    } finally {
      setRetryingItemId(null);
    }
  }, [showToast]);

  const updateItem = useCallback(async (itemId: number, data: Partial<WardrobeItem>) => {
    try {
      const updated = await wardrobeService.updateItem(itemId, data);
      setItems((prev) => prev.map((i) => (i.id === itemId ? updated : i)));
    } catch (err: any) {
      showToast('Update failed: ' + err.message, 'error');
    }
  }, [showToast]);

  const toggleFavorite = useCallback(async (item: WardrobeItem) => {
    await updateItem(item.id, {
      is_favorite: !item.is_favorite,
      wear_frequency: !item.is_favorite ? 'favorite' : 'regular',
    });
  }, [updateItem]);

  const setWearFrequency = useCallback(async (item: WardrobeItem, frequency: string) => {
    await updateItem(item.id, {
      wear_frequency: frequency,
      is_favorite: frequency === 'favorite' ? true : item.is_favorite,
    });
  }, [updateItem]);

  const deleteItem = useCallback(async (itemId: number) => {
    try {
      await wardrobeService.deleteItem(itemId);
      setItems((prev) => prev.filter((i) => i.id !== itemId));
      showToast('Item removed from wardrobe', 'info');
    } catch (err: any) {
      showToast('Failed to delete item: ' + err.message, 'error');
    }
  }, [showToast]);

  useEffect(() => {
    fetchWardrobe(activeCategory);
  }, [activeCategory, fetchWardrobe]);

  return {
    items,
    activeCategory,
    setActiveCategory,
    isLoading,
    fetchWardrobe,
    gapAnalyses,
    isGapLoading,
    fetchGaps,
    isAutoTagging,
    autoTagResult,
    autoTagUpload,
    addNewItem,
    deleteItem,
    uploadFiles,
    isUploading,
    uploadReport,
    retryAnalysis,
    retryingItemId,
    toggleFavorite,
    setWearFrequency,
    outfitSuggestion,
    isOutfitLoading,
    fetchOutfitSuggestion,
  };
}
