import React, { useCallback, useEffect, useState } from 'react';
import { adminPartnerService } from '../../services/apiServices';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';
import { ApiError } from '../../services/apiClient';

/**
 * /admin/partners — partner onboarding approvals (BRD G6 §2.2).
 *
 * Approving here is the ONLY self-service path from a consumer account to a
 * brand role: the server provisions the brand tenant and grants brand_owner in
 * one transaction, records a before/after audit row and emails the applicant.
 * The UI displays the consequence before the admin commits to it.
 */
export const AdminPartnersView: React.FC = () => {
  const [status, setStatus] = useState('pending');
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminPartnerService.list(status);
      setItems(res.items || []);
      setError(null);
    } catch (err) {
      setError((err as ApiError)?.message || 'Could not load partner applications.');
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const decide = async (id: number, approve: boolean) => {
    setBusyId(id);
    try {
      if (approve) await adminPartnerService.approve(id, notes[id]);
      else await adminPartnerService.reject(id, notes[id]);
      await load();
    } catch (err) {
      const apiErr = err as ApiError;
      setError(
        apiErr?.code === 'ADMIN_REAUTH_REQUIRED'
          ? 'Your admin session is older than the 60-minute step-up policy. Sign in again to record this decision.'
          : apiErr?.message || 'The decision could not be recorded.'
      );
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6 pb-20">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="font-serif text-3xl font-bold text-white">Partner Onboarding Approvals</h1>
        <p className="text-xs sm:text-sm text-slate-400 mt-1">
          Every application is a request, not a grant. Approval provisions the brand tenant and the
          <span className="text-[#C5A059]"> brand_owner</span> role server-side and is recorded in the audit log
          with a correlation id.
        </p>
      </div>

      <div className="flex gap-2" role="tablist" aria-label="Application status filter">
        {['pending', 'approved', 'rejected', 'withdrawn'].map((s) => (
          <button
            key={s}
            role="tab"
            aria-selected={status === s}
            onClick={() => setStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold uppercase tracking-wider border ${
              status === s ? 'bg-[#C5A059] text-[#0C0E1E] border-[#C5A059]' : 'bg-slate-900 text-slate-300 border-slate-700'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-500/40 text-rose-200 text-xs" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <LoadingSpinner text="Loading applications…" />
      ) : items.length === 0 ? (
        <EmptyState
          title={`No ${status} applications`}
          description="Nothing to review in this state right now. This list is read from the database — it is never padded."
        />
      ) : (
        <div className="grid gap-4">
          {items.map((a) => (
            <div key={a.id} className="bg-white rounded-3xl border border-slate-200 p-5 space-y-3 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="font-serif text-lg font-bold text-[#1B1F3B]">{a.brand_name}</h2>
                  <p className="text-[11px] text-slate-500">
                    #{a.id} · {a.contact_name} · {a.contact_email} · market {a.market}
                  </p>
                </div>
                <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                  {a.status}
                </span>
              </div>
              <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-[12px] text-slate-600">
                {a.website && <div><strong>Website:</strong> {a.website}</div>}
                {a.category && <div><strong>Category:</strong> {a.category}</div>}
                {a.catalogue_size && <div><strong>Catalogue:</strong> {a.catalogue_size}</div>}
                {a.contact_phone && <div><strong>Phone:</strong> {a.contact_phone}</div>}
                <div><strong>Submitted:</strong> {new Date(a.submitted_at).toLocaleString()}</div>
                {a.reviewed_at && <div><strong>Reviewed:</strong> {new Date(a.reviewed_at).toLocaleString()}</div>}
                {a.brand_id && <div><strong>Brand tenant:</strong> #{a.brand_id}</div>}
              </div>
              {a.message && (
                <p className="text-[12px] text-slate-700 bg-[#FAF9F6] rounded-xl p-3 border border-slate-200">{a.message}</p>
              )}
              {a.decision_note && <p className="text-[12px] text-slate-500">Decision note: {a.decision_note}</p>}

              {a.status === 'pending' && (
                <div className="space-y-2 pt-1">
                  <textarea
                    rows={2}
                    placeholder="Reviewer note (stored in the audit trail and emailed to the applicant on rejection)"
                    value={notes[a.id] || ''}
                    onChange={(e) => setNotes({ ...notes, [a.id]: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs text-slate-800 focus:outline-none focus:border-[#C5A059]"
                  />
                  <div className="flex gap-3">
                    <button
                      disabled={busyId === a.id}
                      onClick={() => decide(a.id, true)}
                      className="px-4 py-2.5 rounded-xl bg-[#1B1F3B] text-white text-xs font-bold disabled:opacity-50"
                    >
                      {busyId === a.id ? 'Recording…' : 'Approve & provision brand_owner'}
                    </button>
                    <button
                      disabled={busyId === a.id}
                      onClick={() => decide(a.id, false)}
                      className="px-4 py-2.5 rounded-xl bg-white border border-slate-300 text-slate-700 text-xs font-semibold disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                  <p className="text-[10px] text-slate-500">
                    Approving creates (or links) the brand tenant and grants brand_owner. Requires a fresh admin session
                    (60-minute step-up policy).
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
