import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthShell, AuthButton, AuthInput, AuthNote } from './AuthShell';
import { partnerService, authService } from '../../services/apiServices';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { ApiError } from '../../services/apiClient';
import { PartnerApplication } from '../../models';

/**
 * /partner/apply — the self-service entry to the partner workflow.
 *
 * Submitting creates a PENDING application and nothing else. No role, no
 * tenant, no portal access is granted here; a platform admin decides
 * (BRD G6 §2.2), and the outcome is delivered by email + visible on
 * /partner/status.
 */
export const PartnerApplyView: React.FC = () => {
  const { user, isAuthenticated, hasAttemptedBootstrap, fetchMe } = useAuthStore();
  const { openAuthModal } = useUIStore();
  const navigate = useNavigate();
  const [applications, setApplications] = useState<PartnerApplication[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [form, setForm] = useState({
    brand_name: '',
    legal_name: '',
    website: '',
    market: 'EG',
    category: '',
    catalogue_size: '',
    contact_name: user?.full_name || '',
    contact_phone: '',
    message: '',
  });

  useEffect(() => {
    if (!isAuthenticated) return;
    partnerService
      .listMine()
      .then((rows) => setApplications(rows))
      .catch(() => setApplications([]));
  }, [isAuthenticated]);

  const latest = applications[0];
  const hasPending = applications.some((a) => a.status === 'pending');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setNeedsVerification(false);
    try {
      await partnerService.submitApplication({
        ...form,
        contact_name: form.contact_name || user?.full_name || '',
      });
      await fetchMe();
      navigate('/partner/status', { replace: true });
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr?.code === 'EMAIL_VERIFICATION_REQUIRED') {
        setNeedsVerification(true);
        setError('Verify your email address first — partner decisions are delivered by email.');
      } else if (apiErr?.code === 'PARTNER_APPLICATION_PENDING') {
        setError('You already have an application in review.');
      } else {
        setError(apiErr?.message || 'We could not submit your application.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (!hasAttemptedBootstrap) {
    return (
      <AuthShell eyebrow="Partner onboarding" title="Loading…">
        <AuthNote>Checking your session…</AuthNote>
      </AuthShell>
    );
  }

  if (!isAuthenticated || !user) {
    return (
      <AuthShell eyebrow="Partner onboarding" title="Sign in to apply">
        <p className="text-slate-400">
          Partner applications are tied to a verified CONFIT account. Sign in (or create one) and you will return here.
        </p>
        <AuthButton onClick={() => openAuthModal('login')}>Sign in</AuthButton>
        <AuthButton variant="ghost" onClick={() => openAuthModal('register')}>Create an account</AuthButton>
      </AuthShell>
    );
  }

  if (user.role !== 'consumer') {
    return (
      <AuthShell eyebrow="Partner onboarding" title="This account already has brand access" tone="success">
        <AuthNote tone="success">
          Role: <strong>{user.role}</strong>. Open the brand portal to continue.
        </AuthNote>
        <Link to="/b2b" className="block text-center text-[#C5A059] hover:underline">Open the brand portal →</Link>
      </AuthShell>
    );
  }

  if (hasPending) {
    return (
      <AuthShell eyebrow="Partner onboarding" title="Application in review" tone="warning">
        <AuthNote>
          <strong>{latest.brand_name}</strong> — submitted {new Date(latest.submitted_at).toLocaleDateString()}.
          A platform admin reviews every application; you will be emailed as soon as a decision is recorded.
        </AuthNote>
        <Link to="/partner/status" className="block text-center text-[#C5A059] hover:underline">View status →</Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell eyebrow="Partner onboarding" title="Apply for partner access">
      <AuthNote>
        Requesting access does not grant it. After review, an approved brand gets its own workspace with a
        <strong> brand_owner</strong> role — and nothing is provisioned before that decision.
      </AuthNote>
      {latest && latest.status === 'rejected' && (
        <AuthNote tone="error">
          Your previous application for <strong>{latest.brand_name}</strong> was not approved.
          {latest.decision_note ? ` Reviewer note: ${latest.decision_note}` : ''} You can submit the details again below.
        </AuthNote>
      )}
      {needsVerification && (
        <AuthNote tone="error">
          Verify your email first.{' '}
          <Link to="/verify-email" className="underline">Open email verification →</Link>
        </AuthNote>
      )}
      <form onSubmit={submit} className="space-y-3">
        <AuthInput
          label="Brand name *"
          required
          value={form.brand_name}
          onChange={(e) => setForm({ ...form, brand_name: e.target.value })}
          placeholder="e.g. Atelier Cairo"
        />
        <AuthInput
          label="Contact name *"
          required
          value={form.contact_name}
          onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
        />
        <AuthInput
          label="Contact phone"
          value={form.contact_phone}
          onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
        />
        <AuthInput
          label="Website"
          value={form.website}
          onChange={(e) => setForm({ ...form, website: e.target.value })}
          placeholder="https://"
        />
        <AuthInput
          label="Category"
          value={form.category}
          onChange={(e) => setForm({ ...form, category: e.target.value })}
          placeholder="Ready-to-wear, accessories, …"
        />
        <AuthInput
          label="Catalogue size"
          value={form.catalogue_size}
          onChange={(e) => setForm({ ...form, catalogue_size: e.target.value })}
          placeholder="e.g. ~120 SKUs"
        />
        <label className="block space-y-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Notes for the review team</span>
          <textarea
            rows={3}
            value={form.message}
            onChange={(e) => setForm({ ...form, message: e.target.value })}
            className="w-full px-3.5 py-2.5 rounded-xl bg-[#141833] border border-slate-700 text-white text-sm focus:outline-none focus:border-[#C5A059]"
          />
        </label>
        {error && <AuthNote tone="error">{error}</AuthNote>}
        <AuthButton type="submit" disabled={submitting}>
          {submitting ? 'Submitting…' : 'Submit application'}
        </AuthButton>
      </form>
      <p className="text-[11px] text-slate-500">
        Decisions are emailed to {user.email}. Your account keeps working as a shopper while the review runs.
      </p>
    </AuthShell>
  );
};
