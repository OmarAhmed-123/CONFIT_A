import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useUIStore } from "../../stores/uiStore";

/**
 * Interaction primitives for commerce actions (add to bag / save / add to
 * wardrobe).
 *
 * WHY THIS EXISTS
 * ---------------
 * Every surface that fired `cartStore.addItem` did three things differently:
 * whether the button disabled while the request was in flight (ProductCard
 * did not — a double-tap sent twice), what the shopper was told while it was
 * pending (ProductDetailView said a literal English "Adding...", the card
 * said nothing), and when "Added" was claimed (ProductDetailView toasted
 * "Added to bag" even when the add was INTERCEPTED by the duplicate-SKU
 * dialog and nothing was added).
 *
 * HONESTY CONTRACT
 * ----------------
 *   idle → pending → success | error, and nothing else.
 *   - "Added" renders ONLY after the server resolved the mutation. There is
 *     no optimistic success state here; the one optimistic flow in the app
 *     (cart quantity/remove, cartStore C7) reconciles against the server and
 *     is documented where it lives.
 *   - An action may also resolve "handled": the flow continues in another
 *     surface (e.g. the duplicate-SKU dialog). The button returns to idle and
 *     claims nothing, because nothing has been added yet.
 *   - "unavailable" resolves to the error state: the caller surfaces the
 *     reason (no purchasable SKU) as text, not as a dead silent button.
 *   - The motion "flight" hint is decorative ONLY. It is aria-hidden, local
 *     to the button (no fixed-coordinate flight across the page), and removed
 *     entirely under `prefers-reduced-motion`. State is always communicated
 *     as text inside an `aria-live="polite"` region.
 */


/* ------------------------------------------------------------------ */
/* StatusIcon — the one semantic status glyph (spec 14)                 */
/* ------------------------------------------------------------------ */

export type StatusIconStatus = "loading" | "success" | "error" | "warning" | "info";

/**
 * Fixed shape-per-status mapping: meaning is carried by the ICON SHAPE and
 * by text, never by colour alone (§8 "لا تجعل error أحمر فقط") and never by
 * a unicode glyph or emoji (§8). The same five shapes everywhere is what
 * makes the status language learnable across Toast, banners and buttons.
 */
