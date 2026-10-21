import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useRef, useState, useMemo } from 'react';
import React from 'react';
import { Upload, Tags, RefreshCw, Search, Filter, CheckCircle2, AlertTriangle, Building2 } from 'lucide-react';
import { UploadIcon } from '../../components/icons/ConfitIcons';
import { useBrandViewModel, CatalogImportJob } from '../../viewmodels/useBrandViewModel';
import { Surface } from '../../components/common/Surface';
import { HonestProductImage } from '../../components/common/HonestProductImage';
import { request } from '../../services/apiClient';
import { brandService } from '../../services/apiServices';
import { CSVProductImportModal } from '../../components/brands/CSVProductImportModal';
import { CatalogImportResult } from '../../models';

/**
 * B03 — Catalog & SKU Management, upgraded with CSV Product Import,
 * Boutique Branch Inventory Management, and Automated Notifications.
 */

/**
 * Illustrative row shown in the dialog. It is NOT the download any more — the
 * download comes from `/partner/catalog/template.csv`, so the file a brand
 * receives is produced by the code that validates it.
 *
 * It was also wrong: it named the category `shirts`, which the seeded catalogue
 * does not contain (the seeded slugs are outerwear, tops, bottoms, dresses,
 * footwear, accessories) and it priced in EGP while the price book is
 * denominated in USD. A brand copying this example was guaranteed two
 * validation errors. Kept here only as on-screen text, and kept correct.
 */
