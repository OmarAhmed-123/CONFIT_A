/**
 * Machine-state localization contract (2026-09-23).
 *
 * The defect: the post-purchase view rendered raw backend enums into the page
 * (`{timeline.current_status.replace(/_/g, ' ')}`, `payment {order.payment_status}`),
 * so an Arabic shopper read English machine tokens — "pending_delivery",
 * "credit_due". No existing gate could catch it: the i18n ratchet looks for
 * literal English sentences, and a `.replace()` on a runtime value is invisible
 * to a text scan.
 *
 * The fix moved the mapping into `orderState.ts` with the keys written as
 * literals, which makes the state space reviewable and testable. This test is
 * the drift guard: it fails when a state exists in the product but has no copy
 * in both locales.
 */
import { describe, it, expect } from 'vitest';

import en from '../en.json';
import ar from '../ar.json';
import {
  ORDER_STATUS_KEYS,
  PAYMENT_METHOD_KEYS,
  PAYMENT_STATUS_KEYS,
} from '../orderState';

type Tree = Record<string, unknown>;

function lookup(tree: Tree, dotted: string): unknown {
  return dotted
    .split('.')
    .reduce<unknown>((node, part) => {
      if (node && typeof node === 'object') return (node as Tree)[part];
      return undefined;
    }, tree);
}

const GROUPS: Array<[string, Record<string, string>]> = [
  ['order.status', ORDER_STATUS_KEYS],
  ['order.payment_status', PAYMENT_STATUS_KEYS],
  ['order.payment_method', PAYMENT_METHOD_KEYS],
];

describe('every backend machine state resolves to localized copy', () => {
  for (const [group, map] of GROUPS) {
    it(`${group}: each state has an en and an ar string`, () => {
      for (const [state, key] of Object.entries(map)) {
        const enValue = lookup(en as Tree, key);
        const arValue = lookup(ar as Tree, key);
        expect(typeof enValue, `${state} -> ${key} (en)`).toBe('string');
        expect(typeof arValue, `${state} -> ${key} (ar)`).toBe('string');
        expect((enValue as string).trim(), `${key} (en) is empty`).not.toBe('');
        expect((arValue as string).trim(), `${key} (ar) is empty`).not.toBe('');
        expect(key, `${state} maps to its own key, not another state's`).toBe(
          `${group}.${state}`,
        );
        expect(arValue, `${key} is an English fallback in Arabic`).not.toBe(enValue);
      }
    });
  }

  it('covers the full order state machine, not a convenient subset', () => {
    // Kept in sync with ORDER_TRANSITIONS; the Python drift test asserts this
    // list against the backend source, so a new state cannot be added silently.
    const backendStates = [
      'placed', 'payment_pending', 'processing', 'preparing', 'ready_for_pickup',
      'dispatched', 'shipped', 'out_for_delivery', 'picked_up', 'delivered',
      'failed_delivery', 'return_requested', 'partially_returned', 'returned',
      'refund_pending', 'refunded', 'refund_failed', 'exchange_requested',
      'completed', 'cancelled', 'failed', 'rejected',
    ];
    for (const state of backendStates) {
      expect(ORDER_STATUS_KEYS[state], `order status '${state}' has no mapping`).toBeTruthy();
    }
    expect(Object.keys(ORDER_STATUS_KEYS).sort()).toEqual([...backendStates].sort());
  });
});
