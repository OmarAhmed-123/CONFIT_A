/**
 * Pure, testable checkout submission validation (2026-09-06 remediation,
 * P0-01 follow-up). The old flow signalled EVERY problem through a transient
 * toast — guests who pressed "Place order" without an email saw an easy-to
 * -miss message and a button that appeared dead. This module returns a
 * machine-usable { field, message } so the view can highlight the exact
 * input, scroll it into view and set aria-invalid — while the same rules
 * remain enforced server-side.
 *
 * i18n (audit 2026-09-21): `message` is a TranslatableMessage, not an English
 * sentence. This module is pure — it has no React context and no translator —
 * so it now returns a KEY and the view resolves it in the active language.
 * Previously an Arabic checkout showed English validation errors.
 */
import { msg, type TranslatableMessage } from '../i18n/messages';

export type CheckoutField =
  | 'cart'
  | 'guest_email'
  | 'bopis_store'
  | 'address'
  | 'recipient_name'
  | 'phone';

export interface CheckoutSubmissionInput {
  isAuthenticated: boolean;
  itemsCount: number;
  guestEmail: string;
  fulfillmentType: 'delivery' | 'bopis';
  bopisStoreId?: number | null;
  addressLine: string;
  recipientName: string;
  phone: string;
}

export interface CheckoutValidationResult {
  ok: boolean;
  field?: CheckoutField;
  message?: TranslatableMessage;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function isValidEmail(email: string): boolean {
  return EMAIL_RE.test(email.trim());
}

export function validateCheckoutSubmission(
  input: CheckoutSubmissionInput
): CheckoutValidationResult {
  if (input.itemsCount <= 0) {
    return { ok: false, field: 'cart', message: msg('errors.empty_bag') };
  }
  if (!input.isAuthenticated) {
    const email = input.guestEmail.trim();
    if (!email) {
      return {
        ok: false,
        field: 'guest_email',
        message: msg('errors.guest_email_required'),
      };
    }
    if (!isValidEmail(email)) {
      return {
        ok: false,
        field: 'guest_email',
        message: msg('errors.email_invalid'),
      };
    }
  }
  if (!input.recipientName.trim()) {
    return { ok: false, field: 'recipient_name', message: msg('errors.recipient_required') };
  }
  if (!input.phone.trim()) {
    return { ok: false, field: 'phone', message: msg('errors.phone_required') };
  }
  if (input.fulfillmentType === 'bopis' && !input.bopisStoreId) {
    return {
      ok: false,
      field: 'bopis_store',
      message: msg('errors.store_required'),
    };
  }
  if (input.fulfillmentType === 'delivery' && !input.addressLine.trim()) {
    return { ok: false, field: 'address', message: msg('errors.address_required') };
  }
  return { ok: true };
}
