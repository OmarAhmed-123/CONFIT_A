import React, { useCallback, useRef } from "react";
import { motion } from "framer-motion";
import { Check, AlertTriangle, WifiOff, Lock, PackageX } from "lucide-react";
import { useUIStore } from "../../stores/uiStore";
import { recordCtaMetric } from "../../lib/ctaMetrics";
import {
  useAsyncAction,
  usePrefersReducedMotion,
  classifyActionError,
  ActionStatusLive,
  type ActionOutcome,
  type AsyncAction,
  type AsyncActionState,
} from "./InteractionPrimitives";

/**
 * ActionButton — the unified kinetic CTA with trust state (spec 08).
 *
 * Built ON the spec-01 state machine; the additions are the trust contract:
 *
 *  · FOCUS NEVER DROPS (§9): the control is never given the `disabled`
 *    attribute mid-flight — real browsers move focus to <body> when a
 *    focused button becomes disabled. Re-entry is blocked by the machine's
 *    in-flight guard plus `aria-disabled`, so there is still exactly one
 *    submit per activation.
 *  · LAYOUT NEVER MOVES (§6.3/§2): fixed min-height, and every possible
 *    state label is pre-rendered invisibly in the same grid cell, so the
 *    control is as wide as its widest label from the first paint. No
 *    spring/bounce — motion is transform/opacity only, and under
 *    `prefers-reduced-motion` there is no motion at all (text carries the
 *    state by itself).
 *  · FINANCIAL HONESTY (§2/§9): the machine can only ENTER "success" from
 *    a resolved action — there is no code path that paints success before
 *    the server replies. Checkout drives the CONTROLLED mode, where even
 *    that success state is never used: the server-confirmed navigation is
 *    the success surface.
 *  · CANCELLATION IS NOT FAILURE (§5): an action that rejects with
 *    AbortError returns the control silently to idle — the user changed
 *    their mind; nothing failed, nothing succeeded.
 *  · NON-SENSITIVE TELEMETRY (§6.5): with `metricsId`, duration + outcome
 *    word are recorded locally (see ctaMetrics.ts). Never payload data.
 *
 * Two modes:
 *  · UNCONTROLLED (default): pass `onAction`; the internal machine owns
 *    pending/success/error/unavailable/unauthorized/offline.
 *  · CONTROLLED: pass `state` (+ optional `onPress`); the caller owns the
 *    transitions. This exists for form-submit flows (checkout) where the
 *    view already owns an isSubmitting flag and success is a navigation.
 */
export interface ActionButtonLabels {
  idle: string;
  pending: string;
  success?: string;
  error?: string;
  unavailable?: string;
  unauthorized?: string;
  offline?: string;
}

export interface ActionButtonProps {
  labels: ActionButtonLabels;
  /** Uncontrolled mode: the mutation to run. */
  onAction?: AsyncAction;
  /** Controlled mode: the caller-owned state. Supplying this disables the machine. */
  state?: AsyncActionState;
  /** Controlled mode click handler (omit for native type="submit" forms). */
  onPress?: () => void;
  type?: "button" | "submit";
  /** Static id for non-sensitive duration/outcome telemetry (§6.5). */
  metricsId?: string;
  /**
   * Marks a money-moving action. Purely declarative today — the honesty
   * guarantees hold for every button — but it documents intent at the call
   * site and is asserted in tests (financial CTAs never self-flash success).
   */
  financial?: boolean;
  /** Fired on "unauthorized" (uncontrolled). Defaults to the auth modal. */
  onUnauthorized?: () => void;
  /** Leading icon for the idle state; rendered decorative (aria-hidden). */
  icon?: React.ReactNode;
  disabled?: boolean;
  /**
   * Cross-control lockout (e.g. "revoke is in flight, so hold publish"):
   * swallows clicks + aria-disabled, but NEVER the `disabled` attribute —
   * a sibling action must not eject this control's keyboard focus (§9).
   */
  softDisabled?: boolean;
  className?: string;
  "data-testid"?: string;
}

/** Maps the viewmodel convention `true | false | undefined` → outcome. */
export function outcomeFromResult(res: boolean | undefined | void): ActionOutcome {
  if (res === true) return "success";
  if (res === false) return "error";
  // undefined/void = another surface took over (dialog, inline validation…)
  return "handled";
}

const stateIcon: Partial<Record<AsyncActionState, React.ReactNode>> = {
  success: <Check size={14} strokeWidth={3} aria-hidden="true" />,
  error: <AlertTriangle size={14} aria-hidden="true" />,
  unavailable: <PackageX size={14} aria-hidden="true" />,
  unauthorized: <Lock size={14} aria-hidden="true" />,
  offline: <WifiOff size={14} aria-hidden="true" />,
};

