import React from 'react';
import { useTranslation } from 'react-i18next';
import { usePlatformReadiness } from '../../hooks/usePlatformReadiness';

/**
 * P1 closure (2026-09-22 admin audit): the admin dashboard must surface the
 * platform's real readiness verdict instead of letting rich KPI cards imply
 * "everything works" while `/health` says `ready=false`.
 *
 * Three honest states, all sourced from the backend's own capability
 * registry (`/health` — the same one the services read):
 *
 *  - ready       → a quiet confirmation line (not a celebration banner);
 *  - not_ready   → a prominent blocker banner NAMING the blocked and
 *                  degraded capabilities, verbatim from the backend;
 *  - unknown     → the health endpoint itself was unreachable; said as such,
 *                  never rendered as green.
 *
 * role="status" (ready/unknown) vs role="alert" (not_ready) so screen readers
 * announce a blocker without being interrupted by routine confirmations.
 */
export const ReadinessBanner: React.FC = () => {
  const { t } = useTranslation();
  const { verdict, readiness, isLoading } = usePlatformReadiness();

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="readiness-banner-loading"
        className="rounded-2xl border border-slate-300 bg-slate-50 p-3 text-xs text-slate-700"
      >
        {t('admin_readiness.loading_body')}
      </div>
    );
  }

  if (verdict === 'not_ready' && readiness) {
    return (
      <div
        role="alert"
        data-testid="readiness-banner-blocked"
        className="rounded-2xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-900"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-rose-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-white">
            {t('admin_readiness.blocked_tag')}
          </span>
          <span className="font-bold">{t('admin_readiness.blocked_title')}</span>
        </div>
        <p className="mt-2 text-xs">
          {t('admin_readiness.blocked_body')}
        </p>
        {readiness.blocking_capabilities.length > 0 && (
          <p className="mt-1 font-mono text-xs" data-testid="readiness-blocking-list">
            {t('admin_readiness.blocking_label')}{' '}
            {readiness.blocking_capabilities.join(', ')}
          </p>
        )}
        {readiness.degraded_capabilities.length > 0 && (
          <p className="mt-1 font-mono text-xs text-rose-700" data-testid="readiness-degraded-list">
            {t('admin_readiness.degraded_label')}{' '}
            {readiness.degraded_capabilities.join(', ')}
          </p>
        )}
        {(readiness.unprobed_capabilities?.length ?? 0) > 0 && (
          <p className="mt-1 font-mono text-xs text-amber-800" data-testid="readiness-unprobed-list">
            {t('admin_readiness.unprobed_label')}{' '}
            {readiness.unprobed_capabilities.join(', ') }
          </p>
        )}
      </div>
    );
  }

  if (verdict === 'unknown') {
    return (
      <div
        role="status"
        data-testid="readiness-banner-unknown"
        className="rounded-2xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900"
      >
        {t('admin_readiness.unknown_body')}
      </div>
    );
  }

  return (
    <div
      role="status"
      data-testid="readiness-banner-ready"
      className="rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900"
    >
      {t('admin_readiness.ready_body')}
      {readiness?.degraded_capabilities?.length ? (
        <span className="ml-1 font-mono" data-testid="readiness-degraded-list">
          {t('admin_readiness.degraded_label')} {readiness.degraded_capabilities.join(', ')}
        </span>
      ) : null}
      {readiness?.unprobed_capabilities?.length ? (
        <span className="ml-1 font-mono text-amber-900" data-testid="readiness-unprobed-list">
          {t('admin_readiness.unprobed_label')} {readiness.unprobed_capabilities.join(', ')}
        </span>
      ) : null}
    </div>
  );
};
