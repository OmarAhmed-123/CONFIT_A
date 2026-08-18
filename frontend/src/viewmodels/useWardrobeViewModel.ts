import { useState, useCallback, useEffect } from 'react';
import { wardrobeService } from '../services/apiServices';
import { WardrobeItem, GapAnalysisItem } from '../models';
import { useUIStore } from '../stores/uiStore';

export function useWardrobeViewModel() {
  const [items, setItems] = useState<WardrobeItem[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>('All');
  const [isLoading, setIsLoading] = useState(false);
  const [gapAnalyses, setGapAnalyses] = useState<GapAnalysisItem[]>([]);
  const [isGapLoading, setIsGapLoading] = useState(false);
  const [isAutoTagging, setIsAutoTagging] = useState(false);
  const [autoTagResult, setAutoTagResult] = useState<any>(null);

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

  const autoTagUpload = useCallback(async (imageUrl: string) => {
    setIsAutoTagging(true);
    try {
      const res = await wardrobeService.autoTagImage(imageUrl);
      setAutoTagResult(res);
      setIsAutoTagging(false);
      showToast('AI auto-tagged garment attributes!', 'success');
    } catch (err: any) {
      setIsAutoTagging(false);
      showToast('Auto-tagging failed: ' + err.message, 'error');
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
  };
}
