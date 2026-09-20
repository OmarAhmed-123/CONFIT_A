import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AuthShell, AuthButton, AuthInput, AuthNote } from './AuthShell';
import { authService } from '../../services/apiServices';
import { ApiError } from '../../services/apiClient';

/** /reset-password?token=… — set a new password with the emailed token. */
export const ResetPasswordView: React.FC = () => {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError('Both password fields must match.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters and include 3 of: lowercase, uppercase, digit, symbol.');
      return;
    }
    setSubmitting(true);
    try {
      await authService.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(((err as ApiError)?.message) || 'This reset link could not be used.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!token) {
    return (
      <AuthShell eyebrow="Account recovery" title="Reset link required" tone="warning">
        <AuthNote tone="error">
          This page needs the one-time link from your reset email. Open the link again, or request a new one.
        </AuthNote>
        <Link to="/forgot-password" className="block text-center text-[#C5A059] hover:underline">
          Request a new reset link →
        </Link>
      </AuthShell>
    );
  }

  if (done) {
    return (
      <AuthShell eyebrow="Account recovery" title="Password updated" tone="success">
        <AuthNote tone="success">
          Your password was changed and every other session was signed out. Sign in with your new password.
        </AuthNote>
        <Link to="/" className="block text-center text-[#C5A059] hover:underline">Continue to sign in →</Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell eyebrow="Account recovery" title="Choose a new password">
      <form onSubmit={submit} className="space-y-3">
        <AuthInput
          label="New password"
          type={showPassword ? 'text' : 'password'}
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
        />
        <AuthInput
          label="Confirm new password"
          type={showPassword ? 'text' : 'password'}
          required
          minLength={8}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
        />
        <label className="flex items-center gap-2 text-[11px] text-slate-400">
          <input type="checkbox" checked={showPassword} onChange={(e) => setShowPassword(e.target.checked)} />
          Show passwords
        </label>
        {error && <AuthNote tone="error">{error}</AuthNote>}
        <AuthButton type="submit" disabled={submitting}>{submitting ? 'Updating…' : 'Update password'}</AuthButton>
      </form>
      <p className="text-[11px] text-slate-500">
        Policy: at least 8 characters with 3 of lowercase, uppercase, digit, symbol. The server enforces this
        independently of this form.
      </p>
    </AuthShell>
  );
};
