import React, { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { brandService } from "../../services/apiServices";
import { ApiError } from "../../services/apiClient";
import { Field } from "../../components/common/Field";
import { StatusPanel, type StatusTone } from "../../components/common/StatusPanel";
import { ActionButton } from "../../components/common/ActionButton";
import type { AsyncActionState } from "../../components/common/InteractionPrimitives";

/**
 * LeadForm — the public B2B partner-lead capture form (B01).
 *
 * WHAT WAS WRONG (all measured in the previous implementation, which lived
 * inside RoleGuard.tsx and has been replaced):
 *
 *  · Client validation did not match the server. The server rejects an email
 *    failing `^[^@\s]+@[^@\s]+\.[^@\s]+$` and any company/contact name under
 *    two characters (brand_controller.py:49-54); the client only set
 *    `required` + `type="email"`, so typing "x" in Company cost a full round
 *    trip to discover a two-character rule.
 *  · Every failure shared ONE catch: network drop, 422, 429 and 503 all
 *    rendered the same rose box with a retry affordance.
 *  · A duplicate lead rendered in the SUCCESS (emerald) style.
 *  · `PartnerLeadOut.id` came back from the server and was discarded, so the
 *    prospect left with no reference — and with nothing discouraging a
 *    re-submit that would burn the shared rate limit.
 *  · The 5-per-hour-per-IP ceiling was invisible until it fired.
 *  · Success cleared the form immediately, destroying what was submitted.
 *
 * FUNCTIONAL
 *  · mirrors the server's rules locally, so an invalid submit makes ZERO
 *    network requests;
 *  · four distinct outcomes — field error, 422, 429 (throttled), network —
 *    each with its own affordance;
 *  · 429 is now a real 429: the backend throttle was moved off
 *    ValidationDomainError (422) onto RateLimitExceededError, because a
 *    client cannot branch on a status the server shares with "bad email";
 *  · renders the server-assigned reference;
 *  · duplicate resolves to a neutral `notice`, never to success;
 *  · warns BEFORE the ceiling fires rather than after;
 *  · preserves the entered values through a failure.
 * NON-FUNCTIONAL
 *  · every control >= 48px (Field owns the floor, ActionButton gets it here);
 *  · ActionButton's label stack reserves the widest state label up front, so
 *    idle→pending→success cannot shift the layout;
 *  · focus is never dropped: ActionButton uses aria-disabled, never the
 *    disabled attribute, mid-flight.
 */

/** Mirrors brand_controller.py:51 exactly. Kept adjacent to the call site
 *  that depends on it so a server-side change has an obvious partner. */
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Mirrors the `len(...) < 2` check at brand_controller.py:53. */
const MIN_NAME_LENGTH = 2;

/** Ceiling enforced server-side: 5 per hashed IP per sliding hour. */
const IP_CEILING = 5;
/** Warn when this many have been sent from this browser. */
const WARN_AT = 4;
const COUNTER_KEY = "confit_partner_lead_sent";

/** Where a throttled prospect should go instead. Retrying cannot help. */
const PARTNERSHIPS_EMAIL = "partnerships@confit.app";

export interface LeadFormValues {
  company_name: string;
  contact_name: string;
  work_email: string;
  website: string;
  monthly_order_volume: string;
  message: string;
}

const EMPTY: LeadFormValues = {
  company_name: "",
  contact_name: "",
  work_email: "",
  website: "",
  monthly_order_volume: "",
  message: "",
};

type FieldKey = keyof LeadFormValues;

interface ResultState {
  tone: StatusTone;
  message: string;
  detail?: string;
  reference?: string;
  action?: { label: string; href: string };
}

/** Reads this browser's submission count. Returns 0 on any failure — a
 *  corrupt or blocked localStorage must never block the form. */
function readSentCount(): number {
  try {
    const raw = window.localStorage.getItem(COUNTER_KEY);
    const n = raw ? parseInt(raw, 10) : 0;
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch {
    return 0;
  }
}

function writeSentCount(n: number): void {
  try {
    window.localStorage.setItem(COUNTER_KEY, String(n));
  } catch {
    /* Private mode / disabled storage: the counter is a courtesy, the server
       remains the authority. Silently degrade rather than break submit. */
  }
}

export const LeadForm: React.FC = () => {
  const { t } = useTranslation();
  const [values, setValues] = useState<LeadFormValues>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [result, setResult] = useState<ResultState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sentCount, setSentCount] = useState<number>(() => readSentCount());
  // Synchronous single-flight guard. `submitting` is React STATE, so it only
  // reads true on the NEXT render: two activations inside one frame both saw
  // `submitting === false`, both passed ActionButton's pending guard, and both
  // fired a request. On this endpoint that is not a cosmetic duplicate — the
  // second one burns another of the five requests this network is allowed per
  // hour, and answers `duplicate: true`, which the panel then renders as
  // "we already have a recent request" over a form the user only sent once.
  // A ref is mutated in place, so the second call sees it immediately.
  // Proven by e2e_partner_gateway_goals.py G5.
  const inFlight = useRef(false);

  const set = useCallback(
    (key: FieldKey) => (value: string) => {
      setValues((prev) => ({ ...prev, [key]: value }));
      // Clearing a field's own error as the user edits it: leaving a stale
      // "required" message under a field that now has content is noise.
      setFieldErrors((prev) => (prev[key] ? { ...prev, [key]: undefined } : prev));
    },
    [],
  );

  const volumeOptions = useMemo(
    () => [
      { value: "", label: t("partner.volume_placeholder") },
      { value: "under_500", label: t("partner.volume_under_500") },
      { value: "500_5000", label: t("partner.volume_500_5000") },
      { value: "5000_plus", label: t("partner.volume_5000_plus") },
    ],
    [t],
  );

  /** Returns the first invalid field, or null. Mirrors the server rules. */
  const validate = useCallback((): Partial<Record<FieldKey, string>> => {
    const errs: Partial<Record<FieldKey, string>> = {};
    if (values.company_name.trim().length < MIN_NAME_LENGTH) {
      errs.company_name = t("partner.err_company");
    }
    if (values.contact_name.trim().length < MIN_NAME_LENGTH) {
      errs.contact_name = t("partner.err_contact");
    }
    if (!EMAIL_PATTERN.test(values.work_email.trim())) {
      errs.work_email = t("partner.err_email");
    }
    return errs;
  }, [values, t]);

  const submit = useCallback(async () => {
    if (inFlight.current) {
      return;
    }
    setResult(null);

    // 1. Local validation first — an invalid form must not spend a request.
    const errs = validate();
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      // Move focus to the first problem rather than leaving the user to hunt.
      const firstKey = (["company_name", "contact_name", "work_email"] as FieldKey[])
        .find((k) => errs[k]);
      if (firstKey) {
        document
          .querySelector<HTMLElement>(`[name="${firstKey}"]`)
          ?.focus({ preventScroll: false });
      }
      return;
    }
    setFieldErrors({});

    inFlight.current = true;
    setSubmitting(true);
    try {
      const res = await brandService.requestDemo({
        ...values,
        source_path: "/b2b",
      });

      const nextCount = sentCount + 1;
      setSentCount(nextCount);
      writeSentCount(nextCount);

      if (res.duplicate) {
        // NOT a success. Nothing new was created; an earlier lead was linked.
        setResult({
          tone: "notice",
          message: t("partner.duplicate_title"),
          detail: t("partner.duplicate_detail"),
          reference: `CONFIT-${res.id}`,
        });
      } else {
        setResult({
          tone: "success",
          message: t("partner.success_title"),
          detail: t("partner.success_detail"),
          reference: `CONFIT-${res.id}`,
        });
      }
      // Values are deliberately NOT cleared: the panel shows what was sent
      // and the reference, and "submit another" reveals the intact form.
    } catch (err) {
      // Four honest branches. Retrying is offered only where retry can help.
      if (err instanceof ApiError && err.status === 429) {
        setResult({
          tone: "throttled",
          message: t("partner.throttled_title"),
          detail: t("partner.throttled_detail"),
          action: {
            label: t("partner.throttled_action"),
            href: `mailto:${PARTNERSHIPS_EMAIL}`,
          },
        });
      } else if (err instanceof ApiError && err.status === 422) {
        // Well-formed transport, rejected content. Point at the fields rather
        // than repeating a server string the user cannot act on.
        setFieldErrors({
          work_email: t("partner.err_email"),
        });
        setResult({
          tone: "error",
          message: t("partner.error_title"),
          detail: t("partner.error_detail_validation"),
        });
      } else if (typeof navigator !== "undefined" && navigator.onLine === false) {
        // The request never left the device: that is neither a success nor a
        // server failure, and saying "try again" alone hides the real cause.
        setResult({
          tone: "error",
          message: t("partner.offline_title"),
          detail: t("partner.offline_detail"),
        });
      } else {
        setResult({
          tone: "error",
          message: t("partner.error_title"),
          detail: t("partner.error_detail_generic"),
        });
      }
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }, [validate, values, sentCount, t]);

  // Controlled ActionButton state: the form owns `submitting` because the
  // native submit event, not a click, drives it.
  const buttonState: AsyncActionState = submitting ? "pending" : "idle";

  const nearCeiling = sentCount >= WARN_AT && !result;

  return (
    <form
      id="partner-request"
      aria-labelledby="partner-request-title"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="flex flex-col gap-4 rounded-[20px] border border-slate-200 bg-white p-5 shadow-md sm:p-6"
      data-testid="lead-form"
    >
      <header className="flex flex-col gap-1">
        <h2
          id="partner-request-title"
          className="font-serif text-[1.375rem] font-bold leading-tight text-[#1B1F3B]"
        >
          {t("partner.form_title")}
        </h2>
        <p className="text-[0.8125rem] leading-relaxed text-slate-500">
          {t("partner.form_hint")}
        </p>
      </header>

      {/* Pre-emptive warning. The server ceiling is per hashed IP over a
          sliding hour, so everyone behind one NAT shares one budget — telling
          the prospect only after it fires leaves them at a dead end. */}
      {nearCeiling && (
        <StatusPanel
          tone="throttled"
          message={t("partner.throttle_warning")}
          detail={t("partner.throttle_warning_detail")}
          action={{
            label: t("partner.throttled_action"),
            href: `mailto:${PARTNERSHIPS_EMAIL}`,
          }}
          data-testid="lead-throttle-warning"
        />
      )}

      <Field
        name="company_name"
        label={t("partner.field_company")}
        value={values.company_name}
        onChange={set("company_name")}
        autoComplete="organization"
        required
        minLength={MIN_NAME_LENGTH}
        error={fieldErrors.company_name}
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          name="contact_name"
          label={t("partner.field_contact")}
          value={values.contact_name}
          onChange={set("contact_name")}
          autoComplete="name"
          required
          minLength={MIN_NAME_LENGTH}
          error={fieldErrors.contact_name}
        />
        <Field
          name="work_email"
          label={t("partner.field_email")}
          type="email"
          inputMode="email"
          value={values.work_email}
          onChange={set("work_email")}
          autoComplete="email"
          required
          error={fieldErrors.work_email}
        />
      </div>

      <Field
        name="website"
        label={t("partner.field_website")}
        type="url"
        inputMode="url"
        value={values.website}
        onChange={set("website")}
        autoComplete="url"
        optional
      />

      <Field
        name="monthly_order_volume"
        label={t("partner.field_volume")}
        as="select"
        value={values.monthly_order_volume}
        onChange={set("monthly_order_volume")}
        options={volumeOptions}
        optional
      />

      <Field
        name="message"
        label={t("partner.field_message")}
        as="textarea"
        rows={3}
        maxLength={600}
        counter
        value={values.message}
        onChange={set("message")}
        optional
      />

      {result && (
        <StatusPanel
          tone={result.tone}
          message={result.message}
          detail={result.detail}
          reference={result.reference}
          action={result.action}
          data-testid="lead-result"
        />
      )}

      <ActionButton
        type="submit"
        state={buttonState}
        labels={{
          idle: t("partner.submit"),
          pending: t("partner.submitting"),
          success: t("partner.submit"),
          error: t("partner.submit"),
        }}
        metricsId="b01_partner_lead_submit"
        className="min-h-[48px] w-full rounded-[14px] bg-[#1B1F3B] text-xs font-bold uppercase tracking-wider text-white transition-colors duration-[140ms] ease-luxury hover:bg-[#13162C] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44] focus-visible:ring-offset-2"
        data-testid="lead-submit"
      />
    </form>
  );
};

export default LeadForm;
