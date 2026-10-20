import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Upload,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Download,
  Building2,
  RefreshCw,
  Bell,
  ArrowRight,
  ArrowLeft,
  X,
} from 'lucide-react';
import { brandService } from '../../services/apiServices';
import {
  PartnerStoreDetail,
  CatalogImportPreviewResponse,
  CatalogImportResult,
} from '../../models';
import { useModalFocus } from '../../hooks/useModalFocus';

interface CSVProductImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (result: CatalogImportResult) => void;
}

/**
 * The five states the job table's CHECK constraint allows. Only three are
 * terminal, so only those three stop the poller — a job that is still running
 * must never be reported as finished.
 */
const TERMINAL_JOB_STATES = new Set(['completed', 'partially_completed', 'failed']);
const POLL_INTERVAL_MS = 2500;
/** Bounded so a stuck job cannot poll forever (25 x 2.5s ≈ 1 minute). */
const MAX_POLLS = 25;

export const CSVProductImportModal: React.FC<CSVProductImportModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const [step, setStep] = useState<'upload' | 'preview' | 'processing' | 'result'>('upload');
  const [stores, setStores] = useState<PartnerStoreDetail[]>([]);
  const [targetStoreId, setTargetStoreId] = useState<number | undefined>(undefined);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [previewData, setPreviewData] = useState<CatalogImportPreviewResponse | null>(null);
  const [importResult, setImportResult] = useState<CatalogImportResult | null>(null);
  // OFF by default, matching the API contract. `confirm-import` used to default
  // to sending and was changed to an explicit opt-in, with the reasoning: a bulk
  // catalog load of a thousand rows would fire a campaign nobody asked for. The
  // modal still defaulted to `true`, so the one-click accident the API closed
  // was re-opened by the UI. Notifications are now a deliberate choice.
  const [sendNotifications, setSendNotifications] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const modalRef = useModalFocus<HTMLDivElement>(onClose, isOpen);

  // Load brand stores for branch inventory targeting
  useEffect(() => {
    if (isOpen) {
      brandService
        .getStores()
        .then((res) => {
          if (Array.isArray(res)) setStores(res);
        })
        .catch(() => setStores([]));
    } else {
      // Reset state on close
      setStep('upload');
      setSelectedFile(null);
      setPreviewData(null);
      setImportResult(null);
      setErrorMsg(null);
      setTargetStoreId(undefined);
    }
  }, [isOpen]);

  /**
   * Follow a job the server accepted but has not finished.
   *
   * `confirm-import` answers with the job id before the rows are committed, so
   * the result screen used to sit on a `processing` snapshot forever: the
   * import had not failed, the UI had simply stopped asking. This polls the
   * job row the worker writes to, so the counts on screen are the server's
   * counts and the screen moves to a terminal state on its own.
   */
  useEffect(() => {
    if (step !== 'result' || !importResult || TERMINAL_JOB_STATES.has(importResult.status)) return;
    let cancelled = false;
    let polls = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      polls += 1;
      try {
        const job = await brandService.getCatalogImportJob(importResult.job_id);
        if (cancelled) return;
        if (job) {
          setImportResult(job);
          if (TERMINAL_JOB_STATES.has(job.status)) return;
        }
      } catch {
        // A transient poll failure is not a failed import: keep the last known
        // server state on screen and try again until the bound is reached.
      }
      if (!cancelled && polls < MAX_POLLS) timer = setTimeout(tick, POLL_INTERVAL_MS);
    };
    timer = setTimeout(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // Re-running on status is the point: a non-terminal status is what keeps
    // the loop alive; a terminal one lets the cleanup below stop it.
  }, [step, importResult?.job_id, importResult?.status]);

  const saveBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // The template comes from the API that validates against it, so the header a
  // brand downloads can never drift from the header the importer accepts.
  const handleDownloadTemplate = async () => {
    try {
      const { blob, filename } = await brandService.downloadCatalogTemplate();
      saveBlob(blob, filename || 'confit-catalog-template.csv');
    } catch (err: any) {
      setErrorMsg(err?.message || t('b2b.cat.err_template_download'));
    }
  };

  const handleProcessFileForPreview = async (file: File) => {
    setErrorMsg(null);
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setErrorMsg(t('b2b.cat.file_err_type'));
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setErrorMsg(t('b2b.cat.file_err_size'));
      return;
    }

    setSelectedFile(file);
    setIsAnalyzing(true);
    try {
      const res = await brandService.previewCatalogCSV(file, targetStoreId);
      setPreviewData(res);
      setStep('preview');
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to parse CSV file. Ensure valid columns and formatting.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleProcessFileForPreview(e.dataTransfer.files[0]);
    }
  };

  const handleConfirmImport = async () => {
    if (!selectedFile) return;
    setIsImporting(true);
    setErrorMsg(null);
    try {
      const result = await brandService.confirmCatalogImport(
        selectedFile,
        targetStoreId,
        sendNotifications,
      );
      setImportResult(result);
      setStep('result');
    } catch (err: any) {
      setErrorMsg(err?.message || 'Import failed. Check error log and retry.');
    } finally {
      setIsImporting(false);
    }
  };

  const handleDone = () => {
    if (importResult) {
      onSuccess(importResult);
    }
    onClose();
  };

  /**
   * Download the row errors as CSV — from the PREVIEW or from the IMPORT.
   *
   * The old implementation called a JSON parser on a text/csv response (so it
   * always threw) and then "fell back" to `window.open` on an endpoint that
   * only accepts POST (so it answered 405). Both downloads were broken; there
   * was no working path at all. Single path now, and it reports failure instead
   * of silently opening a blank tab.
   */
  const handleDownloadErrorReport = async () => {
    const errors = importResult?.errors?.length
      ? importResult.errors
      : previewData?.errors ?? [];
    if (errors.length === 0) return;
    try {
      const { blob, filename } = await brandService.exportImportErrors(errors);
      saveBlob(blob, filename || 'confit-import-errors.csv');
    } catch (err: any) {
      setErrorMsg(err?.message || t('b2b.cat.err_report_download'));
    }
  };

  const errorCount = importResult?.errors?.length ?? previewData?.errors?.length ?? 0;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-brand-charcoal/70 p-4 backdrop-blur-sm">
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('b2b.cat.import_products_cta')}
        tabIndex={-1}
        className="relative flex max-h-[92vh] w-full max-w-4xl flex-col rounded-3xl bg-white shadow-2xl overflow-hidden border border-slate-200"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-coral/10 text-brand-coral">
              <FileSpreadsheet size={20} aria-hidden="true" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-brand-coral">
                  CONFIT Maison B2B
                </span>
                <span className="h-1 w-1 rounded-full bg-slate-300" />
                <span className="text-[10px] font-semibold text-slate-500">
                  {step === 'upload' && t('b2b.cat.step_upload')}
                  {step === 'preview' && !isImporting && t('b2b.cat.step_preview')}
                  {/* While the rows commit, say so: the preview label claimed
                      "Validate & Preview" during a write. */}
                  {step === 'preview' && isImporting && t('b2b.cat.step_processing')}
                  {step === 'result' && t('b2b.cat.step_result')}
                </span>
              </div>
              <h2 className="font-serif text-xl font-bold text-brand-charcoal">
                {t('b2b.cat.import_products_cta')}
              </h2>
            </div>
          </div>
          <button data-motion="neutral" data-motion-tone="icon"
            type="button"
            onClick={onClose}
            className="rounded-full p-2 text-slate-400 hover:bg-slate-100 hover:text-brand-charcoal transition-colors"
            aria-label={t('common.close')}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {errorMsg && (
            <div
              role="alert"
              className="mb-6 flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-xs font-medium text-rose-800"
            >
              <AlertTriangle size={16} className="shrink-0 text-rose-600 mt-0.5" />
              <div className="flex-1">{errorMsg}</div>
            </div>
          )}

          {/* STEP 1: UPLOAD */}
          {step === 'upload' && (
            <div className="space-y-6">
              <div className="rounded-2xl border border-slate-100 bg-brand-wash p-4 text-xs text-slate-600 leading-relaxed">
                <p className="font-medium text-brand-charcoal mb-1">
                  {t('b2b.cat.import_benefit_copy')}
                </p>
                <p className="text-[11px] text-slate-500">
                  {t('b2b.cat.modal_limits')}
                </p>
              </div>

              {/* Target Branch Selector */}
              {stores.length > 0 && (
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-xs font-bold text-brand-charcoal">
                    <Building2 size={14} className="text-brand-coral" />
                    {t('b2b.cat.target_branch_label')}
                  </label>
                  <select
                    value={targetStoreId ?? ''}
                    onChange={(e) =>
                      setTargetStoreId(e.target.value ? Number(e.target.value) : undefined)
                    }
                    className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs font-medium text-brand-charcoal focus:border-brand-charcoal focus:outline-none focus:ring-1 focus:ring-brand-charcoal"
                  >
                    <option value="">{t('b2b.cat.target_branch_all')}</option>
                    {stores.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.city})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Drag and Drop Zone */}
              <div
                role="button"
                tabIndex={0}
                aria-label={t('b2b.cat.drop_cta')}
                onKeyDown={(e) => {
                  if ((e.key === 'Enter' || e.key === ' ') && !isAnalyzing) {
                    e.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`flex flex-col items-center justify-center rounded-3xl border-2 border-dashed p-10 text-center transition-all cursor-pointer ${
                  dragActive
                    ? 'border-brand-coral bg-brand-coral/5 scale-[0.99]'
                    : 'border-slate-200 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-300'
                } ${isAnalyzing ? 'pointer-events-none opacity-60' : ''}`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleProcessFileForPreview(e.target.files[0]);
                    }
                  }}
                  className="hidden"
                />
                {isAnalyzing ? (
                  <div className="space-y-3">
                    <RefreshCw size={28} className="mx-auto text-brand-coral motion-safe:animate-spin" />
                    <p className="text-sm font-semibold text-brand-charcoal">
                      {t('b2b.cat.drop_processing')}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-xs border border-slate-100 text-brand-charcoal">
                      <Upload size={24} />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-brand-charcoal">
                        {t('b2b.cat.drop_cta')}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {t('b2b.cat.drop_hint')}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Official Template Action */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 rounded-2xl border border-slate-100 bg-brand-wash px-5 py-3 text-xs">
                <div>
                  <span className="font-bold text-brand-charcoal">
                    {t('b2b.cat.sample_title')}
                  </span>{' '}
                  <span className="text-slate-500">
                    product_name, sku, description, category, price, stock, color, size...
                  </span>
                </div>
                <button data-motion="download"
                  type="button"
                  onClick={handleDownloadTemplate}
                  className="inline-flex items-center gap-1.5 font-bold text-brand-coral hover:underline shrink-0"
                >
                  <Download size={14} />
                  {t('b2b.cat.sample_dl')}
                </button>
              </div>
            </div>
          )}

          {/* STEP 2: VALIDATE & PREVIEW */}
          {step === 'preview' && previewData && (
            <div className="space-y-6">
              {/* Summary Metric Badges */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                  <span className="text-[11px] font-bold text-slate-500 uppercase">
                    {t('b2b.cat.th_total')}
                  </span>
                  <div className="mt-1 text-2xl font-serif font-bold text-brand-charcoal">
                    {previewData.total_rows}
                  </div>
                </div>
                <div className="rounded-2xl border border-emerald-100 bg-emerald-50/50 p-4">
                  <span className="text-[11px] font-bold text-emerald-700 uppercase">
                    {t('b2b.cat.preview_valid_count', { n: previewData.valid_rows_count })}
                  </span>
                  <div className="mt-1 text-2xl font-serif font-bold text-emerald-700">
                    {previewData.valid_rows_count}
                  </div>
                </div>
                <div className="rounded-2xl border border-rose-100 bg-rose-50/50 p-4">
                  <span className="text-[11px] font-bold text-rose-700 uppercase">
                    {t('b2b.cat.preview_error_count', { n: previewData.error_rows_count })}
                  </span>
                  <div className="mt-1 text-2xl font-serif font-bold text-rose-700">
                    {previewData.error_rows_count}
                  </div>
                </div>
                <div className="rounded-2xl border border-amber-100 bg-amber-50/50 p-4">
                  <span className="text-[11px] font-bold text-amber-700 uppercase">
                    {t('b2b.cat.preview_dup_count', { n: previewData.duplicate_rows_count })}
                  </span>
                  <div className="mt-1 text-2xl font-serif font-bold text-amber-700">
                    {previewData.duplicate_rows_count}
                  </div>
                </div>
              </div>

              {/* Warnings: real, non-blocking findings from the server. The
                  counter badge above has existed since the first cut, but the
                  API always returned `[]`, so this section was dead. */}
              {(previewData.warnings?.length ?? 0) > 0 && (
                <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
                  <div className="flex items-center gap-2 text-xs font-bold text-amber-900">
                    <AlertTriangle size={14} className="shrink-0" />
                    {t('b2b.cat.warnings_title', { n: previewData.warnings?.length ?? 0 })}
                  </div>
                  <ul className="mt-2 space-y-1.5 text-[11px] leading-relaxed text-amber-900">
                    {(previewData.warnings ?? []).slice(0, 8).map((w, i) => (
                      <li key={`${w.field}-${i}`} className="flex gap-2">
                        <span className="font-mono text-amber-700">
                          {w.row > 1 ? t('b2b.cat.row_label', { row: w.row }) : t('b2b.cat.file_label')}
                        </span>
                        <span>{w.message}</span>
                      </li>
                    ))}
                  </ul>
                  {(previewData.warnings?.length ?? 0) > 8 && (
                    <p className="mt-1.5 text-[11px] font-semibold text-amber-800">
                      {t('b2b.cat.warnings_more', { n: (previewData.warnings?.length ?? 0) - 8 })}
                    </p>
                  )}
                </div>
              )}

              {/* A blocker is not a warning: nothing would land. Say why, and
                  keep the confirm button disabled (can_import already reflects it). */}
              {(previewData.blocked_reasons?.length ?? 0) > 0 && (
                <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-900">
                  <div className="font-bold">{t('b2b.cat.blocked_title')}</div>
                  <ul className="mt-1.5 list-disc space-y-1 ps-5">
                    {previewData.blocked_reasons!.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}

              {/* Data Preview Table */}
              <div className="rounded-2xl border border-slate-200 overflow-hidden">
                <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 flex items-center justify-between">
                  <div className="text-xs font-bold text-brand-charcoal">
                    {t('b2b.cat.preview_title')}
                  </div>
                  {previewData.error_rows_count > 0 && (
                    <button data-motion="download"
                      type="button"
                      onClick={handleDownloadErrorReport}
                      className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-700 hover:underline"
                    >
                      <Download size={13} />
                      {t('b2b.cat.btn_download_error_report')}
                    </button>
                  )}
                </div>
                <div className="overflow-x-auto max-h-72">
                  <table className="w-full text-start text-xs">
                    <caption className="sr-only">{t('b2b.cat.preview_table_caption')}</caption>
                    <thead>
                      <tr className="border-b border-slate-200 bg-white text-[10px] font-bold uppercase tracking-wider text-slate-500">
                        <th scope="col" className="py-2.5 px-3">#</th>
                        <th scope="col" className="py-2.5 px-3">{t('b2b.cat.th_status')}</th>
                        <th scope="col" className="py-2.5 px-3">{t('b2b.cat.th_action')}</th>
                        <th scope="col" className="py-2.5 px-3">{t('b2b.cat.th_product')}</th>
                        <th scope="col" className="py-2.5 px-3">{t('b2b.cat.th_sku')}</th>
                        <th scope="col" className="py-2.5 px-3">{t('b2b.cat.th_category')}</th>
                        <th scope="col" className="py-2.5 px-3">{t('b2b.cat.th_price')}</th>
                        <th scope="col" className="py-2.5 px-3">{t('b2b.cat.th_stock')}</th>
                        <th scope="col" className="py-2.5 px-3">{t('b2b.cat.th_variant')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                      {/* Defensive: a preview body without `preview_records` (older API, proxy
                      error envelope) must render an empty table, not white-screen. */}
                      {(previewData.preview_records ?? []).map((r, i) => (
                        <tr
                          key={i}
                          className={r.status === 'error' ? 'bg-rose-50/40' : 'hover:bg-slate-50/80'}
                        >
                          <td className="py-2.5 px-3 font-mono text-[11px] text-slate-400">
                            {r.row_number}
                          </td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                                r.status === 'valid'
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : 'bg-rose-100 text-rose-800'
                              }`}
                            >
                              {r.status === 'valid' ? (
                                <CheckCircle2 size={11} />
                              ) : (
                                <XCircle size={11} />
                              )}
                              {r.status}
                            </span>
                          </td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${
                                r.action === 'create'
                                  ? 'bg-blue-50 text-blue-700'
                                  : r.action === 'update'
                                  ? 'bg-amber-50 text-amber-700'
                                  : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              {r.action === 'create' && t('b2b.cat.action_create')}
                              {r.action === 'update' && t('b2b.cat.action_update')}
                              {r.action === 'error' && '—'}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 font-medium text-brand-charcoal max-w-[160px] truncate">
                            {r.product_name}
                            {r.error_message && (
                              <div className="text-[10px] text-rose-600 font-normal">
                                {r.error_message}
                              </div>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">
                            {r.sku}
                          </td>
                          <td className="py-2.5 px-3 text-slate-600">{r.category}</td>
                          <td className="py-2.5 px-3 font-semibold text-brand-charcoal">
                            {r.price} {r.currency}
                          </td>
                          <td className="py-2.5 px-3">{r.stock}</td>
                          <td className="py-2.5 px-3 text-[11px] text-slate-500">
                            {r.color} / {r.size}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Notification Dispatch Toggle */}
              <label className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-brand-wash p-4 cursor-pointer hover:bg-slate-100/60 transition-colors">
                <input
                  type="checkbox"
                  checked={sendNotifications}
                  onChange={(e) => setSendNotifications(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-brand-coral focus:ring-brand-coral"
                />
                <div className="flex items-center gap-2">
                  <Bell size={15} className="text-brand-coral shrink-0" />
                  <span className="text-xs font-semibold text-brand-charcoal">
                    {t('b2b.cat.notif_toggle_label')}
                  </span>
                </div>
              </label>
            </div>
          )}

          {/* STEP 3: RESULT */}
          {step === 'result' && importResult && (
            <div className="space-y-6 text-center py-4">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-emerald-50 text-emerald-600 border border-emerald-100">
                <CheckCircle2 size={32} />
              </div>
              <div>
                <h3 className="font-serif text-2xl font-bold text-brand-charcoal">
                  {t('b2b.cat.result_title')}
                </h3>
                <p className="mt-1 text-xs text-slate-600">
                  {t('b2b.cat.result_job', {
                    id: importResult.job_id,
                    status: t(`b2b.cat.status_${importResult.status}`, {
                      defaultValue: importResult.status,
                    }),
                  })}
                </p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-2xl mx-auto">
                <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                  <span className="text-[11px] font-bold text-slate-500 uppercase">
                    {t('b2b.cat.th_total')}
                  </span>
                  <div className="mt-1 text-2xl font-serif font-bold text-brand-charcoal">
                    {importResult.total_rows}
                  </div>
                </div>
                <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
                  <span className="text-[11px] font-bold text-emerald-700 uppercase">
                    {t('b2b.cat.result_created')}
                  </span>
                  <div className="mt-1 text-2xl font-serif font-bold text-emerald-700">
                    {importResult.accepted_rows}
                  </div>
                </div>
                <div className="rounded-2xl border border-rose-100 bg-rose-50 p-4">
                  <span className="text-[11px] font-bold text-rose-700 uppercase">
                    {t('b2b.cat.result_failed')}
                  </span>
                  <div className="mt-1 text-2xl font-serif font-bold text-rose-700">
                    {importResult.rejected_rows}
                  </div>
                </div>
                <div className="rounded-2xl border border-purple-100 bg-purple-50 p-4">
                  <span className="text-[11px] font-bold text-purple-700 uppercase">
                    {t('b2b.cat.result_notifications')}
                  </span>
                  <div className="mt-1 text-2xl font-serif font-bold text-purple-700">
                    {importResult.notifications_queued ?? 0}
                  </div>
                </div>
              </div>

              {/* The import returns facts the modal never showed: how many
                  Arabic titles are missing, how many image assets were
                  registered, and which rows were refused. Reporting "done"
                  without them would be the summary lying by omission. */}
              <div className="mx-auto max-w-2xl space-y-2 rounded-2xl border border-slate-100 bg-slate-50 p-4 text-start text-[11px] leading-relaxed text-slate-700">
                <div className="flex justify-between gap-3">
                  <span>{t('b2b.cat.result_media')}</span>
                  <span className="font-mono font-bold text-brand-charcoal">
                    {importResult.media_rows_registered ?? 0}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>{t('b2b.cat.result_missing_ar')}</span>
                  <span className="font-mono font-bold text-brand-charcoal">
                    {importResult.rows_missing_title_ar ?? 0}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>{t('b2b.cat.result_gender_inferred')}</span>
                  <span className="font-mono font-bold text-brand-charcoal">
                    {importResult.rows_gender_inferred ?? 0}
                  </span>
                </div>
                {importResult.rows_missing_title_ar ? (
                  <p className="pt-1 text-amber-800">{t('b2b.cat.result_missing_ar_hint')}</p>
                ) : null}
              </div>

              {errorCount > 0 && (
                <div className="mx-auto max-w-2xl rounded-2xl border border-rose-200 bg-rose-50 p-4 text-start">
                  <div className="text-xs font-bold text-rose-900">
                    {t('b2b.cat.result_rejected_title', { n: errorCount })}
                  </div>
                  <ul className="mt-1.5 space-y-1 text-[11px] text-rose-900">
                    {(importResult.errors ?? []).slice(0, 5).map((e: any, i: number) => (
                      <li key={i} className="flex gap-2">
                        <span className="font-mono text-rose-700">
                          {e?.row > 1 ? t('b2b.cat.row_label', { row: e.row }) : t('b2b.cat.file_label')}
                        </span>
                        <span>{e?.message}</span>
                      </li>
                    ))}
                  </ul>
                  <button data-motion="download"
                    type="button"
                    onClick={handleDownloadErrorReport}
                    className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-rose-800 hover:underline"
                  >
                    <Download size={13} />
                    {t('b2b.cat.btn_download_error_report')}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer Controls */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/50 px-6 py-4">
          {step === 'upload' && (
            <>
              <button data-motion="neutral"
                type="button"
                onClick={onClose}
                className="rounded-xl px-4 py-2.5 text-xs font-semibold text-slate-600 hover:text-brand-charcoal"
              >
                {t('b2b.cat.modal_cancel')}
              </button>
              <button data-motion="upload"
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isAnalyzing}
                className="inline-flex items-center gap-2 rounded-xl bg-brand-charcoal px-5 py-2.5 text-xs font-bold text-white hover:bg-black transition-colors"
              >
                {t('b2b.cat.modal_browse')}
              </button>
            </>
          )}

          {step === 'preview' && (
            <>
              <button data-motion="upload"
                type="button"
                onClick={() => setStep('upload')}
                disabled={isImporting}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-semibold text-slate-700 hover:bg-white"
              >
                <ArrowLeft size={14} />
                {t('b2b.cat.btn_back_upload')}
              </button>
              <button data-motion="upload"
                type="button"
                onClick={handleConfirmImport}
                disabled={isImporting || !previewData?.can_import}
                className="inline-flex items-center gap-2 rounded-xl bg-brand-coral px-6 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-[#E76A52] transition-colors disabled:opacity-50"
              >
                {isImporting ? (
                  <>
                    <RefreshCw size={14} className="motion-safe:animate-spin" />
                    <span>{t('b2b.cat.status_processing')}</span>
                  </>
                ) : (
                  <>
                    <span>
                      {t('b2b.cat.btn_confirm_import', {
                        n: previewData?.valid_rows_count ?? 0,
                      })}
                    </span>
                    <ArrowRight size={14} />
                  </>
                )}
              </button>
            </>
          )}

          {step === 'result' && (
            <div className="w-full flex justify-end">
              <button data-motion="neutral"
                type="button"
                onClick={handleDone}
                className="inline-flex items-center gap-2 rounded-xl bg-brand-charcoal px-6 py-2.5 text-xs font-bold text-white hover:bg-black transition-colors"
              >
                {t('b2b.cat.btn_view_catalog')}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
