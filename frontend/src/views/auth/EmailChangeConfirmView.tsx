import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AuthShell, AuthNote } from './AuthShell';
import { authService } from '../../services/apiServices';
import { useAuthStore } from '../../stores/authStore';
import { ApiError } from '../../services/apiClient';

/** /settings/confirm-email?token=… — complete an email change. */
export const EmailChangeConfirmView: React.FC = () => {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const { fetchMe } = useAuthStore();
  const [state, setState] = useState<'working' | 'done' | 'failed'>('working');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setState('failed');
      setMessage('This page needs the confirmation link from your email.');
      return;
    }
    authService
      .confirmEmailChange(token)
      .then(async (res) => {
        setState('done');
        setMessage(res.message || 'Your sign-in email has been updated.');
        await fetchMe();
      })
      .catch((err) => {
        setState('failed');
        setMessage((err as ApiError)?.message || 'This confirmation link could not be used.');
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <AuthShell
      eyebrow="Email change"
      title={state === 'done' ? 'Email updated' : state === 'failed' ? 'Link not usable' : 'Confirming…'}
      tone={state === 'done' ? 'success' : state === 'failed' ? 'danger' : 'neutral'}
    >
      {state === 'working' && <AuthNote>Confirming your new address…</AuthNote>}
      {state === 'done' && <AuthNote tone="success">{message}</AuthNote>}
      {state === 'failed' && <AuthNote tone="error">{message}</AuthNote>}
      <Link to="/" className="block text-center text-[#C5A059] hover:underline">Continue to CONFIT →</Link>
    </AuthShell>
  );
};
