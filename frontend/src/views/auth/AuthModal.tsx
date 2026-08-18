import React, { useState } from 'react';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { ConfitLogo } from '../../components/common/ConfitLogo';
import { UserIcon } from '../../components/icons/ConfitIcons';

export const AuthModal: React.FC = () => {
  const { isAuthModalOpen, authModalMode, closeAuthModal, showToast } = useUIStore();
  const { login, register, isLoading, error } = useAuthStore();

  const [mode, setMode] = useState<'login' | 'register'>(authModalMode || 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');

  if (!isAuthModalOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (mode === 'login') {
        await login(email, password);
        showToast('Welcome back to CONFIT!', 'success');
      } else {
        await register({ email, password, full_name: fullName, phone });
        showToast('Account created successfully!', 'success');
      }
      closeAuthModal();
    } catch (err: any) {
      // Error handled in store
    }
  };

  const handleQuickLogin = (demoEmail: string) => {
    login(demoEmail, 'Password123!')
      .then(() => {
        showToast(`Logged in as ${demoEmail}`, 'success');
        closeAuthModal();
      })
      .catch((err) => {
        showToast('Login failed: ' + err.message, 'error');
      });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-150">
      <div className="w-full max-w-md bg-white rounded-3xl shadow-2xl overflow-hidden border border-slate-100">
        {/* Luxury Top Banner with ConfitLogo */}
        <div className="p-6 bg-[#0C0E1E] text-white flex justify-between items-center border-b border-slate-800">
          <ConfitLogo variant="compact" theme="light" size="md" />
          <button onClick={closeAuthModal} className="text-slate-400 hover:text-white text-sm">
            ✕
          </button>
        </div>

        {/* 1-Click Demo Persona Shortcuts */}
        <div className="p-4 bg-[#FAF9F6] border-b border-slate-200/80 space-y-2">
          <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider block">
            1-Click Demo Persona Access:
          </span>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <button
              onClick={() => handleQuickLogin('shopper@confit.io')}
              className="py-2 px-3 rounded-xl bg-white border border-slate-200 hover:border-[#C5A059] text-slate-800 font-semibold hover:bg-[#FDF8EE] transition-all text-left truncate shadow-2xs"
            >
              👤 Shopper (Layla)
            </button>
            <button
              onClick={() => handleQuickLogin('brand@massimodutti.com')}
              className="py-2 px-3 rounded-xl bg-white border border-slate-200 hover:border-[#C5A059] text-slate-800 font-semibold hover:bg-[#FDF8EE] transition-all text-left truncate shadow-2xs"
            >
              🏢 Brand Manager
            </button>
          </div>
        </div>

        {/* Auth Form */}
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
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full p-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-[#C5A059]"
            />
          </div>

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
      </div>
    </div>
  );
};
