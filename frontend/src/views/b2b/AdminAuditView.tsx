import React from 'react';
import { useTranslation } from 'react-i18next';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';
import { request } from '../../services/apiClient';
import type { AuditTrailPage, AuditIntegrity } from '../../models';

/**
 * Platform audit trail (ADMIN-01 / gap register G-05, G-07).
 *
 * The route `/admin/audit` used to render the analytics dashboard, so the audit
 * trail had no UI at all even though the API existed. This view is that UI.
 *
 * It renders only what the API returned. There is no sample data, no
 * placeholder row and no invented actor: an empty trail says so, and a failed
 * fetch shows the error with a retry instead of an empty table that looks like
 * "nothing happened".
 */

interface Filters {
  action: string;
  resource_type: string;
  resource_id: string;
  search: string;
  date_from: string;
  date_to: string;
  only_admin_actions: boolean;
}

const EMPTY_FILTERS: Filters = {
  action: '',
  resource_type: '',
  resource_id: '',
  search: '',
  date_from: '',
  date_to: '',
  only_admin_actions: false,
};

const PAGE_SIZE = 25;

const buildQuery = (filters: Filters, page: number): string => {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(PAGE_SIZE),
    include_facets: 'true',
  });
  if (filters.action) params.set('action', filters.action);
  if (filters.resource_type) params.set('resource_type', filters.resource_type);
  if (filters.resource_id) params.set('resource_id', filters.resource_id);
  if (filters.search) params.set('search', filters.search);
  if (filters.date_from) params.set('date_from', new Date(filters.date_from).toISOString());
  if (filters.date_to) params.set('date_to', new Date(filters.date_to).toISOString());
  if (filters.only_admin_actions) params.set('only_admin_actions', 'true');
  return params.toString();
};

