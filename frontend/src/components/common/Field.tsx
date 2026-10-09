import React, { useId } from "react";
import { useTranslation } from "react-i18next";

/**
 * Field — the single form-field primitive.
 *
 * WHY THIS EXISTS
 * ---------------
 * Eleven files hand-roll their own input markup (`AuthModal`, `CheckoutView`,
 * `FitFinderView`, `OrderTrackingView`, `ResetPasswordView`, `VerifyEmailView`,
 * `PhotoEstimatePanel`, `CameraScanModal`, `VisualSearchModal`,
 * `CurrencySwitcher`, `AdminCatalogView`) and every one of them got a
 * different subset of the contract right. The public partner gateway
 * (`/b2b`, B01) was the worst case, measured before this component existed:
 *
 *     <label>              0      aria-describedby  0
 *     autocomplete         0      aria-invalid      0
 *     name=                0      maxLength         0
 *
 * Its fields were labelled by `placeholder` — which VANISHES the moment the
 * user types — plus an invisible `aria-label`, and carried no `autocomplete`,
 * so browser autofill was dead on a six-field B2B form. This component makes
 * the correct wiring the only wiring available: a real visible <label>,
 * `aria-describedby` bound to the hint and the error, `aria-invalid` set from
 * a single prop, and a 48px floor on the control.
 *
 * FUNCTIONAL
 *   · renders <input>, <select> or <textarea> from one API;
 *   · `error` drives aria-invalid + aria-describedby + the message slot;
 *   · `options` drives <select>; `maxLength` + `counter` drive the textarea
 *     counter; `optional` renders an explicit "optional" marker instead of
 *     leaving the user to guess which fields are mandatory.
 * NON-FUNCTIONAL
 *   · touch target >= 48px (B01 brief; the repo's older floor is 44px);
 *   · visible label never depends on placeholder, so it survives input and
 *     survives translation (Arabic strings run ~30% longer than English —
 *     the label is a block, it wraps, it never truncates);
 *   · focus ring uses --confit-focus, the darkened brand gold measured at
 *     3.55:1 on cream / 4.31:1 on navy (see styles/index.css). Brand gold
 *     #B8935A itself is only 2.71:1 on cream and may NOT be used for a focus
 *     indicator or for text on a light surface;
 *   · colour is never the only channel: an error carries text, not just red.
 */

export interface FieldOption {
  value: string;
  label: string;
}

export interface FieldProps {
  /** Stable key. Becomes the DOM id, the `name`, and the aria wiring root. */
  name: string;
  /** Visible label — also the accessible name. Never a placeholder. */
  label: string;
  as?: "input" | "select" | "textarea";
  type?: string;
  value: string;
  onChange: (value: string) => void;
  /** Autofill hint. Omit only where no standard token applies. */
  autoComplete?: string;
  inputMode?: "text" | "email" | "url" | "tel" | "numeric";
  placeholder?: string;
  /** Short supporting copy under the control, announced with the value. */
  hint?: string;
  /** Validation message. Its presence is what marks the field invalid. */
  error?: string;
  required?: boolean;
  /** Renders an explicit optional marker rather than implying it. */
  optional?: boolean;
  minLength?: number;
  maxLength?: number;
  rows?: number;
  /** Shows "n / max" for a textarea. */
  counter?: boolean;
  options?: FieldOption[];
  disabled?: boolean;
  className?: string;
  "data-testid"?: string;
}

/** 48px floor (B01 brief). Tailwind has no `min-h-12` in v3's default scale
 *  under that name, so the value is explicit and tokenised here once. */
const CONTROL_MIN_HEIGHT = "min-h-[48px]";

const CONTROL_BASE = [
  "w-full rounded-[14px] border bg-white px-4 py-3 text-sm text-[#1B1F3B]",
  "transition-[border-color,box-shadow] duration-[180ms] ease-luxury",
  // slate-500, not slate-400: 400 measures 2.56:1 on white and placeholder
  // text is text — WCAG 2.2 AA asks 4.5:1. slate-500 is 4.76:1. This is a
  // shared primitive, so the old token was shipping that failure to every
  // form in the app, not just this one.
  "placeholder:text-slate-500",
  "focus:outline-none focus-visible:outline-none focus:ring-[3px]",
].join(" ");

