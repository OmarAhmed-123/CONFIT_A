import React from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { OnboardingGate } from '../AppRoutes';
import { useAuthStore, dismissOnboarding, clearOnboardingDismissed } from '../../stores/authStore';

// Shows the resolved location so a redirect is observable.
const Where: React.FC = () => {
  const loc = useLocation();
  return <output data-testid="where">{loc.pathname + loc.search}</output>;
};

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/discover"
          element={
            <OnboardingGate>
              <div>discover content</div>
            </OnboardingGate>
          }
        />
        <Route path="/profile" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );

const setUser = (onboarding_completed: boolean, has_profile = onboarding_completed) =>
  useAuthStore.setState({
    user: {
      id: 1,
      email: 'a@b.c',
      full_name: 'A',
      role: 'consumer',
      has_profile,
      onboarding_completed,
    } as never,
    isAuthenticated: true,
    isLoading: false,
    hasAttemptedBootstrap: true,
  });

beforeEach(() => {
  clearOnboardingDismissed();
  useAuthStore.setState({ user: null, isAuthenticated: false });
});
afterEach(() => clearOnboardingDismissed());

describe('OnboardingGate — G1 §23 first-run, dismissible (regression: wizard must not reappear)', () => {
  it('redirects an authenticated user WITHOUT a profile to the wizard host', () => {
    setUser(false);
    renderAt('/discover');
    expect(screen.getByTestId('where').textContent).toBe('/profile?onboarding=1');
  });

  it('does NOT redirect once onboarding is completed (the reported bug: no reappear after completion/refresh/re-login)', () => {
    setUser(true);
    renderAt('/discover');
    expect(screen.getByText('discover content')).toBeTruthy();
  });

  // PHASE 0.2 REGRESSION — the exact state that made the wizard reappear.
  // A profile row exists (the wizard saved one field, or a split PATCH landed)
  // but the wizard was never finished. The old gate read `has_profile` and
  // concluded "onboarded"; the server said otherwise and the wizard came back.
  it('STILL redirects when a profile row exists but onboarding was never completed', () => {
    setUser(false, true);
    renderAt('/discover');
    expect(screen.getByTestId('where').textContent).toBe('/profile?onboarding=1');
  });

  it('does not redirect a completed user even though has_profile is also true', () => {
    setUser(true, true);
    renderAt('/discover');
    expect(screen.getByText('discover content')).toBeTruthy();
  });

  it('treats a missing onboarding_completed field (cached old session) as not completed', () => {
    useAuthStore.setState({
      user: { id: 1, email: 'a@b.c', full_name: 'A', role: 'consumer', has_profile: true } as never,
      isAuthenticated: true,
      isLoading: false,
      hasAttemptedBootstrap: true,
    });
    renderAt('/discover');
    expect(screen.getByTestId('where').textContent).toBe('/profile?onboarding=1');
  });

  it('does NOT redirect after the user skips/dismisses onboarding (non-blocking across routes)', () => {
    setUser(false);
    dismissOnboarding();
    renderAt('/discover');
    expect(screen.getByText('discover content')).toBeTruthy();
  });

  it('ignores guests — the gate only applies to authenticated users', () => {
    useAuthStore.setState({ user: null, isAuthenticated: false });
    renderAt('/discover');
    expect(screen.getByText('discover content')).toBeTruthy();
  });
});
