import { msg, detail } from '../i18n/messages';
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
      showToast(msg('toast.wardrobe_load_failed', { reason: detail(err) }), 'error');
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
      showToast(msg('toast.wardrobe_styling_failed', { reason: detail(err) }), 'error');
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
        showToast(msg('toast.auto_tagged'), 'success');
      } else {
        showToast(
          // A server-supplied detail is an upstream string we cannot translate;
          // it is carried as an interpolation value so the surrounding sentence
          // still follows the active language.
          typeof res.detail === 'string' && res.detail
            ? msg('toast.auto_tag_unavailable', { reason: detail(res.detail) })
            : msg('toast.auto_tag_unavailable_generic'),
          'info',
        );
      }
      return res;
    } catch (err: any) {
      setIsAutoTagging(false);
      showToast(msg('toast.auto_tag_failed', { reason: detail(err) }), 'error');
      return null;
    }
  }, [showToast]);

  const addNewItem = useCallback(async (itemData: Partial<WardrobeItem>) => {
    try {
      const created = await wardrobeService.addItem(itemData);
      setItems((prev) => [created, ...prev]);
      showToast(msg('toast.added_to_piece'), 'success');
    } catch (err: any) {
      showToast(msg('toast.added_to_piece_failed', { reason: detail(err) }), 'error');
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
        // Two explicit keys rather than interpolating a nested key name: an
        // interpolated key would render as the literal string
        // "toast.wardrobe_upload_state_ready" for the user.
        showToast(
          report.results.some((r) => r.item?.processing_status === 'ready')
            ? msg('toast.wardrobe_upload_complete', { succeeded })
            : msg('toast.wardrobe_upload_pending', { succeeded }),
          'success',
        );
      } else if (succeeded > 0) {
        showToast(
          msg('toast.wardrobe_upload_mixed', {
            succeeded,
            failed,
            duplicates: duplicates_skipped,
          }),
          'info',
        );
      } else {
        showToast(msg('toast.wardrobe_upload_all_failed'), 'error');
      }
      return report;
    } catch (err: any) {
      showToast(msg('toast.wardrobe_upload_failed', { reason: detail(err) }), 'error');
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
        showToast(msg('toast.wardrobe_analysis_complete'), 'success');
      } else {
        showToast(
          typeof updated.processing_error === 'string' && updated.processing_error
            ? msg('toast.analysis_unavailable_reason', { reason: detail(updated.processing_error) })
            : msg('toast.analysis_unavailable'),
          'info',
        );
      }
    } catch (err: any) {
      showToast(msg('toast.retry_failed', { reason: detail(err) }), 'error');
    } finally {
      setRetryingItemId(null);
    }
  }, [showToast]);

  const updateItem = useCallback(async (itemId: number, data: Partial<WardrobeItem>) => {
    try {
      const updated = await wardrobeService.updateItem(itemId, data);
      setItems((prev) => prev.map((i) => (i.id === itemId ? updated : i)));
    } catch (err: any) {
      showToast(msg('toast.update_failed', { reason: detail(err) }), 'error');
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
      showToast(msg('toast.item_removed'), 'info');
    } catch (err: any) {
      showToast(msg('toast.item_delete_failed', { reason: detail(err) }), 'error');
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
