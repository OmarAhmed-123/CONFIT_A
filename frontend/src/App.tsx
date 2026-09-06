import React, { useEffect } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { BrowserRouter } from 'react-router-dom';
import { AppRoutes } from './router/AppRoutes';
import { queryClient, clearUserQueries, clearQueryCacheOnLogout } from './lib/queryClient';
import { useAuthStore } from './stores/authStore';
import { useUIStore } from './stores/uiStore';
import { AuthModal } from './views/auth/AuthModal';
import { Toast } from './components/common/CommonComponents';
import './i18n/i18n';

export const App: React.FC = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const toast = useUIStore((s) => s.toast);
  const hideToast = useUIStore((s) => s.hideToast);

  // AUTH-02 FIX: session bootstrap runs ONCE at the application root — not
  // inside ConsumerLayout. /b2b and /admin render through BrandLayout, which
  // never restored the session, so a signed-in user hitting those routes
  // directly was treated as a guest (and the gate's Sign In button opened a
  // modal that was never mounted). Restoring the session here means every
  // layout (consumer, B2B, admin, shared looks) starts from the same
  // server-verified identity.
  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  // C22 FIX: Clear user-specific cache on logout/auth transition to prevent leakage
  useEffect(() => {
    if (!isAuthenticated) {
      clearUserQueries();
    }
  }, [isAuthenticated, user?.id]);

  // Also clear on user change (different user logging in)
  useEffect(() => {
    const currentUserId = user?.id;
    return () => {
      // Cleanup when user changes - will be called before new user effect
      if (currentUserId) {
        clearUserQueries();
      }
    };
  }, [user?.id]);

  return (
    <QueryClientProvider client={queryClient}>
      {/* AUTH-02 FIX: the Router lives at the app root (not inside AppRoutes)
          so root-mounted chrome — the AuthModal's post-login role landing —
          can use navigate(). Previously <AuthModal /> crashed with
          "useNavigate() may be used only in the context of a <Router>". */}
      <BrowserRouter>
        <AppRoutes />
        <AuthModal />
        {toast && <Toast message={toast.message} type={toast.type} onClose={hideToast} />}
      </BrowserRouter>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
};