export const ActionButton: React.FC<ActionButtonProps> = ({
  labels,
  onAction,
  state: controlledState,
  onPress,
  type = "button",
  metricsId,
  financial = false,
  onUnauthorized,
  icon,
  disabled = false,
  softDisabled = false,
  className = "",
  "data-testid": dataTestId,
}) => {
  const openAuthModal = useUIStore((s) => s.openAuthModal);
  const reduceMotion = usePrefersReducedMotion();
  const startedAt = useRef<number>(0);

  // Wrap the caller's action: AbortError → "handled" (cancel ≠ failure),
  // thrown errors are classified HERE so the metric sees the real outcome.
  const wrappedAction = useCallback(async (): Promise<ActionOutcome> => {
    startedAt.current = performance.now();
    let outcome: ActionOutcome;
    try {
      const res = await onAction!();
      outcome = (res as ActionOutcome | undefined) ?? "success";
    } catch (err) {
      outcome =
        (err as { name?: string } | null)?.name === "AbortError"
          ? "handled"
          : classifyActionError(err);
    }
    if (metricsId) {
      recordCtaMetric({
        id: metricsId,
        durationMs: performance.now() - startedAt.current,
        outcome,
      });
    }
    return outcome;
  }, [onAction, metricsId]);

  const machine = useAsyncAction(wrappedAction, {
    onUnauthorized: onUnauthorized ?? (() => openAuthModal("login")),
  });

  const isControlled = controlledState !== undefined;
  const state: AsyncActionState = isControlled ? controlledState : machine.state;
  const isPending = state === "pending";

  const resolved: Required<ActionButtonLabels> = {
    idle: labels.idle,
    pending: labels.pending,
    success: labels.success ?? labels.idle,
    error: labels.error ?? labels.idle,
    unavailable: labels.unavailable ?? labels.error ?? labels.idle,
    unauthorized: labels.unauthorized ?? labels.idle,
    offline: labels.offline ?? labels.error ?? labels.idle,
  };
  const visibleLabel = resolved[state];

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    // One activation = at most one send. While pending (either mode) a
    // click is swallowed instead of the button being disabled — that keeps
    // keyboard focus where the user put it (§9 "focus لا يضيع").
    if (disabled || softDisabled || isPending) {
      e.preventDefault();
      return;
    }
    if (isControlled) {
      onPress?.();
      // type="submit" buttons let the native form submission proceed.
      return;
    }
    e.preventDefault();
    void machine.run();
  };

  const body = (
    <>
      <span className="flex items-center justify-center gap-1.5">
        {isPending ? (
          <span
            aria-hidden="true"
            data-testid="cta-spinner"
            className="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent motion-safe:animate-spin"
          />
        ) : (
          <span aria-hidden="true" className="inline-flex items-center">
            {stateIcon[state] ?? icon ?? null}
          </span>
        )}
        {/* Label stack: every state label occupies the SAME grid cell, the
            inactive ones invisible — the control reserves its widest label
            up front so state changes cannot shift layout (§6.3). */}
        <span className="grid text-center" data-testid="cta-label-stack">
          {(Object.keys(resolved) as AsyncActionState[]).map((k) => (
            <span
              key={k}
              aria-hidden={k !== state ? "true" : undefined}
              className={`col-start-1 row-start-1 ${k === state ? "" : "invisible"}`}
            >
              {resolved[k]}
            </span>
          ))}
        </span>
      </span>
      <ActionStatusLive
        state={state}
        pendingText={resolved.pending}
        successText={resolved.success}
        errorText={resolved.error}
        unavailableText={resolved.unavailable}
        unauthorizedText={resolved.unauthorized}
        offlineText={resolved.offline}
      />
    </>
  );

  const sharedProps = {
    type,
    onClick: handleClick,
    // `disabled` ONLY for caller-level unavailability (empty cart, invalid
    // composition) — never for the transient pending phase (focus!).
    disabled,
    "aria-disabled": disabled || softDisabled || isPending,
    "aria-busy": isPending,
    "data-state": state,
    "data-financial": financial || undefined,
    "data-testid": dataTestId,
    className: [
      "relative min-h-[44px] select-none",
      softDisabled && !isPending ? "opacity-40" : "",
      state === "error" || state === "offline" ? "ring-1 ring-[#7A1F2B]/40" : "",
      state === "unavailable" ? "ring-1 ring-slate-400/50" : "",
      className,
    ]
      .filter(Boolean)
      .join(" "),
  } as const;

  // Reduced motion: a perfectly plain button — the state is text either way.
  if (reduceMotion) {
    return <button {...sharedProps}>{body}</button>;
  }

  // Kinetic variant: transform/opacity only (§2 — no spring/bounce, no
  // layout-affecting animation). Tween, not spring, so nothing overshoots.
  return (
    <motion.button
      {...sharedProps}
      whileTap={disabled || softDisabled || isPending ? undefined : { scale: 0.97 }}
      animate={{ opacity: 1, scale: state === "success" ? [1, 1.02, 1] : 1 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
    >
      {body}
    </motion.button>
  );
};
