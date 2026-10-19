import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  isOnboardingDismissed,
  dismissOnboarding,
  clearOnboardingDismissed,
} from '../authStore';

beforeEach(() => clearOnboardingDismissed());
afterEach(() => clearOnboardingDismissed());

describe('onboarding dismissal (session-scoped, G1 §23)', () => {
  it('defaults to not dismissed', () => {
    expect(isOnboardingDismissed()).toBe(false);
  });

  it('records a dismissal within the session', () => {
    dismissOnboarding();
    expect(isOnboardingDismissed()).toBe(true);
  });

  it('clears a dismissal (e.g. on logout / after completion)', () => {
    dismissOnboarding();
    clearOnboardingDismissed();
    expect(isOnboardingDismissed()).toBe(false);
  });
});
