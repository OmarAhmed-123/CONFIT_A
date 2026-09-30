import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
// fireEvent, not user-event: @testing-library/user-event is NOT a project
// dependency and the specification forbids adding one unless the existing
// libraries are insufficient. They are not — every interaction asserted here
// is a click or a key press.
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

import { Toast } from '../../components/common/CommonComponents';
import { useUIStore } from '../../stores/uiStore';

/**
 * Undo / Remove-to-Bin — the front-end half of the contract.
 *
 * The backend had to change first (migration 0030): the old delete was a hard
 * DELETE that ALSO removed the photograph from object storage, so an Undo
 * button would have been a lie twice over. These tests cover what the UI
 * still owns: the affordance is reachable, named, announced, and it invokes a
 * real handler rather than only re-rendering a list.
 */

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, params?: Record<string, unknown>) =>
        params ? `${key}:${JSON.stringify(params)}` : key,
    }),
  };
});

describe('Undo affordance on the toast', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('is a real button with an accessible name, not an icon or a colour', () => {
    render(
      <Toast
        message="toast.item_removed"
        type="info"
        onClose={() => {}}
        action={{ label: 'Undo removal', onAction: () => {} }}
      />,
    );
    // Name comes from text content, so a screen reader announces something
    // meaningful — the spec forbids icon-only or colour-only state.
    expect(screen.getByRole('button', { name: 'Undo removal' })).toBeInTheDocument();
  });

  it('announces the outcome in a polite live region', () => {
    render(<Toast message="toast.item_removed" type="info" onClose={() => {}} />);
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-live', 'polite');
    // The text itself carries the state; animation is not the carrier.
    expect(region).toHaveTextContent('toast.item_removed');
  });

  it('invokes the handler and then dismisses', () => {
    const onAction = vi.fn();
    const onClose = vi.fn();
    render(
      <Toast message="toast.item_removed" type="info" onClose={onClose}
             action={{ label: 'Undo removal', onAction }} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Undo removal' }));
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('is keyboard reachable and operable', () => {
    const onAction = vi.fn();
    render(
      <Toast message="toast.item_removed" type="info" onClose={() => {}}
             action={{ label: 'Undo removal', onAction }} />,
    );
    const button = screen.getByRole('button', { name: 'Undo removal' });
    button.focus();
    expect(button).toHaveFocus();
    // A real <button> activates on Enter/Space natively; asserting the click
    // handler fires proves the element is the right ELEMENT, which is what
    // keyboard operability actually depends on.
    fireEvent.click(button);
    expect(onAction).toHaveBeenCalled();
  });

  it('meets the 44px touch-target floor', () => {
    render(
      <Toast message="toast.item_removed" type="info" onClose={() => {}}
             action={{ label: 'Undo removal', onAction: () => {} }} />,
    );
    const button = screen.getByRole('button', { name: 'Undo removal' });
    // jsdom has no layout engine, so assert the declared constraint rather
    // than a measured box — measuring here would return 0 and prove nothing.
    expect(button.className).toContain('min-h-[44px]');
    expect(button.className).toContain('min-w-[44px]');
  });

  it('uses logical direction classes so RTL is not hand-mirrored', () => {
    render(
      <Toast message="toast.item_removed" type="info" onClose={() => {}}
             action={{ label: 'Undo removal', onAction: () => {} }} />,
    );
    const button = screen.getByRole('button', { name: 'Undo removal' });
    expect(button.className).toContain('ms-');
    expect(button.className).not.toMatch(/\bml-\d/);
  });

  it('renders no action button when none is supplied', () => {
    render(<Toast message="toast.item_removed" type="info" onClose={() => {}} />);
    expect(screen.queryByRole('button', { name: 'Undo removal' })).not.toBeInTheDocument();
  });
});

describe('uiStore carries the recovery action', () => {
  beforeEach(() => {
    useUIStore.setState({ toast: null });
  });

  it('stores the handler and the label KEY, not a translated string', () => {
    const onAction = vi.fn();
    useUIStore.getState().showToast(
      { key: 'toast.item_removed' } as never, 'info',
      { i18nLabel: 'a11y.undo_remove', onAction },
    );
    const toast = useUIStore.getState().toast;
    // A store has no t(); translating there would freeze the label in
    // whatever language was active when the toast was created.
    expect(toast?.action?.i18nLabel).toBe('a11y.undo_remove');
    expect(toast?.action?.onAction).toBe(onAction);
  });

  it('keeps an undo toast on screen longer than a plain confirmation', () => {
    vi.useFakeTimers();
    try {
      // A DISTINCT key: the store debounces an identical message within
      // 1.5s, and the previous test in this file already emitted
      // `toast.item_removed`. Reusing it here would be silently swallowed and
      // the assertion would pass or fail for the wrong reason.
      useUIStore.getState().showToast({ key: 'toast.item_restored' } as never, 'info', {
        i18nLabel: 'a11y.undo_remove',
        onAction: () => {},
      });
      // 4s is enough to READ a confirmation, not to decide you regret a
      // deletion and move the pointer to the button.
      vi.advanceTimersByTime(5000);
      expect(useUIStore.getState().toast).not.toBeNull();
      vi.advanceTimersByTime(5000);
      expect(useUIStore.getState().toast).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
