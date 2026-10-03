import { useCallback, useRef } from 'react';
import { useUIStore } from '../stores/uiStore';
import type { TranslatableMessage } from '../i18n/messages';

/**
 * ONE undoable-remove flow, shared by `/wardrobe`, `/builder` and `/my-looks`.
 *
 * WHY A HOOK AND NOT THREE COPIES
 * There are three call sites that delete something a shopper can regret:
 * a wardrobe item, a saved look in `useMyLooksViewModel`, and a saved look on
 * `WardrobeView`. Writing the optimistic-remove / toast / restore / rollback
 * dance in each one guarantees they drift: one forgets the rollback, one
 * announces a success the server never confirmed, one keeps a 4s window while
 * the others use 9s. The user sees a single product, so the behaviour is
 * defined once.
 *
 * THE RULES IT ENFORCES, from the Undo specification:
 *
 *  - OPTIMISTIC ONLY WHERE THE SERVER CAN REVERSE IT. Both backing endpoints
 *    soft-delete (migrations 0030/0031) and expose a real restore route. The
 *    caller passes `restore`; there is no local-only "undo".
 *  - NEVER CLAIM A LOCAL SUCCESS WHEN THE API FAILED. `remove` rejecting
 *    triggers `rollback` and an error toast; the Undo affordance is only
 *    offered after the server confirms `undoable`.
 *  - UNDO MUST NOT LIE. If `restore` rejects (window elapsed, item purged,
 *    offline) the UI says so and refetches, rather than leaving a row that
 *    is not really there.
 *  - RECOVER BY REFETCHING, not by re-inserting a remembered snapshot. The
 *    server owns order and content; a stale snapshot is how a list grows a
 *    ghost row after a concurrent edit.
 *
 * Returns a stable callback; the caller supplies only what differs.
 */
export interface UndoableRemoveOptions {
  /**
   * Server-side remove, resolving to the delete contract.
   *
   * `undoable` is typed OPTIONAL deliberately. zod's inferred type marks it
   * so, and rather than cast that away the hook treats a MISSING flag as
   * "not undoable": if the server did not positively say the delete can be
   * reversed, offering an Undo button would be offering an affordance that
   * may not work. Unknown must fail safe, not fail silent.
   */
  remove: () => Promise<{ undoable?: boolean }>;
  /**
   * Identity of the thing being removed (spec 03 §10 "duplicate click").
   * While a remove for this key is in flight, further calls for the SAME
   * key are ignored: a double-tap must produce one DELETE, not a second
   * request that 404s and surfaces a misleading error toast. Omitting the
   * key keeps the old behaviour (no guard) for callers without identity.
   */
  key?: string | number;
  /** Server-side restore. Called only when the server said `undoable`. */
  restore: () => Promise<unknown>;
  /** Hide the row immediately (optimistic). */
  optimisticRemove: () => void;
  /** Undo the optimistic hide when `remove` fails. */
  rollback: () => void;
  /** Re-read from the server after a restore attempt, success or failure. */
  refetch: () => Promise<unknown> | unknown;
  messages: {
    removed: TranslatableMessage;
    removeFailed: (reason: string) => TranslatableMessage;
    restored: TranslatableMessage;
    restoreFailed: (reason: string) => TranslatableMessage;
    /** Shown when the server reports the delete was NOT reversible. */
    removedPermanently: TranslatableMessage;
  };
}

export function useUndoableRemove() {
  // Destructured, not selector-based: every existing view model in this
  // codebase reads the store as `const { showToast } = useUIStore()`, and the
  // suite's store mocks are written for that shape. A hook that reaches for
  // the store differently works in production and breaks every test that
  // mocks it — matching the house style is the cheaper correctness.
  const { showToast } = useUIStore();
  // One in-flight set per hook instance (i.e. per view). A Set, not a
  // boolean: removing item A must not block removing item B.
  const inFlight = useRef<Set<string | number>>(new Set());

  return useCallback(
    async (options: UndoableRemoveOptions) => {
      const { remove, restore, optimisticRemove, rollback, refetch, messages, key } = options;

      // Duplicate click: the first tap already owns this removal.
      if (key !== undefined && inFlight.current.has(key)) return;
      if (key !== undefined) inFlight.current.add(key);

      optimisticRemove();                                   // active -> removing
      let result: { undoable?: boolean };
      try {
        result = await remove();
      } catch (err: unknown) {
        rollback();                                         // -> error/rollback
        showToast(messages.removeFailed(errorReason(err)), 'error');
        return;
      } finally {
        if (key !== undefined) inFlight.current.delete(key);
      }

      if (result?.undoable !== true) {   // absent or false => no Undo offered
        // The server performed a permanent delete. Offering Undo here would
        // be an affordance that cannot work.
        showToast(messages.removedPermanently, 'info');
        return;
      }

      // -> removed / undo-available
      showToast(messages.removed, 'info', {
        i18nLabel: 'a11y.undo_remove',
        onAction: () => {
          void (async () => {
            try {
              await restore();                              // -> restored
              await refetch();
              showToast(messages.restored, 'success');
            } catch (err: unknown) {
              // The window may have closed or the row was purged. Refetch so
              // the list reflects reality, then say the Undo failed.
              await refetch();
              showToast(messages.restoreFailed(errorReason(err)), 'error');
            }
          })();
        },
      });
    },
    [showToast],
  );
}

/** Extract a human-usable reason without leaking an object into the UI. */
function errorReason(err: unknown): string {
  if (typeof err === 'string') return err;
  if (err && typeof err === 'object') {
    const anyErr = err as { message?: unknown; detail?: unknown };
    if (typeof anyErr.detail === 'string') return anyErr.detail;
    if (typeof anyErr.message === 'string') return anyErr.message;
  }
  return 'unknown error';
}
