import React, { useState } from 'react';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { ConfitLogo } from '../../components/common/ConfitLogo';
import { UserIcon } from '../../components/icons/ConfitIcons';

// Group 1 §14: demo-persona quick-login buttons are DEV-only. They are
// hard-gated on Vite's build-time constant so production bundles never
// contain either the buttons or the seeded passwords.
const IS_DEV = import.meta.env.DEV === true;

export const AuthModal: React.FC = () => {
  const { isAuthModalOpen, authModalMode, closeAuthModal, showToast } = useUIStore();
  const { login, register, isLoading, error, mfaRequired, completeMfaLogin } = useAuthStore();

  const [mode, setMode] = useState<'login' | 'register'>(authModalMode || 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [mfaCode, setMfaCode] = useState('');

  if (!isAuthModalOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (mode === 'login') {
        // Group 1 §11: two-step login. If the account has MFA, `login`
        // throws with reason=MFA_REQUIRED and the store flips a flag;
        // the second-step form below sends the code.
        await login(email, password);
        showToast('Welcome back to CONFIT!', 'success');
      } else {
        await register({ email, password, full_name: fullName, phone });
        showToast('Account created — complete your style profile to personalize CONFIT.', 'success');
      }
      closeAuthModal();
    } catch (err: any) {
      // MFA_REQUIRED is not an error, it's a state — do not close.
      if (err?.details?.reason !== 'MFA_REQUIRED') {
        // Error surfaced via `error` in the store.
      }
    }
  };

  const handleMfaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await completeMfaLogin(email, password, mfaCode);
      showToast('Signed in with MFA.', 'success');
      closeAuthModal();
    } catch (err: any) {
      // Error surfaced via `error` in the store.
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-150">
      <div className="w-full max-w-md bg-white rounded-3xl shadow-2xl overflow-hidden border border-slate-100">
        {/* Luxury Top Banner */}
        <div className="p-6 bg-[#0C0E1E] text-white flex justify-between items-center border-b border-slate-800">
          <ConfitLogo variant="compact" theme="light" size="md" />
          <button onClick={closeAuthModal} className="text-slate-400 hover:text-white text-sm">
            ✕
          </button>
        </div>

        {/* Development-only 1-Click Demo Persona Shortcuts */}
        {IS_DEV && (
          <div className="p-4 bg-[#FAF9F6] border-b border-slate-200/80 space-y-2">
            <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider block">
              Dev-only quick-login (never shipped to production):
            </span>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <button
                type="button"
                onClick={() => {
                  setEmail('shopper@confit.io');
                  setPassword('Password123!');
                  setMode('login');
                }}
                className="py-2 px-3 rounded-xl bg-white border border-slate-200 hover:border-[#C5A059] text-slate-800 font-semibold hover:bg-[#FDF8EE] transition-all text-left truncate shadow-2xs"
              >
                👤 Fill shopper creds
              </button>
              <button
                type="button"
                onClick={() => {
                  setEmail('brand@massimodutti.com');
                  setPassword('Password123!');
                  setMode('login');
                }}
                className="py-2 px-3 rounded-xl bg-white border border-slate-200 hover:border-[#C5A059] text-slate-800 font-semibold hover:bg-[#FDF8EE] transition-all text-left truncate shadow-2xs"
              >
                🏢 Fill brand creds
              </button>
            </div>
          </div>
        )}

        {/* MFA challenge (second step) */}
        {mfaRequired ? (
          <form onSubmit={handleMfaSubmit} className="p-6 space-y-4 text-xs">
            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs">
              Enter the 6-digit code from your authenticator app, or one of your single-use recovery codes.
            </div>
            {error && (
              <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 font-medium">
                {error}
              </div>
            )}
            <div>
              <label className="font-bold text-slate-700 block mb-1">MFA Code / Recovery Code</label>
              <input
                type="text"
                required
                autoFocus
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                placeholder="123456 or CONFIT-XXXX-XXXX"
                className="w-full p-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-[#C5A059] font-mono tracking-wider"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-bold text-xs shadow-md transition-all"
            >
              {isLoading ? 'Verifying…' : 'Verify & Sign In'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
            {error && (
              <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 font-medium">
                {error}
              </div>
            )}

            {mode === 'register' && (
              <div>
                <label className="font-bold text-slate-700 block mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Layla Al-Mansoor"
                  className="w-full p-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-[#C5A059]"
                />
              </div>
            )}

            <div>
              <label className="font-bold text-slate-700 block mb-1">Email Address</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
                className="w-full p-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-[#C5A059]"
              />
            </div>

            <div>
              <label className="font-bold text-slate-700 block mb-1">Password</label>
              <input
                type="password"
                required
                minLength={mode === 'register' ? 8 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === 'register' ? '8+ chars incl. 3 of upper/lower/digit/symbol' : '••••••••'}
                className="w-full p-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-[#C5A059]"
              />
              {mode === 'register' && (
                <p className="text-[10px] text-slate-400 mt-1">
                  Must be 8+ characters with at least 3 of: uppercase, lowercase, digit, symbol.
                </p>
              )}
            </div>

            {mode === 'register' && (
              <div>
                <label className="font-bold text-slate-700 block mb-1">Phone (optional)</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+971 50 123 4567"
                  className="w-full p-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-[#C5A059]"
                />
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-1.5"
            >
              <UserIcon size={14} color="#FFFFFF" />
              <span>{isLoading ? 'Processing...' : mode === 'login' ? 'Sign In' : 'Create Account'}</span>
            </button>

            <div className="text-center pt-2 text-slate-500">
              {mode === 'login' ? (
                <span>
                  New to CONFIT?{' '}
                  <button
                    type="button"
                    onClick={() => setMode('register')}
                    className="text-[#C5A059] font-bold hover:underline"
                  >
                    Create an Account
                  </button>
                </span>
              ) : (
                <span>
                  Already have an account?{' '}
                  <button
                    type="button"
                    onClick={() => setMode('login')}
                    className="text-[#C5A059] font-bold hover:underline"
                  >
                    Sign In
                  </button>
                </span>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
