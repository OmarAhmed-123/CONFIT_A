import { msg, detail } from '../i18n/messages';
import { localizeApiError } from '../i18n/apiErrors';
import i18n from '../i18n/i18n';
import { useState, useCallback, useEffect } from 'react';
import { wardrobeService, moodBoardService, WardrobeUploadResponse, WardrobeFirstOutfit, AutoTagResponse, MoodBoard } from '../services/apiServices';
import { WardrobeItem, GapAnalysisItem } from '../models';
import { useUIStore } from '../stores/uiStore';

export function useWardrobeViewModel() {
  const [items, setItems] = useState<WardrobeItem[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>('All');
  const [isLoading, setIsLoading] = useState(false);
  // Honest states (BRD G-UX): loading / empty / error are distinct. A failed
  // fetch must never masquerade as an empty wardrobe.
  const [isClosetError, setClosetError] = useState<string | null>(null);
  const [gapAnalyses, setGapAnalyses] = useState<GapAnalysisItem[]>([]);
  const [isGapLoading, setIsGapLoading] = useState(false);
  const [isGapError, setGapError] = useState<string | null>(null);
  const [hasLoadedGaps, setHasLoadedGaps] = useState(false);
  // Mood Boards (G4 surface over the G1 backend)
  const [moodBoards, setMoodBoards] = useState<MoodBoard[]>([]);
  const [isBoardsLoading, setIsBoardsLoading] = useState(false);
  const [isBoardsError, setBoardsError] = useState<string | null>(null);
  const [hasLoadedBoards, setHasLoadedBoards] = useState(false);
  const [isAutoTagging, setIsAutoTagging] = useState(false);
  const [autoTagResult, setAutoTagResult] = useState<AutoTagResponse | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadReport, setUploadReport] = useState<WardrobeUploadResponse | null>(null);
  const [outfitSuggestion, setOutfitSuggestion] = useState<WardrobeFirstOutfit | null>(null);
  const [isOutfitLoading, setIsOutfitLoading] = useState(false);
  const [retryingItemId, setRetryingItemId] = useState<number | null>(null);

  const { showToast } = useUIStore();

  /**
   * The message a shopper reads when a load fails.
   *
   * REGRESSION FIXED 2026-09-23: these three states stored `detail(err)` — the
   * server's message verbatim — and the view rendered it directly. Measured in a
   * real browser in Arabic: the wardrobe showed "Sign in to access your personal
   * style profile and account features." in English, i.e. backend English
   * diagnostics shown to an Arabic-first shopper. This is the same defect class
   * already fixed on the checkout money path; the helper existed, this surface
   * had not been converted. Known error codes now resolve to localized text,
   * and only genuinely unknown codes fall back to the server's wording.
   */
  const errorText = useCallback(
    (err: unknown) => localizeApiError(err, i18n.t.bind(i18n)),
    [],
  );

  const fetchWardrobe = useCallback(async (cat?: string) => {
    setIsLoading(true);
    setClosetError(null);
    try {
      const data = await wardrobeService.getItems(cat || activeCategory);
      setItems(data);
      setIsLoading(false);
    } catch (err: any) {
      setIsLoading(false);
      setClosetError(errorText(err));
      showToast(msg('toast.wardrobe_load_failed', { reason: detail(err) }), 'error');
    }
  }, [activeCategory, showToast]);

  const fetchGaps = useCallback(async () => {
    setIsGapLoading(true);
    setGapError(null);
    try {
      const data = await wardrobeService.getGapAnalysis();
      setGapAnalyses(data);
      setHasLoadedGaps(true);
      setIsGapLoading(false);
    } catch (err: any) {
      setIsGapLoading(false);
      setGapError(errorText(err));
      showToast(msg('toast.gap_analysis_failed', { reason: detail(err) }), 'error');
    }
  }, [showToast]);

  // ─────────────────────────── Mood Boards ───────────────────────────
  const fetchMoodBoards = useCallback(async () => {
    setIsBoardsLoading(true);
    setBoardsError(null);
    try {
      const data = await moodBoardService.list();
      setMoodBoards(data);
      setHasLoadedBoards(true);
      setIsBoardsLoading(false);
    } catch (err: any) {
      setIsBoardsLoading(false);
      setBoardsError(errorText(err));
      showToast(msg('toast.boards_load_failed', { reason: detail(err) }), 'error');
    }
  }, [showToast]);

  const createMoodBoard = useCallback(async (title: string, description?: string) => {
    try {
      const created = await moodBoardService.create(title, description);
      setMoodBoards((prev) => [...prev, created]);
      showToast(msg('toast.board_created'), 'success');
      return created;
    } catch (err: any) {
      showToast(msg('toast.board_create_failed', { reason: detail(err) }), 'error');
      return null;
    }
  }, [showToast]);

  const renameMoodBoard = useCallback(async (boardId: number, title: string) => {
    try {
      const updated = await moodBoardService.update(boardId, { title });
      setMoodBoards((prev) => prev.map((b) => (b.id === boardId ? updated : b)));
    } catch (err: any) {
      showToast(msg('toast.board_rename_failed', { reason: detail(err) }), 'error');
    }
  }, [showToast]);

  const deleteMoodBoard = useCallback(async (boardId: number) => {
    try {
      await moodBoardService.remove(boardId);
      setMoodBoards((prev) => prev.filter((b) => b.id !== boardId));
      showToast(msg('toast.board_deleted'), 'info');
    } catch (err: any) {
      showToast(msg('toast.board_delete_failed', { reason: detail(err) }), 'error');
    }
  }, [showToast]);

  const addMoodBoardTile = useCallback(async (boardId: number, kind: 'url' | 'product' | 'upload', payload: Record<string, any>) => {
    try {
      const updated = await moodBoardService.addItem(boardId, kind, payload);
      setMoodBoards((prev) => prev.map((b) => (b.id === boardId ? updated : b)));
      return updated;
    } catch (err: any) {
      showToast(msg('toast.board_tile_add_failed', { reason: detail(err) }), 'error');
      return null;
    }
  }, [showToast]);

  const removeMoodBoardTile = useCallback(async (boardId: number, itemId: number) => {
    try {
      const updated = await moodBoardService.removeItem(boardId, itemId);
      setMoodBoards((prev) => prev.map((b) => (b.id === boardId ? updated : b)));
    } catch (err: any) {
      showToast(msg('toast.board_tile_remove_failed', { reason: detail(err) }), 'error');
    }
  }, [showToast]);

  /** Real upload -> store -> attach. The stored reference carries a
   * short-lived presigned GET (private bucket) — valid for the tile's
   * current render; re-prefetched boards get fresh signatures. */
  const uploadMoodBoardTile = useCallback(async (boardId: number, file: File) => {
    try {
      const stored = await moodBoardService.upload(boardId, file);
      const updated = await moodBoardService.addItem(boardId, 'upload', {
        upload_id: stored.upload_id,
        url: stored.url,
      });
      if (updated) {
        setMoodBoards((prev) => prev.map((b) => (b.id === boardId ? updated : b)));
        showToast(msg('toast.board_tile_uploaded'), 'success');
      }
    } catch (err: any) {
      showToast(msg('toast.board_tile_upload_failed', { reason: detail(err) }), 'error');
    }
  }, [showToast]);

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
    isClosetError,
    fetchWardrobe,
    gapAnalyses,
    isGapLoading,
    isGapError,
    hasLoadedGaps,
    fetchGaps,
    moodBoards,
    isBoardsLoading,
    isBoardsError,
    hasLoadedBoards,
    fetchMoodBoards,
    createMoodBoard,
    renameMoodBoard,
    deleteMoodBoard,
    addMoodBoardTile,
    removeMoodBoardTile,
    uploadMoodBoardTile,
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
