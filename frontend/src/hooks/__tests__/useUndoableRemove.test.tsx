/**
 * Spec 03 — undo-wardrobe. §10 required coverage:
 *   API success / failure / timeout · Undo before & after reload ·
 *   duplicate click · offline · screen reader · reduced motion.
 *
 * Structure:
 *   A. useUndoableRemove core (mocked UI store; the hook's whole contract)
 *   B. permanent-delete protection (useWardrobeViewModel guard)
 *   C. builder clear-canvas local undo (useOutfitBuilderViewModel)
 *   D. screen-reader semantics of the REAL Toast with an Undo action
 *   E. reduced-motion: the flow is fully functional with `reduce` set
 *
 * House rules honoured: no fake success before the server confirms; Undo is
 * offered ONLY when the server said `undoable: true`; restore failure is
 * reported honestly and followed by a refetch.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, renderHook, screen, act, waitFor, fireEvent } from '@testing-library/react';

import { useUndoableRemove, type UndoableRemoveOptions } from '../useUndoableRemove';
import { Toast } from '../../components/common/CommonComponents';

// ---------------------------------------------------------------------------
// Mocks. The UI store is replaced so every toast (message, type, action) is
// captured for assertion; apiServices is replaced so no network is touched.
// ---------------------------------------------------------------------------
const showToast = vi.fn();

vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({ showToast }),
}));

vi.mock('../../services/apiServices', () => ({
  wardrobeService: {
    getItems: vi.fn().mockResolvedValue([]),
    deleteItem: vi.fn(),
    restoreItem: vi.fn(),
  },
  moodBoardService: {},
  stylistService: {
    previewComposition: vi.fn().mockResolvedValue({ allowed: true }),
    checkCompatibility: vi.fn().mockResolvedValue({ score: 80 }),
    getOutfit: vi.fn(),
    deleteOutfit: vi.fn(),
  },
  catalogService: {
    getProductDetail: vi.fn(),
  },
}));

vi.mock('../../stores/cartStore', () => ({
  useCartStore: () => ({ addItem: vi.fn(), openCart: vi.fn() }),
}));

import { wardrobeService } from '../../services/apiServices';

/** Last toast captured, decomposed for readable assertions. */
const lastToast = () => {
  const call = showToast.mock.calls[showToast.mock.calls.length - 1];
  if (!call) throw new Error('no toast was shown');
  const [message, type, action] = call;
  return { message, type, action } as {
    message: { key: string; params?: Record<string, unknown> } | string;
    type: 'success' | 'error' | 'info' | undefined;
    action?: { i18nLabel: string; onAction: () => void } | null;
  };
};

const toastKey = (m: { key: string } | string) => (typeof m === 'string' ? m : m.key);

/** Minimal valid options for the hook; tests override what they probe. */
const makeOptions = (over: Partial<UndoableRemoveOptions> = {}): UndoableRemoveOptions & {
  spies: Record<'remove' | 'restore' | 'optimisticRemove' | 'rollback' | 'refetch', ReturnType<typeof vi.fn>>;
} => {
  const spies = {
    remove: vi.fn().mockResolvedValue({ undoable: true }),
    restore: vi.fn().mockResolvedValue({ status: 'restored' }),
    optimisticRemove: vi.fn(),
    rollback: vi.fn(),
    refetch: vi.fn().mockResolvedValue(undefined),
  };
  return {
    ...spies,
    messages: {
      removed: { key: 'toast.item_removed' },
      removeFailed: (reason: string) => ({ key: 'toast.item_delete_failed', params: { reason } }),
      restored: { key: 'toast.item_restored' },
      restoreFailed: (reason: string) => ({ key: 'toast.item_restore_failed', params: { reason } }),
      removedPermanently: { key: 'toast.item_deleted_permanently' },
    },
    ...over,
    spies,
  };
};

beforeEach(() => {
  vi.clearAllMocks();
});