const STATUS_ICONS: Record<StatusIconStatus, LucideIcon> = {
  loading: Loader2,
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

/** Default colour accents — hosts may override via className, but the
 *  shape stays; colour is always the SECOND channel, not the only one. */
const STATUS_COLOR: Record<StatusIconStatus, string> = {
  loading: "text-current",
  success: "text-emerald-500",
  error: "text-rose-500",
  warning: "text-amber-500",
  info: "text-sky-500",
};

/**
 * StatusIcon — typed semantic status icon (spec 14).
 *
 * Rules it enforces so hosts cannot get them wrong:
 *  · With visible text next to it (the default), the icon is DECORATIVE:
 *    `aria-hidden`, no role — the container owns `role=status/alert`, the
 *    text owns the meaning (§6.2/§6.3). Pass `label` ONLY for icon-only
 *    placements; it then becomes `role="img"` with that accessible name —
 *    never both a label and adjacent duplicate text (§6.4).
 *  · loading spins via `motion-safe:animate-spin`: under
 *    `prefers-reduced-motion` the same glyph renders STATIC and the text
 *    still says "loading" — full function without motion (§5/§7).
 *  · success/error/warning get ONE short entrance tween (opacity/scale,
 *    0.18s) and then rest: no continuous dancing (§8). Entrance is skipped
 *    entirely under reduced motion.
 */
export const StatusIcon: React.FC<{
  status: StatusIconStatus;
  /** Accessible name for ICON-ONLY placements. Omit when text sits beside it. */
  label?: string;
  size?: number;
  className?: string;
  "data-testid"?: string;
}> = ({ status, label, size = 16, className = "", "data-testid": testId }) => {
  const reduceMotion = usePrefersReducedMotion();
  const Icon = STATUS_ICONS[status];

  const a11yProps = label
    ? ({ role: "img", "aria-label": label } as const)
    : ({ "aria-hidden": true } as const);

  const icon = (
    <Icon
      size={size}
      className={status === "loading" ? "motion-safe:animate-spin" : undefined}
      // The SVG itself is always presentational; the wrapper carries a11y.
      aria-hidden="true"
      focusable="false"
    />
  );

  const shared = {
    ...a11yProps,
    "data-status": status,
    "data-testid": testId,
    className: `inline-flex shrink-0 items-center justify-center ${STATUS_COLOR[status]} ${className}`,
  };

  // Static hosts: loading has its CSS-only motion-safe spin; everything
  // else is a resting glyph. One short entrance tween for state-change
  // feedback, skipped under reduced motion.
  if (reduceMotion || status === "loading" || status === "info") {
    return <span {...shared}>{icon}</span>;
  }

  // Re-pass: each status speaks its OWN motion dialect — one short,
  // one-shot phrase (§8 "no continuous dancing"), transform/opacity only:
  //   success  settles in with a confident pop,
  //   error    gives one brief "no" shake,
  //   warning  tilts once like a raised flag.
  // `key={status}` remounts on every status CHANGE so the entrance replays
  // when loading→success or success→error swap on the same mounted host —
  // without it framer only plays `initial` on first mount and later
  // transitions appeared with no feedback at all.
  const entrance =
    status === "success"
      ? {
          initial: { opacity: 0, scale: 0.5 },
          animate: { opacity: 1, scale: [0.5, 1.08, 1] },
          transition: { duration: 0.28, ease: "easeOut" as const },
        }
      : status === "error"
        ? {
            initial: { opacity: 0 },
            animate: { opacity: 1, x: [0, -2, 2, -1, 0] },
            transition: { duration: 0.3, ease: "easeOut" as const },
          }
        : {
            initial: { opacity: 0, rotate: -8 },
            animate: { opacity: 1, rotate: [-8, 4, 0] },
            transition: { duration: 0.26, ease: "easeOut" as const },
          };

  return (
    <motion.span key={status} {...shared} {...entrance}>
      {icon}
    </motion.span>
  );
};

/**
 * Deterministic prefers-reduced-motion read. framer-motion's own
 * `useReducedMotion` caches the media query in a module singleton on first
 * use, which makes the OS setting unobservable in tests and stale across a
 * live preference change. This reads the media query directly and tracks it.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduce, setReduce] = useState<boolean>(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true,
  );
  useEffect(() => {
    const mql = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mql) return;
    setReduce(mql.matches);
    const onChange = () => setReduce(mql.matches);
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, []);
  return reduce;
}

export type ActionOutcome =
  | "success"
  | "error"
  | "unavailable"
  | "handled"
  | "unauthorized"
  | "offline";
export type AsyncActionState =
  | "idle"
  | "pending"
  | "success"
  | "error"
  | "unavailable"
  | "unauthorized"
  | "offline";

export type AsyncAction = () =>
  | Promise<ActionOutcome | void>
  | ActionOutcome
  | void;

const SUCCESS_RESET_MS = 2000;
const ERROR_RESET_MS = 4000;

/**
 * Maps a thrown mutation error onto the action contract (spec 01 §5):
 *   - the browser says we are offline     → "offline" (never claim failure
 *     of a request that could not leave the device, never claim success);
 *   - ApiError 401 / code AUTH_REQUIRED   → "unauthorized" (the fix is
 *     signing in, not retrying);
 *   - anything else                       → "error" (actionable retry).
 * Exported so view-level handlers that catch for their own toasts can
 * return the same classification instead of flattening everything to error.
 */
export function classifyActionError(err: unknown): "unauthorized" | "offline" | "error" {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return "offline";
  }
  const e = err as { status?: number; code?: string } | null;
  if (e && (e.status === 401 || e.code === "AUTH_REQUIRED")) {
    return "unauthorized";
  }
  return "error";
}

/**
 * State machine for a single mutation-backed control.
 * Guarantees: never two in-flight sends from the same control; success is
 * only ever entered from a resolved action; timers are cleaned on unmount.
 */