const Json: React.FC<{ value: unknown; label: string }> = ({ value, label }) => {
  if (value === null || value === undefined) {
    return <span className="text-slate-600">{label}: —</span>;
  }
  return (
    <pre className="max-h-40 overflow-auto rounded-xl bg-slate-950/60 p-2 text-[10px] leading-relaxed text-slate-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
};

export const AdminAuditView: React.FC = () => {
  const { t } = useTranslation();
  const [page, setPage] = React.useState(1);
  const [filters, setFilters] = React.useState<Filters>(EMPTY_FILTERS);
  const [draft, setDraft] = React.useState<Filters>(EMPTY_FILTERS);
  const [data, setData] = React.useState<AuditTrailPage | null>(null);
  const [integrity, setIntegrity] = React.useState<AuditIntegrity | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [expanded, setExpanded] = React.useState<number | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [trail, check] = await Promise.all([
        request<AuditTrailPage>(`/admin/audit?${buildQuery(filters, page)}`),
        request<AuditIntegrity>('/admin/audit/integrity?window_days=30'),
      ]);
      setData(trail);
      setIntegrity(check);
    } catch (err: any) {
      setError(err?.message || t('admin_audit.unavailable_fallback'));
    } finally {
      setLoading(false);
    }
  }, [filters, page, t]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const apply = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setFilters(draft);
  };

  const reset = () => {
    setDraft(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setPage(1);
  };

  if (loading && !data) {
    return <LoadingSpinner text={t('admin_audit.loading')} />;
  }

  if (error && !data) {
    return (
      <EmptyState
        title={t('admin_audit.unavailable_title')}
        description={error}
        actionText={t('admin_audit.retry')}
        onAction={load}
      />
    );
  }

  const items = data?.items ?? [];
  const meta = data?.meta;
  const facets = data?.facets;

  const columns: Array<[string, string]> = [
    [t('admin_audit.col_when'), 'when'],
    [t('admin_audit.col_action'), 'action'],
    [t('admin_audit.col_actor'), 'actor'],
    [t('admin_audit.col_resource'), 'resource'],
    [t('admin_audit.col_changed'), 'changed'],
    [t('admin_audit.col_request'), 'request'],
    [t('admin_audit.col_ip'), 'ip'],
  ];

  return (
    <div className="space-y-6 pb-20 text-slate-100">
      <header className="border-b border-slate-800 pb-4">
        <span className="text-[10px] font-bold uppercase tracking-widest text-[#C5A059]">
          {t('admin_audit.eyebrow')}
        </span>
        <h1 className="font-serif text-3xl font-bold">{t('admin_audit.title')}</h1>
        <p className="mt-1 text-xs text-slate-400">{t('admin_audit.lede')}</p>
      </header>

      {integrity && (
        <section
          className={`rounded-2xl border p-4 text-xs ${
            integrity.verdict === 'ok'
              ? 'border-emerald-500/30 bg-emerald-500/5'
              : integrity.verdict === 'no_data'
                ? 'border-slate-700 bg-slate-900/60'
                : 'border-rose-500/40 bg-rose-500/5'
          }`}
          aria-label={t('admin_audit.integrity_aria')}
        >
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-slate-300">
              {t('admin_audit.integrity_label', { days: integrity.window_days })}
            </span>
            <span className="rounded-full bg-slate-800 px-2 py-0.5 font-mono text-[10px]">
              {t('admin_audit.integrity_verdict', { verdict: integrity.verdict })}
            </span>
            <span className="font-mono text-[10px] text-slate-400">
              {t('admin_audit.integrity_counts', {
                rows: integrity.checked_rows,
                actors: integrity.distinct_actors ?? 0,
                beforeAfter: integrity.rows_with_before_after,
                requestId: integrity.rows_with_request_id,
                ip: integrity.rows_with_ip,
              })}
            </span>
          </div>
          <p
            className={`mt-2 text-[11px] ${
              integrity.tamper_evident ? 'text-emerald-300/90' : 'text-amber-300/90'
            }`}
          >
            {t('admin_audit.integrity_tamper', {
              value: String(integrity.tamper_evident),
              note: integrity.limitations[0] ?? '',
            })}
          </p>
          {integrity.chain && (
            <p className="mt-1 font-mono text-[10px] text-slate-400">
              {t('admin_audit.integrity_chain', {
                chained: integrity.chain.chained_rows,
                unchained: integrity.chain.unchained_rows,
                breaks: integrity.chain.breaks.length,
                keyVersion: integrity.chain.key_version,
              })}
              {integrity.coverage && (
                <span className="block text-slate-500">
                  {t('admin_audit.integrity_coverage', {
                    mode: integrity.coverage.mode,
                    sampled: integrity.coverage.sampled_rows,
                    inWindow: integrity.coverage.rows_in_window,
                    days: integrity.coverage.window_days,
                  })}
                </span>
              )}
              {(integrity.chain.bypass_suspected_rows ?? 0) > 0 && (
                <span role="alert" className="block font-semibold text-rose-300">
                  {t('admin_audit.integrity_bypass', {
                    count: integrity.chain.bypass_suspected_rows,
                  })}
                </span>
              )}
              {integrity.chain.head_hash && (
                <span className="text-slate-500">
                  {' '}
                  · head {integrity.chain.head_hash.slice(0, 16)}…
                </span>
              )}
            </p>
          )}
          {integrity.violations.length > 0 && (
            <ul className="mt-2 space-y-1 text-[11px] text-rose-300">
              {integrity.violations.slice(0, 5).map((violation, index) => (
                <li key={index} className="font-mono">
                  row {violation.row_id}: {violation.issue}
                  {violation.action ? ` (${violation.action})` : ''}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <form
        onSubmit={apply}
        className="grid gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 sm:grid-cols-2 lg:grid-cols-4"
        aria-label={t('admin_audit.filters_aria')}
      >
        <label className="space-y-1 text-[10px] uppercase tracking-wider text-slate-400">
          {t('admin_audit.filters_action')}
          <input
            list="audit-actions"
            value={draft.action}
            onChange={(e) => setDraft({ ...draft, action: e.target.value })}
            placeholder="ADMIN_ORDER_TRANSITION"
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs normal-case tracking-normal text-slate-100"
          />
          <datalist id="audit-actions">
            {(facets?.actions ?? []).map((facet) => (
              <option key={facet.value} value={facet.value} />
            ))}
          </datalist>
        </label>

        <label className="space-y-1 text-[10px] uppercase tracking-wider text-slate-400">
          {t('admin_audit.filters_resource_type')}
          <input
            list="audit-resources"
            value={draft.resource_type}
            onChange={(e) => setDraft({ ...draft, resource_type: e.target.value })}
            placeholder="Order"
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs normal-case tracking-normal text-slate-100"
          />
          <datalist id="audit-resources">
            {(facets?.resource_types ?? []).map((facet) => (
              <option key={facet.value} value={facet.value} />
            ))}
          </datalist>
        </label>

        <label className="space-y-1 text-[10px] uppercase tracking-wider text-slate-400">
          {t('admin_audit.filters_resource_id')}
          <input
            value={draft.resource_id}
            onChange={(e) => setDraft({ ...draft, resource_id: e.target.value })}
            placeholder="CONF-…"
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs normal-case tracking-normal text-slate-100"
          />
        </label>

        <label className="space-y-1 text-[10px] uppercase tracking-wider text-slate-400">
          {t('admin_audit.filters_search')}
          <input
            value={draft.search}
            onChange={(e) => setDraft({ ...draft, search: e.target.value })}
            placeholder={t('admin_audit.placeholder_search')}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs normal-case tracking-normal text-slate-100"
          />
        </label>

        <label className="space-y-1 text-[10px] uppercase tracking-wider text-slate-400">
          {t('admin_audit.filters_from')}
          <input
            type="date"
            value={draft.date_from}
            onChange={(e) => setDraft({ ...draft, date_from: e.target.value })}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs normal-case tracking-normal text-slate-100"
          />
        </label>

        <label className="space-y-1 text-[10px] uppercase tracking-wider text-slate-400">
          {t('admin_audit.filters_to')}
          <input
            type="date"
            value={draft.date_to}
            onChange={(e) => setDraft({ ...draft, date_to: e.target.value })}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs normal-case tracking-normal text-slate-100"
          />
        </label>

        <label className="flex items-end gap-2 pb-2 text-[11px] text-slate-300">
          <input
            type="checkbox"
            checked={draft.only_admin_actions}
            onChange={(e) => setDraft({ ...draft, only_admin_actions: e.target.checked })}
          />
          {t('admin_audit.filters_privileged_only')}
        </label>

        <div className="flex items-end gap-2">
          <button
            type="submit"
            className="flex-1 rounded-xl bg-[#C5A059] px-4 py-2 text-[11px] font-bold uppercase tracking-wider text-[#0C0E1E]"
          >
            {t('admin_audit.filters_apply')}
          </button>
          <button
            type="button"
            onClick={reset}
            className="rounded-xl border border-slate-700 px-4 py-2 text-[11px] uppercase tracking-wider text-slate-300"
          >
            {t('admin_audit.filters_reset')}
          </button>
        </div>
      </form>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200"
        >
          {error}{' '}
          <button onClick={load} className="underline">
            {t('admin_audit.retry')}
          </button>
        </div>
      )}

      <div className="overflow-x-auto rounded-2xl border border-slate-800">
        <table className="w-full text-left text-xs">
          <caption className="sr-only">{t('admin_audit.audit_table_caption')}</caption>
          <thead className="bg-slate-900/80 text-[10px] uppercase tracking-wider text-slate-400">
            <tr>
              {columns.map(([label, key]) => (
                <th key={key} scope="col" className="px-3 py-2">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {items.map((row) => (
              <React.Fragment key={row.id}>
                <tr
                  className="cursor-pointer hover:bg-slate-900/60"
                  onClick={() => setExpanded(expanded === row.id ? null : row.id)}
                  aria-expanded={expanded === row.id}
                >
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[10px] text-slate-400">
                    {row.timestamp
                      ? new Date(row.timestamp).toISOString().replace('T', ' ').slice(0, 19)
                      : '—'}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-[#E2BF70]">{row.action}</td>
                  <td className="px-3 py-2">
                    <div className="font-semibold">{row.actor}</div>
                    <div className="text-[10px] text-slate-500">
                      {row.actor_role ?? t('admin_audit.role_unknown')}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    {row.resource_type}
                    {row.resource_id ? (
                      <span className="text-slate-500"> #{row.resource_id}</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-300">
                    {row.changed_fields.length ? row.changed_fields.join(', ') : '—'}
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-500">
                    {row.request_id ? row.request_id.slice(0, 12) : '—'}
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-500">
                    {row.ip_address ?? '—'}
                  </td>
                </tr>
                {expanded === row.id && (
                  <tr>
                    <td colSpan={columns.length} className="space-y-2 bg-slate-950/40 px-3 py-3">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
                            {t('admin_audit.before')}
                          </div>
                          <Json value={row.before} label="before" />
                        </div>
                        <div>
                          <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
                            {t('admin_audit.after')}
                          </div>
                          <Json value={row.after} label="after" />
                        </div>
                      </div>
                      {row.details && (
                        <div>
                          <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
                            {t('admin_audit.details')}
                          </div>
                          <p className="rounded-xl bg-slate-950/60 p-2 text-[11px] text-slate-300">
                            {row.details}
                          </p>
                        </div>
                      )}
                      <div className="font-mono text-[10px] text-slate-500">
                        {t('admin_audit.row_meta', {
                          id: row.id,
                          request: row.request_id ?? t('admin_audit.not_available'),
                          ip: row.ip_address ?? t('admin_audit.not_available'),
                        })}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>

        {items.length === 0 && (
          <div className="p-8 text-center text-xs text-slate-500">{t('admin_audit.empty')}</div>
        )}
      </div>

      {meta && (
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>
            {t('admin_audit.pagination', {
              total: meta.total.toLocaleString(),
              page: meta.page,
              pages: meta.total_pages,
            })}
          </span>
          <div className="flex gap-2">
            <button
              disabled={!meta.has_previous}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              className="rounded-xl border border-slate-700 px-3 py-1.5 disabled:opacity-40"
            >
              ← {t('admin_audit.previous')}
            </button>
            <button
              disabled={!meta.has_next}
              onClick={() => setPage((current) => current + 1)}
              className="rounded-xl border border-slate-700 px-3 py-1.5 disabled:opacity-40"
            >
              {t('admin_audit.next')} →
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
