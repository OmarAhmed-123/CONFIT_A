import React, { useEffect } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { AppRoutes } from './router/AppRoutes';
import { queryClient, clearUserQueries, clearQueryCacheOnLogout } from './lib/queryClient';
import { useAuthStore } from './stores/authStore';
import './i18n/i18n';

export const App: React.FC = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);

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
      <AppRoutes />
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
};
