import React from 'react';
import { useTranslation } from 'react-i18next';
import { FileDown } from 'lucide-react';
import { adminService } from '../../services/apiServices';
import { localizeApiError } from '../../i18n/apiErrors';

/**
 * Spec 12 export — the download control next to each brand name.
 *
 * Contract (§5 export pending/success/error, §7, §11):
 *  · the PDF comes from the REAL admin endpoint; there is no client-side
 *    generation and no success before the server's bytes arrive;
 *  · pending/success/error are announced as TEXT inside aria-live=polite —
 *    never only a spinner or a colour change;
 *  · accessible name carries the brand name (icon is decorative);
 *  · ≥44px target (min-h-11); the button guards re-entry with aria-busy
 *    instead of `disabled`, so keyboard focus is never dropped mid-flow;
 *  · the server names the file (Content-Disposition) — the client only
 *    falls back to a deterministic name if a proxy stripped the header.
 */
export const BrandReportDownloadButton: React.FC<{
  brandId: number;
  brandName: string;
  className?: string;
}> = ({ brandId, brandName, className }) => {
  const { t } = useTranslation();
  const [phase, setPhase] = React.useState<'idle' | 'pending' | 'done' | 'error'>('idle');
  const [errorText, setErrorText] = React.useState<string | null>(null);

  const download = async () => {
    if (phase === 'pending') return; // aria-busy re-entry guard
    setPhase('pending');
    setErrorText(null);
    try {
      const { blob, filename } = await adminService.downloadBrandReportPdf(brandId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename || `confit-brand-${brandId}-report.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setPhase('done');
    } catch (err) {
      setErrorText(localizeApiError(err, t, 'admin_catalog.report_failed'));
      setPhase('error');
    }
  };

  return (
    <span className={className}>
      <button
        type="button"
        onClick={download}
        aria-busy={phase === 'pending'}
        aria-label={t('admin_catalog.download_report', { brand: brandName })}
        className="inline-flex min-h-11 items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-[11px] font-bold text-slate-700 shadow-2xs transition-colors hover:border-[#B8935A] hover:text-[#8A6A2F] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A]"
      >
        <span aria-hidden="true"><FileDown className="h-3.5 w-3.5" /></span>
        <span>{t('admin_catalog.report_pdf')}</span>
      </button>
      {/* State as TEXT, politely announced — never colour/animation alone. */}
      <span aria-live="polite" className="ms-2 text-[11px]">
        {phase === 'pending' && (
          <span className="text-slate-500">{t('admin_catalog.report_pending')}</span>
        )}
        {phase === 'done' && (
          <span className="text-emerald-700">{t('admin_catalog.report_done')}</span>
        )}
        {phase === 'error' && (
          <span className="text-rose-700">{errorText}</span>
        )}
      </span>
    </span>
  );
};
