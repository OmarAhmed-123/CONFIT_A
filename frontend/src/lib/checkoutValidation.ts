/**
 * Pure, testable checkout submission validation (2026-09-06 remediation,
 * P0-01 follow-up). The old flow signalled EVERY problem through a transient
 * toast — guests who pressed "Place order" without an email saw an easy-to
 * -miss message and a button that appeared dead. This module returns a
 * machine-usable { field, message } so the view can highlight the exact
 * input, scroll it into view and set aria-invalid — while the same rules
 * remain enforced server-side.
 */

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
  message?: string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function isValidEmail(email: string): boolean {
  return EMAIL_RE.test(email.trim());
}

export function validateCheckoutSubmission(
  input: CheckoutSubmissionInput
): CheckoutValidationResult {
  if (input.itemsCount <= 0) {
    return { ok: false, field: 'cart', message: 'Your bag is empty.' };
  }
  if (!input.isAuthenticated) {
    const email = input.guestEmail.trim();
    if (!email) {
      return {
        ok: false,
        field: 'guest_email',
        message: 'Enter an email for guest checkout, or sign in.',
      };
    }
    if (!isValidEmail(email)) {
      return {
        ok: false,
        field: 'guest_email',
        message: 'That email address looks invalid — check it and try again.',
      };
    }
  }
  if (!input.recipientName.trim()) {
    return { ok: false, field: 'recipient_name', message: 'A recipient name is required.' };
  }
  if (!input.phone.trim()) {
    return { ok: false, field: 'phone', message: 'A contact phone number is required.' };
  }
  if (input.fulfillmentType === 'bopis' && !input.bopisStoreId) {
    return {
      ok: false,
      field: 'bopis_store',
      message: 'Select a boutique with stock for pickup.',
    };
  }
  if (input.fulfillmentType === 'delivery' && !input.addressLine.trim()) {
    return { ok: false, field: 'address', message: 'A delivery address is required.' };
  }
  return { ok: true };
}