export function useAsyncAction(
  action: AsyncAction,
  opts?: {
    /**
     * Fired once on entering "unauthorized". The default button wires this
     * to the auth MODAL (uiStore.openAuthModal), which keeps the shopper on
     * the page — context is preserved, nothing navigates away.
     */
    onUnauthorized?: () => void;
  },
) {
  const [state, setState] = useState<AsyncActionState>("idle");
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onUnauthorizedRef = useRef(opts?.onUnauthorized);
  onUnauthorizedRef.current = opts?.onUnauthorized;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (resetTimer.current) clearTimeout(resetTimer.current);
    };
  }, []);

  const run = useCallback(async () => {
    if (inFlight.current) return; // one control never sends twice
    inFlight.current = true;
    if (resetTimer.current) clearTimeout(resetTimer.current);
    setState("pending");

    let outcome: ActionOutcome;
    try {
      const res = await action();
      outcome = (res as ActionOutcome | undefined) ?? "success";
    } catch (err) {
      // The caller owns the human-readable error (toast with the server's
      // message); this machine owns the control's own state — classified,
      // because "sign in" and "you are offline" are different next steps
      // than "retry".
      outcome = classifyActionError(err);
    }

    inFlight.current = false;
    if (!mounted.current) return;

    if (outcome === "success") {
      setState("success");
      resetTimer.current = setTimeout(() => {
        if (mounted.current) setState("idle");
      }, SUCCESS_RESET_MS);
    } else if (outcome === "handled") {
      // Another surface (duplicate dialog, size picker…) continues the flow.
      // Claiming success here would be a lie; claiming failure would too.
      setState("idle");
    } else if (outcome === "unauthorized") {
      // The action needs a signed-in user. Open auth WITHOUT losing context
      // (modal, no navigation) and say so as text on the control itself.
      setState("unauthorized");
      onUnauthorizedRef.current?.();
      resetTimer.current = setTimeout(() => {
        if (mounted.current) setState("idle");
      }, ERROR_RESET_MS);
    } else if (outcome === "unavailable") {
      // Spec 08: name the capability/stock gap instead of flattening it to a
      // generic failure — retrying an unavailable thing is not actionable,
      // but the control stays usable (e.g. after picking another size).
      setState("unavailable");
      resetTimer.current = setTimeout(() => {
        if (mounted.current) setState("idle");
      }, ERROR_RESET_MS);
    } else if (outcome === "offline") {
      // The request never reached the server: claiming failure of the
      // OPERATION would be as dishonest as claiming success. Name the real
      // problem and keep the control actionable for retry.
      setState("offline");
      resetTimer.current = setTimeout(() => {
        if (mounted.current) setState("idle");
      }, ERROR_RESET_MS);
    } else {
      setState("error");
      resetTimer.current = setTimeout(() => {
        if (mounted.current) setState("idle");
      }, ERROR_RESET_MS);
    }
  }, [action]);

  return { state, run, isPending: state === "pending" };
}

/** Text-first status announcer. The visually hidden copy IS the state. */
export const ActionStatusLive: React.FC<{
  state: AsyncActionState;
  pendingText: string;
  successText: string;
  errorText: string;
  unauthorizedText?: string;
  offlineText?: string;
  unavailableText?: string;
}> = ({ state, pendingText, successText, errorText, unauthorizedText, offlineText, unavailableText }) => (
  <span className="sr-only" role="status" aria-live="polite">
    {state === "pending"
      ? pendingText
      : state === "success"
        ? successText
        : state === "error"
          ? errorText
          : state === "unauthorized"
            ? (unauthorizedText ?? "")
            : state === "offline"
              ? (offlineText ?? "")
              : state === "unavailable"
                ? (unavailableText ?? "")
                : ""}
  </span>
);

/**
 * Decorative local "flight" hint: the icon lifts off the control and fades,
 * suggesting product → bag/closet. Contained in the control's own box (no
 * fragile fixed coordinates), aria-hidden, and absent under reduced motion —
 * the text state carries the meaning on its own.
 */
export const FlightHint: React.FC<{
  active: boolean;
  children: React.ReactNode;
}> = ({ active, children }) => {
  const reduceMotion = usePrefersReducedMotion();
  if (reduceMotion) return null;
  return (
    <AnimatePresence>
      {active && (
        <motion.span
          aria-hidden="true"
          data-testid="flight-hint"
          className="pointer-events-none absolute inset-x-0 top-0 flex justify-center"
          initial={{ opacity: 0.9, y: 2, scale: 1 }}
          animate={{ opacity: 0, y: -22, scale: 0.8 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.45, ease: "easeOut" }}
        >
          {children}
        </motion.span>
      )}
    </AnimatePresence>
  );
};

export interface AsyncActionButtonProps {
  onAction: AsyncAction;
  /** Visible label in the idle state — also the accessible name base. */
  idleLabel: string;
  pendingLabel?: string;
  successLabel?: string;
  errorLabel?: string;
  unauthorizedLabel?: string;
  offlineLabel?: string;
  /**
   * Visible text for the "unavailable" outcome (no purchasable SKU, stock
   * gap). Spec §5: "unavailable" must NAME the reason — before this prop the
   * state machine entered `unavailable` but the button kept rendering its
   * idle label and the live region announced an empty string, so the only
   * explanation (if any) was a toast the shopper may have missed.
   */
  unavailableLabel?: string;
  /**
   * Fired on entering "unauthorized". Defaults to opening the auth modal —
   * the shopper stays on the page, so nothing they were doing is lost.
   */
  onUnauthorized?: () => void;
  /** Leading icon in idle state (semantic, from ConfitIcons). */
  icon?: React.ReactNode;
  /** Icon used by the decorative lift-off hint. Defaults to `icon`. */
  flightIcon?: React.ReactNode;
  disabled?: boolean;
  className?: string;
  "data-testid"?: string;
}

