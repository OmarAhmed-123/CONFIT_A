import React, { useCallback, useEffect, useState } from 'react';
import { brandTeamService } from '../../services/apiServices';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';
import { ApiError } from '../../services/apiClient';

/**
 * /b2b/team — invite colleagues into this brand workspace (BRD G6 §2.1).
 *
 * The inviter chooses a role from the brand roles only; the admin role cannot
 * be granted here, and when no email provider is configured the API returns the
 * one-time accept path so the flow is still completable (never a fake send).
 */
export const BrandTeamView: React.FC = () => {
  const [invitations, setInvitations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('brand_staff');
  const [busy, setBusy] = useState(false);
  const [manualLink, setManualLink] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setInvitations(await brandTeamService.listInvitations(true));
      setError(null);
    } catch (err) {
      setError((err as ApiError)?.message || 'Could not load invitations.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);
    setManualLink(null);
    try {
      const res = await brandTeamService.createInvitation({ email, role });
      const delivery = res.delivery?.status ?? 'blocked';
      setInfo(
        delivery === 'succeeded'
          ? `Invitation emailed to ${res.email}. It expires in 72 hours and can be accepted once.`
          : `Invitation created for ${res.email}, but no email was delivered (status: ${delivery}). Use the one-time link below to complete the invitation manually — nothing is claimed as sent.`
      );
      if (res.accept_path && delivery !== 'succeeded') {
        setManualLink(`${window.location.origin}${res.accept_path}`);
      }
      setEmail('');
      await load();
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr?.message || 'The invitation could not be created.');
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: number) => {
    try {
      await brandTeamService.revokeInvitation(id);
      await load();
    } catch (err) {
      setError((err as ApiError)?.message || 'Could not revoke that invitation.');
    }
  };

  return (
    <div className="space-y-6 pb-20">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="font-serif text-3xl font-bold text-white">Brand Team</h1>
        <p className="text-xs sm:text-sm text-slate-400 mt-1">
          Invite colleagues into this workspace. Role and workspace are recorded server-side at invitation time;
          the admin role can never be granted by invitation.
        </p>
      </div>

      <form onSubmit={invite} className="bg-white rounded-3xl border border-slate-200 p-5 grid md:grid-cols-[2fr_1fr_auto] gap-3 items-end shadow-sm">
        <label className="block space-y-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Colleague email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm text-slate-800 focus:outline-none focus:border-[#C5A059]"
            placeholder="colleague@brand.com"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Role</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm text-slate-800 focus:outline-none focus:border-[#C5A059]"
          >
            <option value="brand_staff">brand_staff</option>
            <option value="brand_manager">brand_manager</option>
            <option value="brand_owner">brand_owner</option>
          </select>
        </label>
        <button
          type="submit"
          disabled={busy}
          className="px-5 py-3 rounded-xl bg-[#1B1F3B] text-white text-xs font-bold disabled:opacity-50"
        >
          {busy ? 'Sending…' : 'Send invitation'}
        </button>
      </form>

      {info && <div className="p-3 rounded-xl bg-slate-900 border border-slate-700 text-slate-200 text-xs">{info}</div>}
      {manualLink && (
        <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-100 text-[11px] break-all">
          One-time accept link (shown once, never emailed because delivery is unconfigured): <br />
          <span className="font-mono">{manualLink}</span>
        </div>
      )}
      {error && (
        <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-500/40 text-rose-200 text-xs" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <LoadingSpinner text="Loading invitations…" />
      ) : invitations.length === 0 ? (
        <EmptyState title="No invitations yet" description="Invitations created for this brand appear here with their real delivery status." />
      ) : (
        <div className="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-sm">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#FAF9F6] text-slate-500 uppercase tracking-wider text-[10px]">
              <tr>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Expires</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {invitations.map((inv) => (
                <tr key={inv.id} className="border-t border-slate-100 text-slate-700">
                  <td className="px-4 py-3">{inv.email}</td>
                  <td className="px-4 py-3 font-mono">{inv.role}</td>
                  <td className="px-4 py-3">{inv.status}</td>
                  <td className="px-4 py-3">{new Date(inv.expires_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    {inv.status === 'pending' && (
                      <button onClick={() => revoke(inv.id)} className="text-rose-600 hover:underline">
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
