import { useState, useCallback, useEffect } from 'react';
import { brandService, adminService } from '../services/apiServices';
import { BrandProfile, BrandAnalyticsDashboard, Product, SponsoredPlacement, AdminPlatformAnalytics } from '../models';
import { useUIStore } from '../stores/uiStore';

export function useBrandViewModel() {
  const [profile, setProfile] = useState<BrandProfile | null>(null);
  const [analytics, setAnalytics] = useState<BrandAnalyticsDashboard | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [placements, setPlacements] = useState<SponsoredPlacement[]>([]);
  const [adminAnalytics, setAdminAnalytics] = useState<AdminPlatformAnalytics | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const { showToast } = useUIStore();

  const fetchBrandData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [prof, an, prods, plc, adm] = await Promise.allSettled([
        brandService.getProfile(),
        brandService.getAnalytics(),
        brandService.getProducts(),
        brandService.getPlacements(),
        adminService.getPlatformAnalytics(),
      ]);

      if (prof.status === 'fulfilled') setProfile(prof.value);
      if (an.status === 'fulfilled') setAnalytics(an.value);
      if (prods.status === 'fulfilled') setProducts(prods.value);
      if (plc.status === 'fulfilled') setPlacements(plc.value);
      if (adm.status === 'fulfilled') setAdminAnalytics(adm.value);

      setIsLoading(false);
    } catch (err: any) {
      setIsLoading(false);
      showToast('Error loading B2B data: ' + err.message, 'error');
    }
  }, [showToast]);

  const updateSKUInventory = useCallback(async (skuId: number, stock: number, priceOverride?: number) => {
    try {
      await brandService.updateSKU(skuId, stock, priceOverride);
      showToast('SKU stock successfully synced across warehouse and BOPIS!', 'success');
      fetchBrandData();
    } catch (err: any) {
      showToast('Update failed: ' + err.message, 'error');
    }
  }, [fetchBrandData, showToast]);

  const createSponsoredSlot = useCallback(async (data: { productId: number; bidAmount: number; dailyBudget: number; placementType?: string }) => {
    try {
      await brandService.createPlacement({
        product_id: data.productId,
        bid_amount_per_click: data.bidAmount,
        daily_budget: data.dailyBudget,
        placement_type: data.placementType || 'stylist_featured',
      });
      showToast('Sponsored placement active! Now bidding for Stylist & Trending hero slots.', 'success');
      fetchBrandData();
    } catch (err: any) {
      showToast('Placement creation failed: ' + err.message, 'error');
    }
  }, [fetchBrandData, showToast]);

  useEffect(() => {
    fetchBrandData();
  }, [fetchBrandData]);

  return {
    profile,
    analytics,
    products,
    placements,
    adminAnalytics,
    isLoading,
    refresh: fetchBrandData,
    updateSKUInventory,
    createSponsoredSlot,
  };
}