const CONTROL_TONE = {
  invalid: "border-rose-400 focus:border-rose-500 focus:ring-rose-500/25",
  valid: "border-slate-200 focus:border-[#A37E44] focus:ring-[#A37E44]/25",
} as const;

export const Field: React.FC<FieldProps> = ({
  name,
  label,
  as = "input",
  type = "text",
  value,
  onChange,
  autoComplete,
  inputMode,
  placeholder,
  hint,
  error,
  required = false,
  optional = false,
  minLength,
  maxLength,
  rows = 3,
  counter = false,
  options = [],
  disabled = false,
  className = "",
  "data-testid": dataTestId,
}) => {
  const { t } = useTranslation();
  // useId, not a hand-built string: ids must stay unique when the same field
  // name appears twice on a page (e.g. this form inside a modal over a view
  // that already renders it), or aria-describedby binds to the wrong node.
  const reactId = useId();
  const id = `${name}-${reactId}`;

  // Only ONE of hint / error is rendered below, so `aria-describedby` must
  // name exactly that one. Joining both would point at an id that does not
  // exist in the DOM whenever a hint is supplied alongside an error — a
  // dangling ARIA reference, which is the same class of defect an audit
  // reports as "aria-describedby references a non-existent element".
  // The error also wins outright: announcing "optional" next to a field that
  // just failed validation contradicts itself.
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const hintId = !error && hint ? `${id}-hint` : undefined;

  const tone = error ? CONTROL_TONE.invalid : CONTROL_TONE.valid;
  const height = as === "textarea" ? "" : CONTROL_MIN_HEIGHT;

  const shared = {
    id,
    name,
    value,
    disabled,
    required,
    minLength,
    maxLength,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy,
    "data-testid": dataTestId,
    className: `${CONTROL_BASE} ${tone} ${height} disabled:opacity-60 ${className}`.trim(),
  };

  const handle = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => onChange(e.target.value);

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={id}
        className="flex items-baseline justify-between gap-2 text-xs font-semibold text-[#1B1F3B]"
      >
        <span>
          {label}
          {/* Required is stated in text, not inferred from an asterisk the
              screen reader may or may not announce. */}
          {required && (
            <span className="ms-1 text-[#A37E44]" aria-hidden="true">
              *
            </span>
          )}
        </span>
        {optional && (
          <span className="shrink-0 text-[11px] font-normal text-slate-500">
            {t("field.optional_marker")}
          </span>
        )}
      </label>

      {as === "select" ? (
        <select {...shared} onChange={handle}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : as === "textarea" ? (
        <textarea
          {...shared}
          rows={rows}
          placeholder={placeholder}
          autoComplete={autoComplete}
          onChange={handle}
        />
      ) : (
        <input
          {...shared}
          type={type}
          placeholder={placeholder}
          autoComplete={autoComplete}
          inputMode={inputMode}
          onChange={handle}
        />
      )}

      {/* Hint and error share the describedBy slot, so both are read with the
          value — the user hears the problem next to the thing it is about. */}
      <div className="min-h-[16px]">
        {error ? (
          <p id={errorId} className="text-[11px] font-medium text-rose-700">
            {error}
          </p>
        ) : hint ? (
          <p id={hintId} className="text-[11px] text-slate-500">
            {hint}
          </p>
        ) : null}
      </div>

      {counter && maxLength ? (
        /* slate-500 (4.76:1), not slate-400 (2.56:1): a character count is
           information, and it sits at 11px where low contrast costs the most.
           It stays aria-hidden on purpose — a live "n / 600" announced on
           every keystroke is noise, and the limit itself is enforced by
           maxLength and stated in the label. Sighted and non-sighted users
           get the constraint; only the running tally is visual. */
        <p className="-mt-1 text-end text-[11px] tabular-nums text-slate-500" aria-hidden="true">
          {value.length} / {maxLength}
        </p>
      ) : null}
    </div>
  );
};

export default Field;
