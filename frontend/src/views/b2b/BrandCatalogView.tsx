import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useRef, useState, useMemo } from 'react';
import React from 'react';
import { Upload, Tags, RefreshCw, Search, Filter, CheckCircle2, AlertTriangle, Building2 } from 'lucide-react';
import { UploadIcon } from '../../components/icons/ConfitIcons';
import { useBrandViewModel, CatalogImportJob } from '../../viewmodels/useBrandViewModel';
import { Surface } from '../../components/common/Surface';
import { HonestProductImage } from '../../components/common/HonestProductImage';
import { request } from '../../services/apiClient';
import { CSVProductImportModal } from '../../components/brands/CSVProductImportModal';
import { CatalogImportResult } from '../../models';

/**
 * B03 — Catalog & SKU Management, upgraded with CSV Product Import,
 * Boutique Branch Inventory Management, and Automated Notifications.
 */

const SAMPLE_CSV = [
  'product_name,sku,description,category,price,currency,original_price,color,size,stock_quantity,image_url',
  '"Classic Cotton Shirt",CONFIT-SHIRT-001,"Regular fit crisp cotton shirt",shirts,850.00,EGP,1000.00,White,M,25,https://images.pexels.com/photos/297933/pexels-photo-297933.jpeg',
].join('\n') + '\n';

const TERMINAL = new Set(['completed', 'partially_completed', 'failed']);

type TagPhase =
  | { phase: 'idle' }
  | { phase: 'previewing' }
  | { phase: 'applying' }
  | { phase: 'preview' | 'applied'; data: any }
  | { phase: 'error'; message: string; throttled?: boolean };