// ===========================================================================
// A. useUndoableRemove — the shared contract
// ===========================================================================
describe('useUndoableRemove — API success', () => {
  it('optimistically removes, then offers Undo ONLY after the server confirms undoable', async () => {
    const { result } = renderHook(() => useUndoableRemove());
    const opts = makeOptions();

    await act(() => result.current(opts));

    expect(opts.spies.optimisticRemove).toHaveBeenCalledTimes(1);
    expect(opts.spies.remove).toHaveBeenCalledTimes(1);
    expect(opts.spies.rollback).not.toHaveBeenCalled();

    const t = lastToast();
    expect(toastKey(t.message)).toBe('toast.item_removed');
    expect(t.type).toBe('info');
    // The Undo affordance is real: label key + callable action.
    expect(t.action?.i18nLabel).toBe('a11y.undo_remove');
    expect(typeof t.action?.onAction).toBe('function');
  });

  it('does NOT offer Undo when the server says undoable: false (honest permanent delete)', async () => {
    const { result } = renderHook(() => useUndoableRemove());
    const opts = makeOptions({ remove: vi.fn().mockResolvedValue({ undoable: false }) });

    await act(() => result.current(opts));

    const t = lastToast();
    expect(toastKey(t.message)).toBe('toast.item_deleted_permanently');
    expect(t.action ?? null).toBeNull();
  });

  it('treats a MISSING undoable flag as not undoable (unknown fails safe)', async () => {
    const { result } = renderHook(() => useUndoableRemove());
    const opts = makeOptions({ remove: vi.fn().mockResolvedValue({}) });

    await act(() => result.current(opts));

    const t = lastToast();
    expect(toastKey(t.message)).toBe('toast.item_deleted_permanently');
    expect(t.action ?? null).toBeNull();
  });
});

describe('useUndoableRemove — API failure & timeout', () => {
  it('rolls the row back and shows the failure reason when the remove rejects', async () => {
    const { result } = renderHook(() => useUndoableRemove());
    const opts = makeOptions({ remove: vi.fn().mockRejectedValue({ detail: 'Server exploded' }) });

    await act(() => result.current(opts));

    expect(opts.spies.optimisticRemove).toHaveBeenCalledTimes(1);
    expect(opts.spies.rollback).toHaveBeenCalledTimes(1);

    const t = lastToast();
    expect(toastKey(t.message)).toBe('toast.item_delete_failed');
    expect((t.message as { params?: { reason?: string } }).params?.reason).toBe('Server exploded');
    expect(t.type).toBe('error');
    // A failed remove must never dangle an Undo button.
    expect(t.action ?? null).toBeNull();
  });

  it('timeout: claims nothing while pending, rolls back when the request finally dies', async () => {
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useUndoableRemove());
      // A remove that rejects only after 15s — the aborted-request shape.
      const remove = vi.fn(
        () =>
          new Promise<{ undoable?: boolean }>((_, reject) =>
            setTimeout(() => reject(new Error('Request timed out')), 15000),
          ),
      );
      const opts = makeOptions({ remove });

      let settled = false;
      act(() => {
        void result.current(opts).then(() => {
          settled = true;
        });
      });

      // While in flight: row hidden (removing state), but NO toast — neither
      // success nor failure has been invented ahead of the server.
      expect(opts.spies.optimisticRemove).toHaveBeenCalledTimes(1);
      expect(showToast).not.toHaveBeenCalled();
      expect(settled).toBe(false);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(15000);
      });

      expect(opts.spies.rollback).toHaveBeenCalledTimes(1);
      expect(toastKey(lastToast().message)).toBe('toast.item_delete_failed');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('useUndoableRemove — Undo', () => {
  it('Undo (before reload): calls the real restore endpoint, refetches, then reports restored', async () => {
    const { result } = renderHook(() => useUndoableRemove());
    const opts = makeOptions();

    await act(() => result.current(opts));
    const undo = lastToast().action!;

    await act(async () => {
      undo.onAction();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(opts.spies.restore).toHaveBeenCalledTimes(1);
      expect(opts.spies.refetch).toHaveBeenCalledTimes(1);
      expect(toastKey(lastToast().message)).toBe('toast.item_restored');
      expect(lastToast().type).toBe('success');
    });
  });

  it('Undo after the window closed (reload case): 404 from restore → refetch + honest failure, no fake row', async () => {
    const { result } = renderHook(() => useUndoableRemove());
    const opts = makeOptions({
      restore: vi.fn().mockRejectedValue({ detail: 'Restore window has passed' }),
    });

    await act(() => result.current(opts));
    const undo = lastToast().action!;

    await act(async () => {
      undo.onAction();
      await Promise.resolve();
    });

    await waitFor(() => {
      // The list is re-read from the server — reality, not a remembered snapshot.
      expect(opts.spies.refetch).toHaveBeenCalledTimes(1);
      const t = lastToast();
      expect(toastKey(t.message)).toBe('toast.item_restore_failed');
      expect((t.message as { params?: { reason?: string } }).params?.reason).toBe(
        'Restore window has passed',
      );
      expect(t.type).toBe('error');
    });
  });

  it('on reload the Undo offer is gone by construction (toast state is memory-only)', () => {
    // The snapshot and the Undo affordance live in the toast closure; nothing
    // is written to Web Storage, so a reload cannot resurrect a dead Undo.
    // This asserts the module keeps that property: no storage writes at all.
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');
    try {
      const { result } = renderHook(() => useUndoableRemove());
      const opts = makeOptions();
      return act(() => result.current(opts)).then(() => {
        expect(setItemSpy).not.toHaveBeenCalled();
      });
    } finally {
      setItemSpy.mockRestore();
    }
  });
});

describe('useUndoableRemove — duplicate click', () => {
  it('ignores a second click for the SAME key while the first remove is in flight', async () => {
    const { result } = renderHook(() => useUndoableRemove());
    let resolveRemove!: (v: { undoable?: boolean }) => void;
    const remove = vi.fn(
      () => new Promise<{ undoable?: boolean }>((res) => (resolveRemove = res)),
    );
    const opts = makeOptions({ remove, key: 42 });

    let first!: Promise<void>;
    act(() => {
      first = result.current(opts);
      void result.current(opts); // the double-tap
    });

    // One DELETE, one optimistic hide — the duplicate was a no-op.
    expect(remove).toHaveBeenCalledTimes(1);
    expect(opts.spies.optimisticRemove).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveRemove({ undoable: true });
      await first;
    });
    expect(toastKey(lastToast().message)).toBe('toast.item_removed');

    // After settling, the key is released: a NEW removal of the same id
    // (e.g. after an Undo) must work again.
    await act(() => result.current(makeOptions({ key: 42 })));
    expect(opts.spies.optimisticRemove).toHaveBeenCalledTimes(1); // old spy untouched
  });

  it('does NOT let item A block item B (per-key guard, not a global lock)', async () => {
    const { result } = renderHook(() => useUndoableRemove());
    const pending = new Promise<{ undoable?: boolean }>(() => {}); // A never settles
    const optsA = makeOptions({ remove: vi.fn().mockReturnValue(pending), key: 1 });
    const optsB = makeOptions({ key: 2 });

    act(() => {
      void result.current(optsA);
    });
    await act(() => result.current(optsB));

    expect(optsB.spies.remove).toHaveBeenCalledTimes(1);
    expect(toastKey(lastToast().message)).toBe('toast.item_removed');
  });
});