const SAMPLE_CSV = [
  'product_name,sku,description,category,price,currency,original_price,color,size,stock_quantity,image_url,gender',
  '"Classic Cotton Shirt",CONFIT-SHIRT-001,"Regular fit crisp cotton shirt",tops,27.00,USD,33.50,White,M,25,https://images.pexels.com/photos/297933/pexels-photo-297933.jpeg,unisex',
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
    fetchErrors, refresh,
  } = useBrandViewModel();

  const [editingSkuId, setEditingSkuId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [editStock, setEditStock] = useState<number>(20);
  const [editPrice, setEditPrice] = useState<number | undefined>(undefined);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [lastImportResult, setLastImportResult] = useState<CatalogImportResult | CatalogImportJob | null>(null);
  const [tag, setTag] = useState<Record<number, TagPhase>>({});
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [domainsOpen, setDomainsOpen] = useState(false);
  const [domains, setDomains] = useState<any[]>([]);
  const [domainsLoading, setDomainsLoading] = useState(false);
  const [domainInput, setDomainInput] = useState('');
  const [domainBusy, setDomainBusy] = useState(false);
  const [domainFeedback, setDomainFeedback] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);

  const [editingProductId, setEditingProductId] = useState<number | null>(null);
  const [detailDraft, setDetailDraft] = useState<{
    title: string;
    description: string;
    description_ar: string;
    material: string;
    care_instructions: string;
    gender: string;
    style_tags: string;
    occasion_tags: string;
    chart_unit: 'cm' | 'in';
    chart_type: 'body' | 'garment';
    chart_fit: 'slim' | 'regular' | 'relaxed' | 'oversized';
    chart_source: string;
    chart_notes: string;
    chart_rows: string;
  } | null>(null);
  const [detailSaving, setDetailSaving] = useState(false);
  const [detailFeedback, setDetailFeedback] = useState<{ tone: 'ok' | 'warn' | 'err'; text: string } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (pollTimer.current) clearTimeout(pollTimer.current); }, []);

  const loadDomains = useCallback(async () => {
    setDomainsLoading(true);
    try {
      const res = await brandService.listBrandDomains();
      setDomains(Array.isArray(res?.domains) ? res.domains : []);
    } catch (err: any) {
      setDomainFeedback({ tone: 'err', text: err?.message || t('b2b.cat.domain_err_generic') });
    } finally {
      setDomainsLoading(false);
    }
  }, [t]);

  const handleToggleDomains = async () => {
    const next = !domainsOpen;
    setDomainsOpen(next);
    if (next) {
      await loadDomains();
    }
  };

  const handleClaimDomain = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!domainInput.trim() || domainBusy) return;
    setDomainBusy(true);
    setDomainFeedback(null);
    try {
      const claimed = await brandService.claimBrandDomain(domainInput.trim());
      setDomainInput('');
      setDomainFeedback({
        tone: 'ok',
        text: t('b2b.cat.domain_claimed_msg', { host: claimed.hostname }),
      });
      await loadDomains();
    } catch (err: any) {
      setDomainFeedback({ tone: 'err', text: err?.message || t('b2b.cat.domain_err_generic') });
    } finally {
      setDomainBusy(false);
    }
  };

  const handleVerifyDomain = async (hostname: string) => {
    setDomainBusy(true);
    setDomainFeedback(null);
    try {
      const res = await brandService.verifyBrandDomain(hostname);
      setDomainFeedback({
        tone: res.imports_allowed ? 'ok' : 'err',
        text: res.imports_allowed
          ? t('b2b.cat.domain_verified_msg', { host: res.hostname })
          : res.last_error || t('b2b.cat.domain_pending_msg', { host: res.hostname }),
      });
      await loadDomains();
    } catch (err: any) {
      setDomainFeedback({ tone: 'err', text: err?.message || t('b2b.cat.domain_err_generic') });
    } finally {
      setDomainBusy(false);
    }
  };

  const handleRevokeOrReleaseDomain = async (hostname: string, release: boolean) => {
    setDomainBusy(true);
    setDomainFeedback(null);
    try {
      await brandService.revokeBrandDomain(hostname, release);
      setDomainFeedback({
        tone: 'ok',
        text: release
          ? t('b2b.cat.domain_released_msg', { host: hostname })
          : t('b2b.cat.domain_revoked_msg', { host: hostname }),
      });
      await loadDomains();
    } catch (err: any) {
      setDomainFeedback({ tone: 'err', text: err?.message || t('b2b.cat.domain_err_generic') });
    } finally {
      setDomainBusy(false);
    }
  };

  const openProductEditor = (p: any) => {
    if (editingProductId === p.id) {
      setEditingProductId(null);
      setDetailDraft(null);
      setDetailFeedback(null);
      return;
    }
    const sc = p.size_chart && typeof p.size_chart === 'object' ? p.size_chart : {};
    const sizeLines = sc.sizes && typeof sc.sizes === 'object'
      ? Object.entries(sc.sizes as Record<string, Record<string, any>>)
          .map(([sz, dims]) => {
            const pairs = Object.entries(dims || {}).map(([k, v]) =>
              Array.isArray(v) ? `${k}:${v[0]}-${v[1]}` : `${k}:${v}`,
            );
            return `${sz} | ${pairs.join(', ')}`;
          })
          .join('\n')
      : '';
    setEditingProductId(p.id);
    setDetailFeedback(null);
    setDetailDraft({
      title: p.title || '',
      description: p.description || '',
      description_ar: p.description_ar || '',
      material: p.material || '',
      care_instructions: p.care_instructions || '',
      gender: p.gender || 'unisex',
      style_tags: Array.isArray(p.style_tags) ? p.style_tags.join(', ') : '',
      occasion_tags: Array.isArray(p.occasion_tags) ? p.occasion_tags.join(', ') : '',
      chart_unit: sc.unit === 'in' ? 'in' : 'cm',
      chart_type: sc.type === 'garment' ? 'garment' : 'body',
      chart_fit: (['slim', 'regular', 'relaxed', 'oversized'].includes(sc.fit_type)
        ? sc.fit_type
        : 'regular') as any,
      chart_source: sc.source || '',
      chart_notes: Array.isArray(sc.notes) ? sc.notes.join('\n') : '',
      chart_rows: sizeLines,
    });
  };

  const handleSaveProductDetails = async (productId: number) => {
    if (!detailDraft || detailSaving) return;
    setDetailSaving(true);
    setDetailFeedback(null);
    try {
      const styleList = detailDraft.style_tags
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const occList = detailDraft.occasion_tags
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await brandService.updateProductDetails(productId, {
        title: detailDraft.title.trim(),
        description: detailDraft.description,
        description_ar: detailDraft.description_ar,
        material: detailDraft.material,
        care_instructions: detailDraft.care_instructions,
        gender: detailDraft.gender,
        style_tags: styleList,
        occasion_tags: occList,
      });

      if (detailDraft.chart_rows.trim()) {
        const parsedSizes: Record<string, Record<string, [number, number] | number>> = {};
        for (const rawLine of detailDraft.chart_rows.split('\n')) {
          const line = rawLine.trim();
          if (!line) continue;
          const [szPart, dimsPart] = line.split('|');
          const sz = (szPart || '').trim();
          if (!sz || !dimsPart) continue;
          parsedSizes[sz] = {};
          for (const seg of dimsPart.split(',')) {
            const [dimName, rangeStr] = seg.split(':').map((x) => x.trim());
            if (!dimName || !rangeStr) continue;
            if (rangeStr.includes('-')) {
              const [lo, hi] = rangeStr.split('-').map((n) => Number(n.trim()));
              parsedSizes[sz][dimName] = [lo, hi];
            } else {
              parsedSizes[sz][dimName] = Number(rangeStr);
            }
          }
        }
        const notesArr = detailDraft.chart_notes
          .split('\n')
          .map((n) => n.trim())
          .filter(Boolean);
        await brandService.putProductSizeChart(productId, {
          schema_version: '1.0',
          unit: detailDraft.chart_unit,
          type: detailDraft.chart_type,
          fit_type: detailDraft.chart_fit,
          source: detailDraft.chart_source.trim() || 'Brand garment specification',
          notes: notesArr,
          sizes: parsedSizes,
        });
      }

      const warnMessages = (res.warnings || []).map((w: any) => w.message).join(' ');
      setDetailFeedback({
        tone: warnMessages ? 'warn' : 'ok',
        text: warnMessages || t('b2b.cat.details_saved_msg'),
      });
      refresh();
    } catch (err: any) {
      setDetailFeedback({
        tone: 'err',
        text: err?.message || t('b2b.cat.details_err_msg'),
      });
    } finally {
      setDetailSaving(false);
    }
  };


  /**
   * Download the template the API validates against.
   *
   * There used to be two templates: this file's hardcoded string and the
   * server's `generate_sample_csv()`. They disagreed on the category slugs, so
   * "download sample" from this dialog produced a file the importer rejected
   * while "download template" from the other dialog produced one it accepted.
   * The server is the only authority now; the local string is display-only and
   * is used as a fallback precisely because it is no longer a second contract.
   */
  const downloadSampleCsv = useCallback(async () => {
    try {
      const { blob, filename } = await brandService.downloadCatalogTemplate();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename || 'confit-catalog-template.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      const blob = new Blob(['\ufeff' + SAMPLE_CSV], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'confit-catalog-template.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }
  }, []);

  /**
   * Keep the import ledger honest while a job is still running.
   *
   * The ledger used to be a snapshot: a job that was `queued` when the page
   * loaded stayed `queued` on screen until a manual reload, even after the
   * worker finished it. One refetch timer per open page is enough — the modal
   * follows its own job, this covers "come back later" and parallel imports.
   */
  const activeJobs = importJobs.filter((j) => !TERMINAL.has(j.status)).length;
  useEffect(() => {
    if (activeJobs === 0) return;
    pollTimer.current = setTimeout(() => refresh(), 3000);
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [activeJobs, refresh]);

  const handleSaveSku = async (skuId: number) => {
    if (saving) return;
    setSaving(true);
    try {
      if (await updateSKUInventory(skuId, editStock, editPrice)) setEditingSkuId(null);
    } finally { setSaving(false); }
  };

  const handleImportComplete = (result: CatalogImportResult) => {
    setLastImportResult(result);
    // The modal already followed a non-terminal job to a terminal state before
    // it reported, so this is a refresh of settled truth — plus the ledger's
    // own poller picks up anything still running.
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
            data-motion="admin"
            type="button"
            onClick={handleToggleDomains}
            data-testid="brand-domains-toggle"
            className={btnGhost}
          >
            {t('b2b.cat.domains_cta')}
          </button>
          <button
            data-motion="upload"
            type="button"
            onClick={() => setImportModalOpen(true)}
            className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand-coral px-5 text-xs font-semibold text-white transition-colors duration-300 ease-luxury hover:bg-[#E76A52] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-coral shadow-xs"
          >
            {/* The design system's own "upload" verb glyph, not a generic
                lucide icon: the button may only borrow the vocabulary the
                brand sheets define, and the labelled text carries the meaning
                so the glyph stays decorative. */}
            <UploadIcon size={16} aria-hidden="true" />
            {/* The established entry point (B03): the modal it opens is titled
                "Import Products from CSV", but the button keeps its name so the
                screen's contract — and the audit test that pins it — hold. */}
            {t('b2b.cat.bulk_cta')}
          </button>
        </div>
      </header>

      {/* ------------------------------------------------------ verified image domains panel */}
      {domainsOpen && (
        <Surface variant="solid" as="section" className="space-y-4 rounded-2xl p-6" data-testid="brand-domains-panel">
          <div className="border-b border-slate-200 pb-3">
            <h2 className="font-serif text-lg font-bold text-brand-charcoal">
              {t('b2b.cat.domains_title')}
            </h2>
            <p className="mt-1 text-xs text-slate-600">
              {t('b2b.cat.domains_subtitle')}
            </p>
          </div>

          <form onSubmit={handleClaimDomain} className="flex flex-col sm:flex-row gap-3">
            <label htmlFor="brand-domain-claim-input" className="sr-only">
              {t('b2b.cat.domain_input_label')}
            </label>
            <input
              id="brand-domain-claim-input"
              type="text"
              value={domainInput}
              onChange={(e) => setDomainInput(e.target.value)}
              placeholder={t('b2b.cat.domain_placeholder')}
              className="flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs text-brand-charcoal focus:border-brand-charcoal focus:outline-none focus:ring-1 focus:ring-brand-charcoal"
            />
            <button
              data-motion="admin"
              type="submit"
              disabled={domainBusy || !domainInput.trim()}
              className={btnPrimary}
            >
              {t('b2b.cat.domain_claim_btn')}
            </button>
          </form>

          {domainFeedback && (
            <div
              role="status"
              className={`rounded-xl border p-3 text-xs font-medium ${
                domainFeedback.tone === 'ok'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                  : 'border-rose-200 bg-rose-50 text-rose-800'
              }`}
            >
              {domainFeedback.text}
            </div>
          )}

          {domainsLoading ? (
            <p className="text-xs text-slate-600">{t('b2b.cat.loading')}</p>
          ) : domains.length === 0 ? (
            <p className="text-xs text-slate-600">{t('b2b.cat.domains_empty')}</p>
          ) : (
            <div className="space-y-3">
              {domains.map((dom) => (
                <div
                  key={dom.hostname}
                  className="rounded-xl border border-slate-200 bg-brand-wash p-4 space-y-2 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-brand-charcoal">{dom.hostname}</span>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                          dom.imports_allowed
                            ? 'bg-emerald-100 text-emerald-800'
                            : dom.is_expired
                              ? 'bg-amber-100 text-amber-800'
                              : dom.status === 'revoked'
                                ? 'bg-rose-100 text-rose-800'
                                : 'bg-slate-200 text-slate-700'
                        }`}
                      >
                        {dom.is_expired ? t('b2b.cat.domain_status_expired') : dom.status}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        data-motion="admin"
                        type="button"
                        disabled={domainBusy}
                        onClick={() => handleVerifyDomain(dom.hostname)}
                        className={btnPrimary}
                      >
                        {t('b2b.cat.domain_verify_btn')}
                      </button>
                      {dom.status !== 'revoked' && (
                        <button
                          data-motion="neutral"
                          type="button"
                          disabled={domainBusy}
                          onClick={() => handleRevokeOrReleaseDomain(dom.hostname, false)}
                          className="min-h-12 rounded-xl border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-700"
                        >
                          {t('b2b.cat.domain_revoke_btn')}
                        </button>
                      )}
                      <button
                        data-motion="neutral"
                        type="button"
                        disabled={domainBusy}
                        onClick={() => handleRevokeOrReleaseDomain(dom.hostname, true)}
                        className="min-h-12 rounded-xl border border-rose-200 bg-white px-3 text-xs font-semibold text-rose-700"
                      >
                        {t('b2b.cat.domain_release_btn')}
                      </button>
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-white p-2.5 font-mono text-[11px] text-brand-charcoal">
                    TXT @ / {dom.hostname} → {dom.dns_record}
                  </div>
                  {dom.expires_at && (
                    <p className="text-[11px] text-slate-600">
                      {t('b2b.cat.domain_expires_label', { date: dom.expires_at.slice(0, 10) })}
                    </p>
                  )}
                  {dom.last_error && (
                    <p className="text-[11px] text-rose-700">{dom.last_error}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </Surface>
      )}

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
          <div role="region" aria-label={t('b2b.cat.caption_jobs')} tabIndex={0} className="overflow-x-auto rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white">
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
              aria-label={t('brands.filter_category_aria')}
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
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-slate-200 bg-brand-wash px-2.5 py-1 text-[11px] font-medium text-slate-600">
                    {t('b2b.cat.curation_readonly')}
                  </span>
                  <button
                    data-motion="admin"
                    type="button"
                    onClick={() => openProductEditor(p)}
                    data-testid={`edit-product-${p.id}`}
                    className={btnGhost}
                  >
                    {t('b2b.cat.edit_details_cta')}
                  </button>
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
              </div>

              {editingProductId === p.id && detailDraft && (
                <div className="space-y-4 rounded-xl border border-slate-200 bg-brand-wash p-4 text-xs" data-testid={`product-editor-${p.id}`}>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <label className="space-y-1">
                      <span className="font-semibold text-brand-charcoal">{t('b2b.cat.field_title')}</span>
                      <input
                        type="text"
                        value={detailDraft.title}
                        onChange={(e) => setDetailDraft({ ...detailDraft, title: e.target.value })}
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                      />
                    </label>
                    <label className="space-y-1">
                      <span className="font-semibold text-brand-charcoal">{t('b2b.cat.field_gender')}</span>
                      <select
                        value={detailDraft.gender}
                        onChange={(e) => setDetailDraft({ ...detailDraft, gender: e.target.value })}
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                      >
                        <option value="womens">{t('discover.gender_womens')}</option>
                        <option value="mens">{t('discover.gender_mens')}</option>
                        <option value="unisex">{t('discover.gender_unisex')}</option>
                      </select>
                    </label>
                    <label className="space-y-1">
                      <span className="font-semibold text-brand-charcoal">{t('b2b.cat.field_material')}</span>
                      <input
                        type="text"
                        value={detailDraft.material}
                        onChange={(e) => setDetailDraft({ ...detailDraft, material: e.target.value })}
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                      />
                    </label>
                    <label className="space-y-1">
                      <span className="font-semibold text-brand-charcoal">{t('b2b.cat.field_care')}</span>
                      <input
                        type="text"
                        value={detailDraft.care_instructions}
                        onChange={(e) => setDetailDraft({ ...detailDraft, care_instructions: e.target.value })}
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                      />
                    </label>
                    <label className="space-y-1">
                      <span className="font-semibold text-brand-charcoal">{t('b2b.cat.field_style_tags')}</span>
                      <input
                        type="text"
                        value={detailDraft.style_tags}
                        onChange={(e) => setDetailDraft({ ...detailDraft, style_tags: e.target.value })}
                        placeholder={t('b2b.cat.style_placeholder')}
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                      />
                    </label>
                    <label className="space-y-1">
                      <span className="font-semibold text-brand-charcoal">{t('b2b.cat.field_occasion_tags')}</span>
                      <input
                        type="text"
                        value={detailDraft.occasion_tags}
                        onChange={(e) => setDetailDraft({ ...detailDraft, occasion_tags: e.target.value })}
                        placeholder={t('b2b.cat.occasion_placeholder')}
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                      />
                    </label>
                    <label className="space-y-1 sm:col-span-2">
                      <span className="font-semibold text-brand-charcoal">{t('b2b.cat.field_description')}</span>
                      <textarea
                        rows={2}
                        value={detailDraft.description}
                        onChange={(e) => setDetailDraft({ ...detailDraft, description: e.target.value })}
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                      />
                    </label>
                  </div>

                  <div className="border-t border-slate-200 pt-3 space-y-3">
                    <h3 className="font-bold text-brand-charcoal">{t('b2b.cat.chart_section_title')}</h3>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
                      <label className="space-y-1">
                        <span className="font-semibold text-brand-charcoal">{t('b2b.cat.chart_unit')}</span>
                        <select
                          value={detailDraft.chart_unit}
                          onChange={(e) => setDetailDraft({ ...detailDraft, chart_unit: e.target.value as 'cm' | 'in' })}
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                        >
                          <option value="cm">cm</option>
                          <option value="in">in</option>
                        </select>
                      </label>
                      <label className="space-y-1">
                        <span className="font-semibold text-brand-charcoal">{t('b2b.cat.chart_basis')}</span>
                        <select
                          value={detailDraft.chart_type}
                          onChange={(e) => setDetailDraft({ ...detailDraft, chart_type: e.target.value as 'body' | 'garment' })}
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                        >
                          <option value="body">body</option>
                          <option value="garment">garment</option>
                        </select>
                      </label>
                      <label className="space-y-1">
                        <span className="font-semibold text-brand-charcoal">{t('b2b.cat.chart_fit')}</span>
                        <select
                          value={detailDraft.chart_fit}
                          onChange={(e) => setDetailDraft({ ...detailDraft, chart_fit: e.target.value as any })}
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                        >
                          <option value="slim">slim</option>
                          <option value="regular">regular</option>
                          <option value="relaxed">relaxed</option>
                          <option value="oversized">oversized</option>
                        </select>
                      </label>
                      <label className="space-y-1">
                        <span className="font-semibold text-brand-charcoal">{t('b2b.cat.chart_source')}</span>
                        <input
                          type="text"
                          value={detailDraft.chart_source}
                          onChange={(e) => setDetailDraft({ ...detailDraft, chart_source: e.target.value })}
                          placeholder={t('b2b.cat.chart_source_placeholder')}
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                        />
                      </label>
                    </div>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <label className="space-y-1">
                        <span className="font-semibold text-brand-charcoal">{t('b2b.cat.chart_rows_label')}</span>
                        <textarea
                          rows={3}
                          value={detailDraft.chart_rows}
                          onChange={(e) => setDetailDraft({ ...detailDraft, chart_rows: e.target.value })}
                          placeholder={t('b2b.cat.chart_rows_placeholder')}
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-brand-charcoal"
                        />
                      </label>
                      <label className="space-y-1">
                        <span className="font-semibold text-brand-charcoal">{t('b2b.cat.chart_notes_label')}</span>
                        <textarea
                          rows={3}
                          value={detailDraft.chart_notes}
                          onChange={(e) => setDetailDraft({ ...detailDraft, chart_notes: e.target.value })}
                          placeholder={t('b2b.cat.chart_notes_placeholder')}
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-brand-charcoal"
                        />
                      </label>
                    </div>
                  </div>

                  {detailFeedback && (
                    <div
                      role="status"
                      className={`rounded-lg border p-2.5 text-xs ${
                        detailFeedback.tone === 'ok'
                          ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                          : detailFeedback.tone === 'warn'
                            ? 'border-amber-200 bg-amber-50 text-amber-900'
                            : 'border-rose-200 bg-rose-50 text-rose-800'
                      }`}
                    >
                      {detailFeedback.text}
                    </div>
                  )}

                  <div className="flex justify-end gap-2">
                    <button
                      data-motion="neutral"
                      type="button"
                      onClick={() => {
                        setEditingProductId(null);
                        setDetailDraft(null);
                      }}
                      className="min-h-12 rounded-xl border border-slate-300 bg-white px-4 text-xs font-semibold text-slate-700"
                    >
                      {t('b2b.cat.cancel')}
                    </button>
                    <button
                      data-motion="admin"
                      type="button"
                      disabled={detailSaving}
                      onClick={() => handleSaveProductDetails(p.id)}
                      className={btnPrimary}
                    >
                      {t('b2b.cat.save')}
                    </button>
                  </div>
                </div>
              )}

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
              <div role="region" aria-label={t('b2b.cat.caption_products')} tabIndex={0} className="overflow-x-auto rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white">
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

    </div>
  );
};
