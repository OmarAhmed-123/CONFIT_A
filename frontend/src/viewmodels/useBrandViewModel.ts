import { useState, useCallback, useEffect, useRef } from 'react';
import { msg, detail } from '../i18n/messages';
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

export function useBrandViewModel(scope: 'brand' | 'admin' = 'brand') {
  const generation = useRef(0);
  const [productAfter, setProductAfter] = useState(0);
  const [profile, setProfile] = useState<BrandProfile | null>(null);
  const [analytics, setAnalytics] = useState<BrandAnalyticsDashboard | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [placements, setPlacements] = useState<SponsoredPlacement[]>([]);
  const [adminAnalytics, setAdminAnalytics] = useState<AdminPlatformAnalytics | null>(null);
  const [importJobs, setImportJobs] = useState<CatalogImportJob[]>([]);
  const [conversionPerSku, setConversionPerSku] = useState<any[]>([]);
  // Honest error propagation (B2B silent-fallback fix): a FAILED fetch must
  // never masquerade as an empty dataset or an eternal spinner. Views render
  // an explicit error + retry for these instead of "no data" copy.
  const [fetchErrors, setFetchErrors] = useState<Record<string, string>>({});
  const [loadFailed, setLoadFailed] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);

  const { showToast } = useUIStore();

  const fetchBrandData = useCallback(async () => {
    setIsLoading(true);
    try {
      const current = ++generation.current;
      const results = await Promise.allSettled(scope === 'admin' ? [adminService.getPlatformAnalytics()] : [
        brandService.getProfile(), brandService.getAnalytics(), brandService.getProducts(productAfter),
        brandService.getPlacements(), request<CatalogImportJob[]>('/partner/catalog/imports'),
        request<any>('/partner/analytics/conversion'),
      ]);
      if (current !== generation.current) return;
      const keys = scope === 'admin' ? ['adminAnalytics'] : ['profile', 'analytics', 'products', 'placements', 'imports', 'conversion'];
      if (scope === 'admin') {
        setAdminAnalytics(results[0].status === 'fulfilled' ? results[0].value as AdminPlatformAnalytics : null);
      } else {
        const [prof, an, prods, plc, imports, conv] = results;
        setProfile(prof.status === 'fulfilled' ? prof.value as BrandProfile : null);
        setAnalytics(an.status === 'fulfilled' ? an.value as BrandAnalyticsDashboard : null);
        setProducts(prods.status === 'fulfilled' ? prods.value as Product[] : []);
        setPlacements(plc.status === 'fulfilled' ? plc.value as SponsoredPlacement[] : []);
        setImportJobs(imports.status === 'fulfilled' ? imports.value as CatalogImportJob[] : []);
        setConversionPerSku(conv.status === 'fulfilled' ? (conv.value?.per_sku ?? []) : []);
      }

      // Record every real failure distinctly (each section is separately
      // owned — a 500 on one must not be shown to the operator as
      // "nothing to import"/"no conversions"/an eternal loading spinner).
      const errors: Record<string, string> = {};
      results.forEach((r, i) => {
        if (r.status === 'rejected') {
          errors[keys[i]] = (r.reason as any)?.message || `Failed to load ${keys[i]}.`;
        }
      });
      setFetchErrors(errors);
      // The dashboard/analyst/admin/placements views block on their payload:
      // if EVERY request failed there is no data to block on — surface a
      // terminal error state instead of an infinite spinner.
      setLoadFailed(Object.keys(errors).length === keys.length);

      if (Object.keys(errors).length === keys.length) {
        showToast(msg('toast.b2b_all_failed'), 'error');
      }
      setIsLoading(false);
    } catch (err: any) {
      setLoadFailed(true);
      setIsLoading(false);
      showToast(msg('toast.b2b_load_failed', { reason: detail(err) }), 'error');
    }
  }, [showToast, scope, productAfter]);

  const updateSKUInventory = useCallback(async (skuId: number, stock: number, priceOverride?: number) => {
    try {
      await brandService.updateSKU(skuId, stock, priceOverride);
      showToast(msg('toast.stock_saved'), 'success');
      await fetchBrandData();
      return true;
    } catch (err: any) {
      showToast(msg('toast.update_failed', { reason: detail(err) }), 'error');
      return false;
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
      showToast(msg('toast.placement_saved'), 'success');
      await fetchBrandData();
      return true;
    } catch (err: any) {
      showToast(msg('toast.placement_create_failed', { reason: detail(err) }), 'error');
      return false;
    }
  }, [fetchBrandData, showToast]);

  const uploadCatalogCSV = useCallback(async (file: File) => {
    setIsUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const job = await request<any>('/partner/catalog/jobs/csv', {
        method: 'POST',
        headers: {'Idempotency-Key': crypto.randomUUID()},
        body: form,
      });
      await request(`/partner/catalog/jobs/${job.job_id}/run`, {method:'POST'});
      const result = await request<CatalogImportJob>(`/partner/catalog/imports/${job.job_id}`);
      showToast(
        msg('toast.import_result', {
          status: result.status,
          accepted: result.accepted_rows,
          rejected: result.rejected_rows,
        }),
        result.status === 'completed' ? 'success' : 'info',
      );
      fetchBrandData();
      return result;
    } catch (err: any) {
      showToast(msg('toast.csv_upload_failed', { reason: detail(err) }), 'error');
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
      showToast(msg('toast.import_job_failed', { reason: detail(err) }), 'error');
      return null;
    }
  }, [showToast]);

  useEffect(() => {
    fetchBrandData();
    return () => { generation.current += 1; };
  }, [fetchBrandData]);

  return {
    profile,
    productAfter, setProductAfter,
    analytics,
    products,
    placements,
    adminAnalytics,
    importJobs,
    conversionPerSku,
    fetchErrors,
    loadFailed,
    isLoading,
    isUploading,
    refresh: fetchBrandData,
    updateSKUInventory,
    createSponsoredSlot,
    uploadCatalogCSV,
    getImportJobStatus,
  };
}