describe('useUndoableRemove — offline', () => {
  it('offline remove fails honestly: rollback + error, never a fake removed/undo toast', async () => {
    const onLineSpy = vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
    try {
      const { result } = renderHook(() => useUndoableRemove());
      // With no network the fetch layer rejects; the hook must not swallow
      // that into an optimistic "removed".
      const opts = makeOptions({ remove: vi.fn().mockRejectedValue(new TypeError('Failed to fetch')) });

      await act(() => result.current(opts));

      expect(opts.spies.rollback).toHaveBeenCalledTimes(1);
      const t = lastToast();
      expect(toastKey(t.message)).toBe('toast.item_delete_failed');
      expect(t.type).toBe('error');
      expect(t.action ?? null).toBeNull();
      // Exactly one toast: the error. No success was ever claimed.
      expect(showToast).toHaveBeenCalledTimes(1);
    } finally {
      onLineSpy.mockRestore();
    }
  });
});

// ===========================================================================
// B. permanent-delete protection (useWardrobeViewModel)
// ===========================================================================
import { useWardrobeViewModel } from '../../viewmodels/useWardrobeViewModel';

describe('permanent delete protection', () => {
  it('refuses permanent=true without explicit confirmation — no API call is made', async () => {
    const { result } = renderHook(() => useWardrobeViewModel());
    await act(async () => {}); // let the mount fetch settle
    vi.mocked(wardrobeService.deleteItem).mockClear();
    showToast.mockClear();

    await act(() => result.current.deleteItem(7, true /* permanent, NOT confirmed */));

    expect(wardrobeService.deleteItem).not.toHaveBeenCalled();
    const t = lastToast();
    expect(toastKey(t.message)).toBe('toast.permanent_delete_needs_confirm');
    expect(t.type).toBe('error');
  });

  it('allows permanent=true only together with explicit confirmation', async () => {
    const { result } = renderHook(() => useWardrobeViewModel());
    await act(async () => {});
    vi.mocked(wardrobeService.deleteItem).mockResolvedValue({
      status: 'deleted', permanent: true, undoable: false, item_id: 7,
    } as never);

    await act(() => result.current.deleteItem(7, true, true));

    expect(wardrobeService.deleteItem).toHaveBeenCalledWith(7, true);
  });

  it('default soft-delete path (the only one the UI uses) still works unchanged', async () => {
    const { result } = renderHook(() => useWardrobeViewModel());
    await act(async () => {});
    vi.mocked(wardrobeService.deleteItem).mockResolvedValue({
      status: 'deleted', permanent: false, undoable: true, item_id: 7,
    } as never);

    await act(() => result.current.deleteItem(7));

    expect(wardrobeService.deleteItem).toHaveBeenCalledWith(7, false);
    expect(toastKey(lastToast().message)).toBe('toast.item_removed');
  });
});

