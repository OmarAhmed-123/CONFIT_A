import { useState, useCallback, useEffect } from 'react';
import { brandService, adminService } from '../services/apiServices';
import { BrandProfile, BrandAnalyticsDashboard, Product, SponsoredPlacement, AdminPlatformAnalytics } from '../models';
import { useUIStore } from '../stores/uiStore';
import { request } from '../services/apiClient';

export interface CatalogImportJob {
  job_id: number;
  file_name?: string;
  status: string;
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  created_at?: string;
  completed_at?: string;
  errors?: any[];
}

export function useBrandViewModel() {
  const [profile, setProfile] = useState<BrandProfile | null>(null);
  const [analytics, setAnalytics] = useState<BrandAnalyticsDashboard | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [placements, setPlacements] = useState<SponsoredPlacement[]>([]);
  const [adminAnalytics, setAdminAnalytics] = useState<AdminPlatformAnalytics | null>(null);
  const [importJobs, setImportJobs] = useState<CatalogImportJob[]>([]);
  const [conversionPerSku, setConversionPerSku] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const { showToast } = useUIStore();

  const fetchBrandData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [prof, an, prods, plc, adm, imports] = await Promise.allSettled([
        brandService.getProfile(),
        brandService.getAnalytics(),
        brandService.getProducts(),
        brandService.getPlacements(),
        adminService.getPlatformAnalytics(),
        request<CatalogImportJob[]>('/partner/catalog/imports').catch(() => []),
      ]);

      if (prof.status === 'fulfilled') setProfile(prof.value as BrandProfile);
      if (an.status === 'fulfilled') setAnalytics(an.value as BrandAnalyticsDashboard);
      if (prods.status === 'fulfilled') setProducts(prods.value as Product[]);
      if (plc.status === 'fulfilled') setPlacements(plc.value as SponsoredPlacement[]);
      if (adm.status === 'fulfilled') setAdminAnalytics(adm.value as AdminPlatformAnalytics);
      if (imports.status === 'fulfilled') setImportJobs(imports.value as CatalogImportJob[]);

      // Fetch per-SKU conversion
      try {
        const conv = await request<any>('/partner/analytics/conversion');
        if (conv.per_sku) setConversionPerSku(conv.per_sku);
      } catch {}

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

  const uploadCatalogCSV = useCallback(async (file: File) => {
    setIsUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const result = await request<any>('/partner/catalog/upload/csv', {
        method: 'POST',
        body: form,
      });
      showToast(`Import ${result.status}: ${result.accepted_rows} accepted, ${result.rejected_rows} rejected`, result.status === 'completed' ? 'success' : 'info');
      fetchBrandData();
      return result;
    } catch (err: any) {
      showToast('CSV upload failed: ' + err.message, 'error');
      throw err;
    } finally {
      setIsUploading(false);
    }
  }, [fetchBrandData, showToast]);

  const getImportJobStatus = useCallback(async (jobId: number) => {
    try {
      const job = await request<CatalogImportJob>(`/partner/catalog/imports/${jobId}`);
      return job;
    } catch (err: any) {
      showToast('Failed to fetch import job: ' + err.message, 'error');
      return null;
    }
  }, [showToast]);

  useEffect(() => {
    fetchBrandData();
  }, [fetchBrandData]);

  return {
    profile,
    analytics,
    products,
    placements,
    adminAnalytics,
    importJobs,
    conversionPerSku,
    isLoading,
    isUploading,
    refresh: fetchBrandData,
    updateSKUInventory,
    createSponsoredSlot,
    uploadCatalogCSV,
    getImportJobStatus,
  };
}