/**
 * A mutation-backed button. ≥44px touch target, disabled while pending,
 * success only after the action resolves, failure returns it to an
 * actionable state. All copy arrives translated from the caller.
 */
export const AsyncActionButton: React.FC<AsyncActionButtonProps> = ({
  onAction,
  idleLabel,
  pendingLabel,
  successLabel,
  errorLabel,
  unauthorizedLabel,
  offlineLabel,
  unavailableLabel,
  onUnauthorized,
  icon,
  flightIcon,
  disabled = false,
  className = "",
  "data-testid": dataTestId,
}) => {
  const { t } = useTranslation();
  const openAuthModal = useUIStore((s) => s.openAuthModal);
  const { state, run, isPending } = useAsyncAction(onAction, {
    onUnauthorized: onUnauthorized ?? (() => openAuthModal("login")),
  });

  const labels = {
    pending: pendingLabel ?? t("commerce.adding"),
    success: successLabel ?? t("commerce.added_confirm"),
    error: errorLabel ?? t("commerce.add_failed_retry"),
    unauthorized: unauthorizedLabel ?? t("common.sign_in_to_continue"),
    offline: offlineLabel ?? t("common.offline_retry"),
    unavailable: unavailableLabel ?? t("commerce.unavailable_label"),
  };

  const visibleLabel =
    state === "pending"
      ? labels.pending
      : state === "success"
        ? labels.success
        : state === "error"
          ? labels.error
          : state === "unauthorized"
            ? labels.unauthorized
            : state === "offline"
              ? labels.offline
              : state === "unavailable"
                ? labels.unavailable
                : idleLabel;

  return (
    <button
      type="button"
      onClick={run}
      disabled={disabled || isPending}
      aria-disabled={disabled || isPending}
      aria-busy={isPending}
      data-state={state}
      data-testid={dataTestId}
      className={[
        "relative min-h-[44px] transition-all",
        state === "error" || state === "offline" || state === "unavailable"
          ? "ring-1 ring-[#7A1F2B]/40"
          : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <FlightHint active={state === "success"}>
        {flightIcon ?? icon}
      </FlightHint>

      <span className="flex items-center justify-center gap-1.5">
        {state === "pending" ? (
          <span
            aria-hidden="true"
            className="inline-block w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent motion-safe:animate-spin"
          />
        ) : state === "success" ? (
          // Spec 14 §8: no unicode glyph as a production status — the shared
          // semantic shape, decorative beside the visible success label.
          <StatusIcon status="success" size={14} className="text-current" />
        ) : (
          // Decorative inside a text-labelled button: without aria-hidden the
          // icon's own label (e.g. "Shopping Bag") leaks into the accessible
          // name and the control stops being findable as its visible text.
          icon && <span aria-hidden="true">{icon}</span>
        )}
        <span>{visibleLabel}</span>
      </span>

      <ActionStatusLive
        state={state}
        pendingText={labels.pending}
        successText={labels.success}
        errorText={labels.error}
        unauthorizedText={labels.unauthorized}
        offlineText={labels.offline}
        unavailableText={labels.unavailable}
      />
    </button>
  );
};

/**
 * Wishlist is LOCAL-ONLY in this deployment: there is no wishlist endpoint in
 * `apiServices.ts`, so the heart persists nothing to the server. The copy
 * says so ("on this device") instead of implying an account-level save —
 * inventing a synced wishlist in the UI would be a false claim about where
 * the shopper's data lives. The toggle itself is instantaneous local state,
 * so there is no pending phase to report.
 */
export const WishlistToggle: React.FC<{
  isWishlisted: boolean;
  onToggle: () => void;
  className?: string;
  children: React.ReactNode;
}> = ({ isWishlisted, onToggle, className = "", children }) => {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const [announcement, setAnnouncement] = useState("");
  const [popKey, setPopKey] = useState(0);

  const handleClick = () => {
    const next = !isWishlisted;
    onToggle();
    setAnnouncement(
      next ? t("commerce.wishlist_saved_device") : t("commerce.wishlist_removed"),
    );
    if (next) setPopKey((k) => k + 1);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={t("a11y.toggle_wishlist")}
      aria-pressed={isWishlisted}
      className={[
        "relative min-w-[44px] min-h-[44px] flex items-center justify-center",
        className,
      ].join(" ")}
    >
      {reduceMotion || popKey === 0 ? (
        children
      ) : (
        <motion.span
          key={popKey}
          aria-hidden="true"
          className="flex items-center justify-center"
          initial={{ scale: 0.6 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 500, damping: 18 }}
        >
          {children}
        </motion.span>
      )}
      <span className="sr-only" role="status" aria-live="polite">
        {announcement}
      </span>
    </button>
  );
};
