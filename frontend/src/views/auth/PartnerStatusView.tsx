import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AuthShell, AuthButton, AuthNote } from './AuthShell';
import { partnerService } from '../../services/apiServices';
import { useAuthStore } from '../../stores/authStore';
import { PartnerApplication } from '../../models';

const STATUS_LABEL: Record<string, string> = {
  pending: 'In review',
  approved: 'Approved',
  rejected: 'Not approved',
  withdrawn: 'Withdrawn',
};

/** /partner/status — the applicant's own view of every application. */
export const PartnerStatusView: React.FC = () => {
  const { user, isAuthenticated, fetchMe } = useAuthStore();
  const [rows, setRows] = useState<PartnerApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setRows(await partnerService.listMine());
      setError(null);
    } catch {
      setError('We could not load your applications.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  const withdraw = async (id: number) => {
    try {
      await partnerService.withdraw(id);
      await fetchMe();
      await load();
    } catch {
      setError('That application could not be withdrawn.');
    }
  };

  if (!isAuthenticated) {
    return (
      <AuthShell eyebrow="Partner onboarding" title="Sign in to view your applications">
        <AuthNote>Sign in with the account that submitted the application.</AuthNote>
      </AuthShell>
    );
  }

  return (
    <AuthShell eyebrow="Partner onboarding" title="Your partner applications" tone="neutral">
      {user?.role !== 'consumer' && (
        <AuthNote tone="success">
          This account holds the <strong>{user?.role}</strong> role — the brand portal is available now.
        </AuthNote>
      )}
      {loading && <AuthNote>Loading…</AuthNote>}
      {error && <AuthNote tone="error">{error}</AuthNote>}
      {!loading && rows.length === 0 && (
        <>
          <AuthNote>You have no partner applications yet.</AuthNote>
          <Link to="/partner/apply" className="block text-center text-[#C5A059] hover:underline">
            Apply for partner access →
          </Link>
        </>
      )}
      {rows.map((a) => (
        <div key={a.id} className="p-4 rounded-2xl bg-[#141833] border border-slate-700 space-y-1">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-white text-sm">{a.brand_name}</span>
            <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800 text-[#C5A059]">
              {STATUS_LABEL[a.status] || a.status}
            </span>
          </div>
          <div className="text-[11px] text-slate-400">
            Submitted {new Date(a.submitted_at).toLocaleString()}
            {a.reviewed_at ? ` · reviewed ${new Date(a.reviewed_at).toLocaleString()}` : ''}
          </div>
          {a.decision_note && <div className="text-[11px] text-slate-300">Reviewer note: {a.decision_note}</div>}
          {a.status === 'pending' && (
            <div className="pt-2">
              <AuthButton variant="ghost" onClick={() => withdraw(a.id)}>Withdraw application</AuthButton>
            </div>
          )}
        </div>
      ))}
      {rows.some((a) => a.status !== 'pending') && (
        <Link to="/partner/apply" className="block text-center text-[#C5A059] hover:underline">
          Submit a new application →
        </Link>
      )}
    </AuthShell>
  );
};
