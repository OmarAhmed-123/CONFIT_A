import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { ConfitLogo } from '../common/ConfitLogo';
import { LockIcon, UserIcon, ShieldIcon } from '../icons/ConfitIcons';

interface RoleGuardProps {
  allowedRoles?: string[];
  children?: React.ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
}

export const RoleGuard: React.FC<RoleGuardProps> = ({
  allowedRoles,
  children,
  fallbackTitle,
  fallbackMessage,
}) => {
  const location = useLocation();
  const { user, isAuthenticated } = useAuthStore();
  const { openAuthModal } = useUIStore();

  // 1. Not Authenticated -> Show Luxury Authentication Required Gate
  if (!isAuthenticated || !user) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-[#0C0E1E] text-white border border-[#C5A059]/40 rounded-3xl p-8 shadow-2xl text-center space-y-6 animate-in fade-in zoom-in-95 duration-200">
          <div className="w-16 h-16 rounded-2xl bg-[#1B1F3B] border border-[#C5A059]/50 mx-auto flex items-center justify-center text-[#C5A059] shadow-lg">
            <LockIcon size={32} color="#C5A059" />
          </div>

          <div className="space-y-2">
            <span className="text-[10px] font-bold tracking-widest text-[#C5A059] uppercase">
              CONFIT Access Governance
            </span>
            <h2 className="font-serif text-2xl font-bold text-white">
              {fallbackTitle || 'Authentication Required'}
            </h2>
            <p className="text-xs text-slate-400 font-light leading-relaxed">
              {fallbackMessage ||
                'This privileged section requires an authenticated luxury profile or merchant credential. Please sign in or create an account to proceed.'}
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <button
              onClick={() => openAuthModal('login')}
              className="w-full py-3.5 rounded-xl bg-[#C5A059] hover:bg-[#E2BF70] text-[#0C0E1E] font-bold text-xs tracking-wider uppercase shadow-md transition-all flex items-center justify-center gap-2"
            >
              <UserIcon size={16} color="#0C0E1E" />
              <span>Sign In to Continue</span>
            </button>

            <button
              onClick={() => openAuthModal('register')}
              className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 text-white font-semibold text-xs border border-slate-700 transition-all"
            >
              Create New Account
            </button>

            <div className="pt-2">
              <Link
                to="/"
                className="text-[11px] text-slate-400 hover:text-[#C5A059] transition-colors inline-block"
              >
                ← Return to Consumer Storefront
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 2. Role Verification
  const userRole = user.role?.toLowerCase();
  const hasRole = !allowedRoles || allowedRoles.includes(userRole) || userRole === 'admin';

  if (!hasRole) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-[#0C0E1E] text-white border border-rose-500/40 rounded-3xl p-8 shadow-2xl text-center space-y-6 animate-in fade-in duration-200">
          <div className="w-16 h-16 rounded-2xl bg-rose-950/60 border border-rose-500/50 mx-auto flex items-center justify-center text-rose-400 shadow-lg">
            <ShieldIcon size={32} color="#F43F5E" />
          </div>

          <div className="space-y-2">
            <span className="text-[10px] font-bold tracking-widest text-rose-400 uppercase">
              403 Forbidden · Role Restriction
            </span>
            <h2 className="font-serif text-2xl font-bold text-white">
              Access Restricted
            </h2>
            <p className="text-xs text-slate-400 font-light leading-relaxed">
              Your account (<strong className="text-white">{user.email}</strong>) is registered with the{' '}
              <span className="px-2 py-0.5 rounded bg-slate-800 text-[#C5A059] font-mono text-[11px]">
                {user.role}
              </span>{' '}
              role. This portal requires one of the following permissions:{' '}
              <span className="text-slate-300 font-medium">
                {allowedRoles?.join(', ')}
              </span>.
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <Link
              to="/"
              className="w-full py-3.5 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 text-white font-bold text-xs border border-slate-700 tracking-wider uppercase shadow-md transition-all flex items-center justify-center gap-2"
            >
              <span>← Return to Consumer Storefront</span>
            </Link>

            <button
              onClick={() => openAuthModal('login')}
              className="w-full py-2.5 rounded-xl text-xs text-[#C5A059] hover:underline"
            >
              Switch Account / Re-authenticate
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 3. Authorized -> Render Protected Content
  return <>{children}</>;
};

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return <RoleGuard>{children}</RoleGuard>;
};
