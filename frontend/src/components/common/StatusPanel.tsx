import React from "react";
import { Clock3, Mail } from "lucide-react";
import { StatusIcon } from "./InteractionPrimitives";

/**
 * StatusPanel — the result surface for a submitted form.
 *
 * WHY THIS EXISTS
 * ---------------
 * The public partner gateway (B01) collapsed every outcome into two buckets.
 * Measured in the code before this component:
 *
 *   · a DUPLICATE lead rendered in the SUCCESS (emerald) style, because both
 *     branches of the response handler set `type: "success"`. "We already
 *     have a recent request for this email" is not a success — painting it
 *     green tells the prospect their second submission worked;
 *   · network failure, HTTP 422 validation, HTTP 429 rate-limit and HTTP 503
 *     all fell into ONE `catch` and rendered the same rose box, although each
 *     demands a different action from the user.
 *
 * This gives four honest tones with four different affordances:
 *
 *   success   → the request landed; shows the reference number.
 *   notice    → nothing new happened (duplicate). Neutral, never green.
 *   error     → actionable retry, or fix a field.
 *   throttled → the 5/hour ceiling was hit. Retrying cannot help, so the
 *               panel must NOT offer retry — it offers email instead.
 *
 * FUNCTIONAL
 *   · `tone` selects semantics, icon and (for throttled) the escape action;
 *   · `reference` renders the server-assigned lead id, which the previous
 *     implementation received from `PartnerLeadOut.id` and discarded;
 *   · `action` renders the alternate channel (mailto:) for throttled.
 * NON-FUNCTIONAL
 *   · `role="alert"` on error and throttled only — those interrupt. success
 *     and notice use `role="status"` so they do not shout over the user;
 *   · colour is never the only channel: every tone carries an icon SHAPE and
 *     a text label, per spec 14 §8;
 *   · the panel reserves no fixed height, but it renders inside a container
 *     that does, so appearing never shifts the submit button.
 */

export type StatusTone = "success" | "notice" | "error" | "throttled";

export interface StatusPanelProps {
  tone: StatusTone;
  /** Primary line. */
  message: string;
  /** Server-assigned lead reference, e.g. "CONFIT-1234". */
  reference?: string;
  /** Secondary explanatory line. */
  detail?: string;
  /** Escape affordance — used by `throttled` to offer email instead of retry. */
  action?: { label: string; href: string };
  "data-testid"?: string;
}

const TONE: Record<
  StatusTone,
  { box: string; text: string; role: "alert" | "status" }
> = {
  success: {
    box: "border-emerald-300 bg-emerald-50",
    text: "text-emerald-900",
    role: "status",
  },
  notice: {
    box: "border-slate-300 bg-slate-50",
    text: "text-slate-800",
    role: "status",
  },
  error: {
    box: "border-rose-300 bg-rose-50",
    text: "text-rose-900",
    role: "alert",
  },
  throttled: {
    box: "border-amber-300 bg-amber-50",
    text: "text-amber-900",
    role: "alert",
  },
};

/** Shape-per-tone. `success`/`error` reuse the shared StatusIcon glyphs so a
 *  button, a toast and this panel speak one status language; `notice` and
 *  `throttled` need shapes the shared five do not cover. */
const ToneIcon: React.FC<{ tone: StatusTone }> = ({ tone }) => {
  if (tone === "success") return <StatusIcon status="success" size={16} />;
  if (tone === "error") return <StatusIcon status="error" size={16} />;
  if (tone === "notice")
    return <Clock3 size={16} aria-hidden="true" className="shrink-0 text-slate-500" />;
  return <Mail size={16} aria-hidden="true" className="shrink-0 text-amber-700" />;
};

export const StatusPanel: React.FC<StatusPanelProps> = ({
  tone,
  message,
  reference,
  detail,
  action,
  "data-testid": dataTestId,
}) => {
  const t = TONE[tone];
  return (
    <div
      role={t.role}
      aria-live={t.role === "alert" ? "assertive" : "polite"}
      data-tone={tone}
      data-testid={dataTestId}
      className={`flex items-start gap-3 rounded-[14px] border p-4 ${t.box} ${t.text}`}
    >
      <span className="mt-0.5 shrink-0">
        <ToneIcon tone={tone} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold leading-snug">{message}</p>

        {reference && (
          /* The reference is a Latin identifier: keep it LTR inside an Arabic
             sentence, and tabular so it does not jitter. */
          <p className="mt-1 text-xs font-medium opacity-90">
            <span className="tabular-nums" dir="ltr">
              {reference}
            </span>
          </p>
        )}

        {detail && <p className="mt-1 text-xs leading-relaxed opacity-80">{detail}</p>}

        {action && (
          <a
            href={action.href}
            className="mt-2 inline-flex min-h-[48px] items-center text-xs font-bold underline underline-offset-4 transition-opacity duration-[140ms] ease-luxury hover:opacity-70"
          >
            {action.label}
          </a>
        )}
      </div>
    </div>
  );
};

export default StatusPanel;