// ===========================================================================
// C. builder clear-canvas — safe LOCAL undo (memory-only state, no endpoint)
// ===========================================================================
import { useOutfitBuilderViewModel } from '../../viewmodels/useOutfitBuilderViewModel';
import type { Product } from '../../models';

const fakeProduct = (id: number): Product =>
  ({
    id,
    slug: `p-${id}`,
    title: `Product ${id}`,
    price: 100,
    category: 'Tops',
    skus: [{ id: id * 10, size: 'M', is_in_stock: true, stock_level: 3, price: 100 }],
  } as unknown as Product);

describe('builder clear canvas — local undo', () => {
  it('clearing a non-empty canvas offers Undo, and Undo restores the exact items', async () => {
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    act(() => {
      result.current.addItemToCanvas(fakeProduct(1), 'top');
      result.current.addItemToCanvas(fakeProduct(2), 'bottom');
    });
    expect(result.current.selectedItems).toHaveLength(2);
    showToast.mockClear();

    act(() => result.current.clearCanvas());

    expect(result.current.selectedItems).toHaveLength(0);
    const t = lastToast();
    expect(toastKey(t.message)).toBe('toast.canvas_cleared');
    expect((t.message as { params?: { count?: number } }).params?.count).toBe(2);
    expect(t.action?.i18nLabel).toBe('a11y.undo_remove');

    act(() => t.action!.onAction());

    expect(result.current.selectedItems.map((i) => i.product.id)).toEqual([1, 2]);
    await waitFor(() => expect(toastKey(lastToast().message)).toBe('toast.canvas_restored'));
  });

  it('clearing an EMPTY canvas is a silent no-op — no toast, no dangling Undo', () => {
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    showToast.mockClear();

    act(() => result.current.clearCanvas());

    expect(showToast).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// D. screen reader — the REAL Toast carrying an Undo action
// ===========================================================================
describe('screen reader semantics', () => {
  it('announces politely and exposes a named, 44px Undo control', async () => {
    const onAction = vi.fn();
    const onClose = vi.fn();
    render(
      <Toast
        message={{ key: 'toast.item_removed' }}
        type="info"
        onClose={onClose}
        action={{ label: 'Undo removal', onAction }}
      />,
    );

    // Announced as a polite status — a deletion confirmation must not steal
    // focus or interrupt (no role=alert / assertive for a reversible action).
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveAttribute('aria-atomic', 'true');

    // The Undo control has a real accessible name and the 44px floor.
    const undoBtn = screen.getByRole('button', { name: 'Undo removal' });
    expect(undoBtn.className).toContain('min-h-[44px]');
    expect(undoBtn.className).toContain('min-w-[44px]');

    // Dismiss control is separately named (not an unnamed ✕).
    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();

    // Activating Undo fires the action AND dismisses the toast.
    fireEvent.click(undoBtn);
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

// ===========================================================================
// E. reduced motion — the flow is identical with `prefers-reduced-motion`
// ===========================================================================
describe('reduced motion', () => {
  const originalMatchMedia = window.matchMedia;

  beforeEach(() => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it('remove → Undo → restore works end-to-end with reduce set (motion is CSS-only decoration)', async () => {
    // The repo disables animation globally via the prefers-reduced-motion
    // block in styles/index.css; nothing in the undo flow depends on an
    // animation callback, so the full cycle must behave identically.
    const { result } = renderHook(() => useUndoableRemove());
    const opts = makeOptions();

    await act(() => result.current(opts));
    const undo = lastToast().action!;
    await act(async () => {
      undo.onAction();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(opts.spies.restore).toHaveBeenCalledTimes(1);
      expect(opts.spies.refetch).toHaveBeenCalledTimes(1);
      expect(toastKey(lastToast().message)).toBe('toast.item_restored');
    });
  });

  it('the Toast still renders its content and controls under reduce', () => {
    render(
      <Toast
        message={{ key: 'toast.item_removed' }}
        onClose={() => {}}
        action={{ label: 'Undo removal', onAction: () => {} }}
      />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Undo removal' })).toBeInTheDocument();
  });
});
