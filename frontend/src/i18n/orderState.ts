/**
 * Backend machine state → localized copy (2026-09-23).
 *
 * The rule this file exists to enforce (audit prompt §26): «كل machine state
 * يجب أن يتحول إلى localized copy. لا تعرض backend English diagnostic message
 * مباشرة كواجهة مستخدم.» — the post-purchase surface violated it. The tracking
 * view rendered raw enum values straight into the page:
 *
 *     {timeline.current_status.replace(/_/g, ' ')}      // "pending_delivery"
 *     ... {order.payment_method} · payment {order.payment_status}
 *
 * so an Arabic shopper read English machine tokens, and no gate could see it:
 * the i18n ratchet scans for literal English *sentences*, and a `.replace()`
 * on a runtime value is invisible to it.
 *
 * Keys are written as literals in these maps (not built by interpolation) so a
 * human can review the full state space, and a test can assert that every
 * backend state is covered in both locales. Unknown values deliberately fall
 * back to the raw token: inventing a label for a state this build does not know
 * would be a guess presented as product copy.
 */

/** Every state in `ORDER_TRANSITIONS` (backend/app/services/commerce_service.py). */
export const ORDER_STATUS_KEYS: Record<string, string> = {
  placed: 'order.status.placed',
  payment_pending: 'order.status.payment_pending',
  processing: 'order.status.processing',
  preparing: 'order.status.preparing',
  ready_for_pickup: 'order.status.ready_for_pickup',
  dispatched: 'order.status.dispatched',
  shipped: 'order.status.shipped',
  out_for_delivery: 'order.status.out_for_delivery',
  picked_up: 'order.status.picked_up',
  delivered: 'order.status.delivered',
  failed_delivery: 'order.status.failed_delivery',
  return_requested: 'order.status.return_requested',
  partially_returned: 'order.status.partially_returned',
  returned: 'order.status.returned',
  refund_pending: 'order.status.refund_pending',
  refunded: 'order.status.refunded',
  refund_failed: 'order.status.refund_failed',
  exchange_requested: 'order.status.exchange_requested',
  completed: 'order.status.completed',
  cancelled: 'order.status.cancelled',
  failed: 'order.status.failed',
  rejected: 'order.status.rejected',
};

/** Every value `order.payment_status` is assigned in commerce_service.py. */
export const PAYMENT_STATUS_KEYS: Record<string, string> = {
  pending: 'order.payment_status.pending',
  pending_delivery: 'order.payment_status.pending_delivery',
  authorized: 'order.payment_status.authorized',
  paid: 'order.payment_status.paid',
  credit_due: 'order.payment_status.credit_due',
  delta_due: 'order.payment_status.delta_due',
  refunded: 'order.payment_status.refunded',
  failed: 'order.payment_status.failed',
  not_required: 'order.payment_status.not_required',
};

/** Method ids from `PAYMENT_CATALOG` plus the paymob aliases the splitter accepts. */
export const PAYMENT_METHOD_KEYS: Record<string, string> = {
  card: 'order.payment_method.card',
  bnpl_tabby: 'order.payment_method.bnpl_tabby',
  bnpl_tamara: 'order.payment_method.bnpl_tamara',
  apple_pay: 'order.payment_method.apple_pay',
  google_pay: 'order.payment_method.google_pay',
  vodafone_cash: 'order.payment_method.vodafone_cash',
  instapay_bridge: 'order.payment_method.instapay_bridge',
  cod: 'order.payment_method.cod',
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

function localize(
  map: Record<string, string>,
  value: string | null | undefined,
  t: Translate,
): string {
  const raw = (value ?? '').trim();
  if (!raw) return t('order.state_unknown');
  const key = map[raw.toLowerCase()];
  // A state this build does not know keeps its raw token: showing the machine
  // truth beats showing a friendly label somebody invented.
  return key ? t(key) : raw.replace(/_/g, ' ');
}

export const localizeOrderStatus = (value: string | null | undefined, t: Translate) =>
  localize(ORDER_STATUS_KEYS, value, t);

export const localizePaymentStatus = (value: string | null | undefined, t: Translate) =>
  localize(PAYMENT_STATUS_KEYS, value, t);

export const localizePaymentMethod = (value: string | null | undefined, t: Translate) =>
  localize(PAYMENT_METHOD_KEYS, value, t);