export const BrandCatalogView: React.FC = () => {
  const { t } = useTranslation();
  const {
    products, updateSKUInventory, isLoading, importJobs,
    fetchErrors, refresh, getImportJobStatus, uploadCatalogCSV, isUploading,
  } = useBrandViewModel();

  const [editingSkuId, setEditingSkuId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [editStock, setEditStock] = useState<number>(20);
  const [editPrice, setEditPrice] = useState<number | undefined>(undefined);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [lastImportResult, setLastImportResult] = useState<CatalogImportResult | CatalogImportJob | null>(null);
  const [tag, setTag] = useState<Record<number, TagPhase>>({});
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (pollTimer.current) clearTimeout(pollTimer.current); }, []);

  const closeBulkDialog = useCallback(() => { if (!isUploading) setBulkModalOpen(false); }, [isUploading]);

  const downloadSampleCsv = useCallback(() => {
    const blob = new Blob(['\ufeff' + SAMPLE_CSV], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'confit-catalog-template.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, []);

  const handleFileUpload = async (file: File) => {
    setFileError(null);
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setFileError(t('b2b.cat.file_err_type'));
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setFileError(t('b2b.cat.file_err_size'));
      return;
    }
    try {
      const result = await uploadCatalogCSV(file);
      setLastImportResult(result);
      if (result?.job_id != null && !TERMINAL.has(result.status)) {
        followJob(result.job_id, Date.now());
      } else {
        refresh();
      }
    } catch (err) {
      /* the view-model already toasts the failure; nothing to fabricate here */
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) handleFileUpload(e.dataTransfer.files[0]);
  };

  const followJob = useCallback((jobId: number, startedAt: number) => {
    const step = async () => {
      const job = await getImportJobStatus(jobId);
      if (!job) return;
      setLastImportResult(job);
      if (TERMINAL.has(job.status)) {
        refresh();
        return;
      }
      if (Date.now() - startedAt > 90_000) return;
      pollTimer.current = setTimeout(step, 2500);
    };
    pollTimer.current = setTimeout(step, 2500);
  }, [getImportJobStatus, refresh]);

  const handleSaveSku = async (skuId: number) => {
    if (saving) return;
    setSaving(true);
    try {
      if (await updateSKUInventory(skuId, editStock, editPrice)) setEditingSkuId(null);
    } finally { setSaving(false); }
  };

  const handleImportComplete = (result: CatalogImportResult) => {
    setLastImportResult(result);
    refresh();
  };

  const runTag = async (productId: number, dry: boolean) => {
    setTag((prev) => ({ ...prev, [productId]: { phase: dry ? 'previewing' : 'applying' } }));
    try {
      const data = await request<any>(`/brand/products/${productId}/auto-tag?dry_run=${dry}`, { method: 'POST' });
      setTag((prev) => ({ ...prev, [productId]: { phase: dry ? 'preview' : 'applied', data } }));
      if (!dry) refresh();
    } catch (err: any) {
      setTag((prev) => ({
        ...prev,
        [productId]: {
          phase: 'error',
          throttled: err?.status === 429,
          message: err?.status === 429 ? t('b2b.cat.tag_throttled') : t('b2b.cat.tag_error', { reason: err?.message || 'failed' }),
        },
      }));
    }
  };

  const categories = useMemo(() => {
    const cats = new Set<string>();
    products.forEach((p) => {
      if (p.category_name) cats.add(p.category_name);
    });
    return Array.from(cats);
  }, [products]);

  const filteredProducts = useMemo(() => {
    return products.filter((p) => {
      const matchesCategory = selectedCategory === 'all' || p.category_name === selectedCategory;
      const q = searchQuery.toLowerCase().trim();
      if (!q) return matchesCategory;
      const matchesTitle = p.title?.toLowerCase().includes(q);
      const matchesSku = p.skus?.some((s) => s.sku_code?.toLowerCase().includes(q));
      return matchesCategory && (matchesTitle || matchesSku);
    });
  }, [products, selectedCategory, searchQuery]);

  const btnPrimary =
    'inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand-charcoal px-5 text-xs font-semibold text-white transition-colors duration-300 ease-luxury hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-coral disabled:opacity-50';
  const btnGhost =
    'inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-brand-lilac/60 bg-brand-lilac/10 px-4 text-xs font-semibold text-brand-charcoal transition-colors duration-300 ease-luxury hover:bg-brand-lilac/20 hover:border-brand-lilac focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-lilac disabled:opacity-50';

  if (isLoading) {
    return (
      <div className="space-y-8 pb-20" role="status" aria-live="polite">
        <span className="sr-only">{t('b2b.cat.loading')}</span>
        <div className="flex items-center justify-between gap-4 border-b border-slate-200 pb-6" aria-hidden="true">
          <div className="space-y-3">
            <div className="skeleton-shimmer h-9 w-72 rounded-xl bg-slate-100" />
            <div className="h-3 w-96 max-w-full animate-pulse rounded bg-slate-200" />
          </div>
          <div className="skeleton-shimmer h-12 w-40 rounded-xl bg-slate-100" />
        </div>
        {[0, 1].map((i) => (
          <div key={i} className="space-y-4 rounded-2xl border border-slate-200 p-6" aria-hidden="true">
            <div className="flex items-center gap-3">
              <div className="skeleton-shimmer h-16 w-14 rounded-xl bg-slate-100" />
              <div className="space-y-2">
                <div className="h-3 w-24 animate-pulse rounded bg-slate-200" />
                <div className="h-4 w-52 animate-pulse rounded bg-slate-200" />
              </div>
            </div>
            <div className="skeleton-shimmer h-24 w-full rounded-xl bg-slate-100" />
          </div>
        ))}
      </div>
    );
  }

  const statusTone = (s: string) =>
    s === 'completed' ? 'bg-emerald-100 text-emerald-800'
    : s === 'partially_completed' ? 'bg-amber-100 text-amber-800'
    : s === 'failed' ? 'bg-rose-100 text-rose-800'
    : 'bg-slate-100 text-slate-700';
  const statusLabel = (s: string) => t(`b2b.cat.status_${s}` as any, { defaultValue: s });

  return (
    <div className="space-y-8 pb-20">
      {/* ------------------------------------------------------ editorial header */}
      <header className="flex flex-col justify-between gap-4 border-b border-slate-200 pb-6 sm:flex-row sm:items-end">
        <div>
          <div className="flex items-center gap-2">
            <span className="h-px w-8 bg-brand-coral" aria-hidden="true" />
            <span className="text-[11px] font-bold uppercase tracking-widest text-brand-charcoal">
              {t('b2b.cat.eyebrow')}
            </span>
          </div>
          <h1 className="mt-2 font-serif text-3xl font-bold text-brand-charcoal">
            {t('b2b.cat.header_title')}
          </h1>
          <p className="mt-1 max-w-xl text-xs leading-relaxed text-slate-600 sm:text-sm">
            {t('b2b.cat.header_hint')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            data-motion="upload"
            type="button"
            onClick={() => { setFileError(null); setBulkModalOpen(true); }}
            className={btnPrimary}
          >
            <UploadIcon size={14} />
            {t('b2b.cat.bulk_cta')}
          </button>
          <button
            data-motion="upload"
            type="button"
            onClick={() => setImportModalOpen(true)}
            className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand-coral px-5 text-xs font-semibold text-white transition-colors duration-300 ease-luxury hover:bg-[#E76A52] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-coral shadow-xs"
          >
            <Upload size={14} aria-hidden="true" />
            {t('b2b.cat.import_products_cta')}
          </button>
        </div>
      </header>

      {/* ------------------------------------------------------ import jobs ledger */}
      {fetchErrors.imports && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-rose-300 bg-rose-50 p-4 text-xs text-rose-800">
          <span>{t('b2b.cat.jobs_err', { reason: fetchErrors.imports })}</span>
          <button data-motion="recovery" type="button" onClick={refresh} className="min-h-12 rounded-xl bg-rose-700 px-4 font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal">
            {t('common.retry')}
          </button>
        </div>
      )}

      {importJobs.length > 0 && (
        <Surface variant="solid" as="section" className="rounded-2xl p-6">
          <h2 className="border-b border-slate-200 pb-3 font-serif text-lg font-bold text-brand-charcoal">
            {t('b2b.cat.jobs_title')}
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-start text-xs">
              <caption className="sr-only">{t('b2b.cat.caption_jobs')}</caption>
              <thead>
                <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-600">
                  <th scope="col" className="py-2 pe-3">{t('b2b.cat.th_job')}</th>
                  <th scope="col" className="py-2 pe-3">{t('b2b.cat.th_file')}</th>
                  <th scope="col" className="py-2 pe-3">{t('b2b.cat.th_status')}</th>
                  <th scope="col" className="py-2 pe-3">{t('b2b.cat.th_total')}</th>
                  <th scope="col" className="py-2 pe-3">{t('b2b.cat.th_accepted')}</th>
                  <th scope="col" className="py-2 pe-3">{t('b2b.cat.th_rejected')}</th>
                  <th scope="col" className="py-2">{t('b2b.cat.th_dup')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {importJobs.slice(0, 5).map((job) => (
                  <tr key={job.job_id}>
                    <td className="py-2.5 pe-3 font-mono">#{job.job_id}</td>
                    <td className="max-w-[150px] truncate py-2.5 pe-3">{job.file_name || t('b2b.cat.job_api')}</td>
                    <td className="py-2.5 pe-3">
                      <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${statusTone(job.status)}`}>
                        {statusLabel(job.status)}
                      </span>
                    </td>
                    <td className="py-2.5 pe-3">{job.total_rows}</td>
                    <td className="py-2.5 pe-3 font-bold text-emerald-700">{job.accepted_rows}</td>
                    <td className="py-2.5 pe-3 text-rose-700">{job.rejected_rows}</td>
                    <td className="py-2.5 text-amber-700">{job.duplicate_rows}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Surface>
      )}

      {/* ------------------------------------------------------ last import result banner */}
      {lastImportResult && (
        <Surface
          variant="solid"
          role="status"
          className={`space-y-3 rounded-2xl border p-6 ${
            lastImportResult.status === 'completed' ? 'border-emerald-300 bg-emerald-50'
            : lastImportResult.status === 'partially_completed' ? 'border-amber-300 bg-amber-50'
            : 'border-rose-300 bg-rose-50'
          }`}
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-brand-charcoal">
              {t('b2b.cat.last_title', { status: statusLabel(lastImportResult.status) })}
            </h3>
            {lastImportResult.notifications_queued != null && lastImportResult.notifications_queued > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-purple-100 px-3 py-1 text-xs font-bold text-purple-800">
                <CheckCircle2 size={13} />
                {lastImportResult.notifications_queued} notifications queued
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
            <div><span className="text-slate-600">{t('b2b.cat.last_total')}</span> <strong>{lastImportResult.total_rows}</strong></div>
            <div><span className="text-slate-600">{t('b2b.cat.last_accepted')}</span> <strong className="text-emerald-700">{lastImportResult.accepted_rows}</strong></div>
            <div><span className="text-slate-600">{t('b2b.cat.last_rejected')}</span> <strong className="text-rose-700">{lastImportResult.rejected_rows}</strong></div>
            <div><span className="text-slate-600">{t('b2b.cat.last_dup')}</span> <strong className="text-amber-700">{lastImportResult.duplicate_rows}</strong></div>
          </div>
          {lastImportResult.errors && lastImportResult.errors.length > 0 && (
            <div className="border-t border-slate-200 pt-3">
              <span className="mb-2 block text-xs font-bold text-slate-700">{t('b2b.cat.errors_title')}</span>
              <div className="max-h-40 space-y-1 overflow-y-auto text-[11px]">
                {lastImportResult.errors.slice(0, 10).map((err: any, idx: number) => (
                  <div key={idx} className="rounded-lg border border-slate-200 bg-white p-2">
                    <span className="font-bold">{t('b2b.cat.err_row', { row: err.row, field: err.field })}</span>{' '}
                    {err.message} {err.value ? `(${err.value})` : ''}
                  </div>
                ))}
              </div>
            </div>
          )}
        </Surface>
      )}

      {/* ------------------------------------------------------ search & filter bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative w-full sm:w-96">
          <Search size={16} className="absolute left-3 top-3.5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('b2b.cat.search_placeholder')}
            className="w-full rounded-xl border border-slate-200 bg-white pl-9 pr-4 py-2.5 text-xs text-brand-charcoal focus:border-brand-charcoal focus:outline-none focus:ring-1 focus:ring-brand-charcoal"
          />
        </div>
        {categories.length > 0 && (
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Filter size={14} className="text-slate-500 shrink-0" />
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="w-full sm:w-auto rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs text-brand-charcoal focus:border-brand-charcoal focus:outline-none focus:ring-1 focus:ring-brand-charcoal"
            >
              <option value="all">{t('b2b.cat.filter_all_categories')}</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------ product dossiers */}
      {filteredProducts.length === 0 ? (
        <Surface variant="solid" className="space-y-3 rounded-2xl p-12 text-center">
          <h2 className="font-serif text-lg font-bold text-slate-700">{t('b2b.cat.empty_title')}</h2>
          <p className="mx-auto max-w-md text-xs leading-relaxed text-slate-600">{t('b2b.cat.empty_body')}</p>
          <button data-motion="upload" type="button" onClick={() => setImportModalOpen(true)} className={btnPrimary}>
            {t('b2b.cat.empty_cta')}
          </button>
        </Surface>
      ) : (
        filteredProducts.map((p) => {
          const tagState = tag[p.id] ?? { phase: 'idle' as const };
          return (
            <Surface key={p.id} variant="solid" as="article" className="space-y-4 rounded-2xl p-6">
              <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-3 sm:flex-row sm:items-center">
                <div className="flex items-center gap-3">
                  <span className="h-16 w-14 shrink-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
                    <HonestProductImage src={p.thumbnail_url} alt={p.title} className="h-full w-full object-cover" />
                  </span>
                  <div>
                    <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-600">{p.category_name}</span>
                    <h2 className="font-serif text-base font-bold text-brand-charcoal">{p.title}</h2>
                    <span className="text-xs font-bold text-brand-charcoal">{p.currency} {p.base_price}</span>
                    <span className="ms-2 text-[11px] text-slate-500">ID: {p.id}</span>
                  </div>
                </div>
                <button data-motion="creative"
                  type="button"
                  disabled={tagState.phase === 'previewing' || tagState.phase === 'applying'}
                  onClick={() => runTag(p.id, true)}
                  className={btnGhost}
                >
                  <Tags size={14} aria-hidden="true" />
                  {t('b2b.cat.tag_cta')}
                </button>
              </div>

              {/* ------------------------------------------ AI tag preview/apply */}
              {tagState.phase !== 'idle' && (
                <div className="space-y-3 rounded-xl border border-slate-200 bg-brand-wash p-4" role="status">
                  {(tagState.phase === 'previewing' || tagState.phase === 'applying') && (
                    <p className="text-xs font-semibold text-slate-600">
                      {tagState.phase === 'previewing' ? t('b2b.cat.tag_previewing') : t('b2b.cat.tag_applying')}
                    </p>
                  )}
                  {tagState.phase === 'error' && (
                    <p className={`text-xs font-semibold ${tagState.throttled ? 'text-amber-700' : 'text-rose-700'}`}>
                      {tagState.message}
                    </p>
                  )}
                  {(tagState.phase === 'preview' || tagState.phase === 'applied') && (
                    <>
                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-600">
                        <span className="font-bold text-brand-charcoal">
                          {t('b2b.cat.tag_quality')}: {tagState.data.quality}
                        </span>
                        <span>{t('b2b.cat.tag_models')}: {(tagState.data.models || []).join(', ')}</span>
                      </div>
                      {Array.isArray(tagState.data.tags) && tagState.data.tags.length > 0 && (
                        <ul className="flex flex-wrap gap-2">
                          {tagState.data.tags.map((tg: any, i: number) => (
                            <li key={i} className="rounded-full border border-slate-300 bg-white px-2.5 py-1 text-[11px] text-slate-700">
                              <strong>{tg.axis}</strong>: {tg.value} · {t('b2b.cat.tag_confidence', { pct: Math.round((tg.confidence ?? 0) * 100) })}
                            </li>
                          ))}
                        </ul>
                      )}
                      {Array.isArray(tagState.data.axes_unresolved) && tagState.data.axes_unresolved.length > 0 ? (
                        <div className="text-[11px] text-slate-600">
                          <span className="font-bold text-amber-700">{t('b2b.cat.tag_unresolved')}:</span>{' '}
                          {tagState.data.axes_unresolved.map((u: any) => `${u.axis} (${u.reason})`).join(' · ')}
                        </div>
                      ) : (
                        <p className="text-[11px] text-slate-500">{t('b2b.cat.tag_resolved')}</p>
                      )}
                      {tagState.data.disclaimer && (
                        <p className="text-[11px] text-slate-500">{tagState.data.disclaimer}</p>
                      )}
                      {tagState.phase === 'applied' ? (
                        <div className="text-[11px] text-slate-600">
                          <span className="font-bold text-emerald-700">{t('b2b.cat.tag_applied')}:</span>{' '}
                          {(tagState.data.applied || []).map((a: any) => a.field).join(', ') || '—'}
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-2 pt-1">
                          <button data-motion="admin" type="button" onClick={() => runTag(p.id, false)} className={btnPrimary}>
                            {t('b2b.cat.tag_apply')}
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* ---------------------------------------------------- SKU table */}
              <div className="overflow-x-auto">
                <table className="w-full text-start text-xs">
                  <caption className="sr-only">{t('b2b.cat.caption_products')}</caption>
                  <thead>
                    <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-600">
                      <th scope="col" className="py-2 pe-3">{t('b2b.cat.sku_th_code')}</th>
                      <th scope="col" className="py-2 pe-3">{t('b2b.cat.sku_th_size')}</th>
                      <th scope="col" className="py-2 pe-3">{t('b2b.cat.sku_th_color')}</th>
                      <th scope="col" className="py-2 pe-3">{t('b2b.cat.sku_th_stock')}</th>
                      <th scope="col" className="py-2 pe-3">{t('b2b.cat.sku_th_price')}</th>
                      <th scope="col" className="py-2 pe-3">{t('b2b.warehouse_status')}</th>
                      <th scope="col" className="py-2 text-end">{t('b2b.cat.sku_th_actions')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {p.skus?.map((sku) => (
                      <tr key={sku.id}>
                        <td className="py-3 pe-3 font-mono font-semibold text-slate-900">{sku.sku_code}</td>
                        <td className="py-3 pe-3 font-bold">{sku.size}</td>
                        <td className="py-3 pe-3">
                          <span className="flex items-center gap-1.5">
                            <span className="h-3 w-3 rounded-full border border-slate-300" style={{ backgroundColor: sku.color_hex }} aria-hidden="true"></span>
                            <span>{sku.color}</span>
                          </span>
                        </td>
                        <td className="py-3 pe-3">
                          {editingSkuId === sku.id ? (
                            <input
                              aria-label={t('b2b.cat.stock_label', { sku: sku.sku_code })}
                              type="number"
                              value={editStock}
                              onChange={(e) => setEditStock(Number(e.target.value))}
                              className="w-20 rounded-lg border border-slate-300 px-2 py-1 text-xs font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
                              min={0}
                              max={100000}
                            />
                          ) : (
                            <span className={`font-bold ${sku.stock_level > 5 ? 'text-slate-900' : 'text-rose-700'}`}>
                              {t('b2b.cat.units', { n: sku.stock_level })}
                            </span>
                          )}
                        </td>
                        <td className="py-3 pe-3">
                          {editingSkuId === sku.id ? (
                            <input
                              aria-label={t('b2b.cat.price_label', { sku: sku.sku_code })}
                              type="number"
                              step="0.01"
                              value={editPrice ?? ''}
                              onChange={(e) => setEditPrice(e.target.value ? Number(e.target.value) : undefined)}
                              placeholder={String(p.base_price)}
                              className="w-20 rounded-lg border border-slate-300 px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
                            />
                          ) : (
                            <span className="font-mono">{p.currency} {sku.price_override ?? p.base_price}</span>
                          )}
                        </td>
                        <td className="py-3 pe-3">
                          <span className={`rounded-full border px-2.5 py-1 text-[11px] font-bold ${sku.is_in_stock ? 'border-brand-mint/50 bg-brand-mint/20 text-[#065F46]' : 'border-rose-200 bg-rose-50 text-rose-700'}`}>
                            {sku.is_in_stock ? t('b2b.cat.in_stock') : t('b2b.cat.out_stock')}
                          </span>
                        </td>
                        <td className="py-3 text-end">
                          {editingSkuId === sku.id ? (
                            <span className="flex justify-end gap-1.5">
                              <button data-motion="admin" type="button" disabled={saving} onClick={() => handleSaveSku(sku.id)} className="min-h-12 rounded-xl bg-brand-charcoal px-4 text-[11px] font-bold text-white transition-colors duration-300 ease-luxury hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:opacity-50">
                                {t('b2b.cat.save')}
                              </button>
                              <button data-motion="neutral" type="button" onClick={() => setEditingSkuId(null)} className="min-h-12 rounded-xl border border-slate-300 px-3 text-[11px] font-semibold text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal">
                                {t('b2b.cat.cancel')}
                              </button>
                            </span>
                          ) : (
                            <button data-motion="admin"
                              type="button"
                              onClick={() => { setEditingSkuId(sku.id); setEditStock(sku.stock_level); setEditPrice(sku.price_override); }}
                              className="min-h-12 rounded-xl px-3 text-xs font-bold text-brand-charcoal hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
                            >
                              {t('b2b.cat.edit_stock')}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Surface>
          );
        })
      )}

      {/* ------------------------------------------------------ CSV Product Import Modal */}
      <CSVProductImportModal
        isOpen={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        onSuccess={handleImportComplete}
      />

      {/* ------------------------------------------------------ bulk CSV modal */}
      {bulkModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
          <div role="dialog" aria-modal="true" aria-label={t('b2b.import_catalog')} tabIndex={-1} className="w-full max-w-lg space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
            <h2 className="font-serif text-lg font-bold text-brand-charcoal">{t('b2b.cat.modal_title')}</h2>
            <div className="space-y-2 text-xs text-slate-600">
              <p>{t('b2b.cat.modal_required', { cols: 'title, category_slug, base_price, color_family, thumbnail_url' })}</p>
              <p>{t('b2b.cat.modal_optional', { cols: 'title_ar, description, material, currency, style_tags, sku_code, size, color, stock_level, price_override, images' })}</p>
              <p className="rounded-lg bg-amber-50 p-2 text-[11px] leading-relaxed text-amber-700">{t('b2b.cat.modal_limits')}</p>
            </div>

            <div
              role="button" tabIndex={0} aria-label={t('b2b.choose_csv')}
              onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && !isUploading) { e.preventDefault(); fileInputRef.current?.click(); } }}
              onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition-colors duration-300 ease-luxury ${dragActive ? 'border-brand-charcoal bg-brand-charcoal/5' : 'border-slate-300 bg-brand-wash'} ${isUploading ? 'pointer-events-none opacity-50' : ''}`}
            >
              <input ref={fileInputRef} type="file" accept=".csv" onChange={(e) => { if (e.target.files && e.target.files[0]) handleFileUpload(e.target.files[0]); }} className="hidden" />
              {isUploading ? (
                <div className="space-y-2">
                  <RefreshCw size={22} className="mx-auto motion-safe:animate-spin text-brand-charcoal" aria-hidden="true" />
                  <p className="text-xs font-semibold text-brand-charcoal">{t('b2b.cat.drop_processing')}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <UploadIcon size={22} className="mx-auto text-brand-charcoal" />
                  <p className="text-xs font-semibold text-slate-600">{t('b2b.cat.drop_cta')}</p>
                  <p className="text-[11px] text-slate-500">{t('b2b.cat.drop_hint')}</p>
                </div>
              )}
            </div>

            {fileError && (
              <p role="alert" className="rounded-lg border border-rose-300 bg-rose-50 p-2 text-xs font-semibold text-rose-700">
                {fileError}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <button data-motion="neutral" type="button" onClick={() => setBulkModalOpen(false)} disabled={isUploading} className={btnGhost}>
                {t('b2b.cat.modal_cancel')}
              </button>
              <button data-motion="upload" type="button" onClick={() => fileInputRef.current?.click()} disabled={isUploading} className={btnPrimary}>
                {t('b2b.cat.modal_browse')}
              </button>
            </div>

            <div className="border-t border-slate-100 pt-3 text-[11px] text-slate-500">
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold text-slate-700">{t('b2b.cat.sample_title')}</span>
                <button data-motion="download" type="button" onClick={downloadSampleCsv} className="min-h-12 rounded-xl border border-brand-charcoal px-3 text-[11px] font-semibold text-brand-charcoal transition-colors duration-300 ease-luxury hover:bg-brand-charcoal hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white">
                  {t('b2b.cat.sample_dl')}
                </button>
              </div>
              <pre className="mt-1 whitespace-pre-wrap break-all rounded-lg bg-slate-50 p-2 text-[11px] leading-relaxed">{SAMPLE_CSV}</pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
