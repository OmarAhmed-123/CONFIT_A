import { useQuery } from "@tanstack/react-query";
import { tryOnService } from "../services/apiServices";
import { queryKeys } from "../lib/queryClient";
import { msg, type MessageDescriptor } from "../i18n/messages";

/**
 * The consumer-facing gate for every Virtual Try-On call to action.
 *
 * WHY THIS EXISTS (consumer-role closure 2026-09-22)
 * --------------------------------------------------
 * `/catalog/capabilities` answered `vton_gpu_ready: true` from
 * `bool(settings.VTON_WORKER_URL)` while `/try-on/capabilities` probed the GPU
 * and answered `temporarily_unavailable`. Two problems compounded:
 *
 *   1. the flag was wrong (fixed in the backend: one shared probe classifier),
 *   2. nothing in the UI read it anyway. Eight consumer entry points
 *      (`HomeView` ×3, `DiscoverView` ×2, `ProductDetailView` ×2, the studio's
 *      own feature card) opened a try-on flow unconditionally, so a shopper
 *      uploaded a photo and waited for a render that could not happen. The
 *      architecture audit report put it precisely: "the presence of a Try-On
 *      button does not mean the feature works".
 *
 * Fixing only (1) would have left seven surfaces still promising. Fixing (2)
 * per call site would have produced eight copies of the same rule — the same
 * duplication that caused the backend contradiction. So the rule lives here,
 * once, next to the verdict it depends on.
 *
 * HONESTY CONTRACT
 * ----------------
 * - `render`    — the engine can render now (ready, or cold but renderable).
 * - `fit_check` — try-on cannot render, but the no-photo fit path can. The CTA
 *                 is relabelled and routed there: a working capability instead
 *                 of a dead end. It never *says* "Try On" when it will not try on.
 * - `blocked`   — cannot render and there is nowhere honest to send the user;
 *                 the caller disables the control and shows the reason.
 *
 * When availability has not been established yet the kind is `render`: blocking
 * a working feature behind a loading state would punish the healthy case, and
 * the backend now fails fast (~1s, circuit-guarded) with the same honest
 * message this hook renders. `renderAvailable` is therefore `boolean | null`,
 * and `null` is never treated as permission to *claim* success — callers bind
 * their label and destination to `ctaKind`, which is what the user experiences.
 */

/** How a try-on control should behave right now. */
export type TryOnCtaKind = "render" | "fit_check" | "blocked";

export interface TryOnAvailability {
  /** Canonical backend engine state, or null before the first probe resolves. */
  engineState: string | null;
  /** true = renders now · false = does not · null = not measured yet. */
  renderAvailable: boolean | null;
  /** A probe is in flight and no verdict has been cached yet. */
  isProbing: boolean;
  /** Seconds until a retry is worth attempting (fail-fast circuit), else 0. */
  retryAfterSeconds: number;
  /** Machine error code, e.g. VTON_ENGINE_UNAVAILABLE. */
  errorCode: string | null;
  /**
   * Localized sentence describing the state. Built from `engine_state` (a
   * language-neutral discriminator), NOT from the backend's English
   * `user_message`, so the Arabic UI is Arabic. See `upstreamDetail`.
   */
  userMessage: MessageDescriptor | null;
  /**
   * Untranslatable upstream diagnostic, shown only as a secondary detail line.
   * Never the primary message: a shopper should not read operator prose.
   */
  upstreamDetail: string | null;
  /** Decide what a control may offer, given whether it has a fit-check path. */
  ctaKind: (hasFitCheckFallback: boolean) => TryOnCtaKind;
  /**
   * Run `render` only when rendering is honestly on offer; otherwise run
   * `fitCheck` (relabelled) or nothing at all.
   */
  gate: (handlers: {
    render: () => void;
    fitCheck?: () => void;
  }) => () => void;
}

/**
 * Pure decision function — no React, so the honesty rule is unit-testable
 * without rendering a component or mocking a network.
 */
export function resolveTryOnCtaKind(
  renderAvailable: boolean | null,
  hasFitCheckFallback: boolean,
): TryOnCtaKind {
  if (renderAvailable === false) {
    return hasFitCheckFallback ? "fit_check" : "blocked";
  }
  return "render";
}

/**
 * Map the canonical engine state to the i18n key for its sentence.
 *
 * `engine_state` is deliberately used instead of the backend's English prose:
 * the same state must read naturally in both locales. The prose remains
 * available as `upstreamDetail` for support, not as the user's message.
 */
export function engineStateMessage(
  engineState: string | null,
): MessageDescriptor | null {
  switch (engineState) {
    case "temporarily_unavailable":
      // Reuses the copy already shipped (and already translated) by
      // TryOnEngineStatus, so the banner and the CTA cannot word one outage
      // two different ways.
      return msg("tryon.engine_offline_fallback");
    case "cold_start":
      return msg("tryon.engine_warming_detail", { seconds: 60 });
    case "misconfigured":
      return msg("tryon.engine_misconfigured_detail");
    case "available":
      return null;
    default:
      return null;
  }
}

/** Engine states that carry a user-visible warning. */
export function engineStateIsWarnable(engineState: string | null): boolean {
  return engineStateMessage(engineState) !== null;
}

export function useTryOnAvailability(): TryOnAvailability {
  const query = useQuery({
    // Engine-only probe: no product ids, so this is one request shared by every
    // consumer of this hook rather than one per mounted CTA.
    queryKey: queryKeys.tryon.engine(),
    queryFn: () => tryOnService.getCapabilities([]),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    retry: 1,
  });

  const engine = query.data?.engine ?? null;
  const engineState = query.data?.engine_state ?? null;

  // A verdict is authoritative; absence of one is not a verdict.
  const renderAvailable: boolean | null =
    engineState === null
      ? null
      : engineState === "available" || engineState === "cold_start";

  const ctaKind = (hasFitCheckFallback: boolean) =>
    resolveTryOnCtaKind(renderAvailable, hasFitCheckFallback);

  const gate: TryOnAvailability["gate"] = ({ render, fitCheck }) => () => {
    const kind = ctaKind(Boolean(fitCheck));
    if (kind === "render") return render();
    if (kind === "fit_check") return fitCheck?.();
    // blocked: do nothing. Silently failing is better than rendering a
    // spinner for a job the backend has already declared impossible.
  };

  return {
    engineState,
    renderAvailable,
    isProbing: query.isLoading || (query.isFetching && !query.data),
    retryAfterSeconds: Math.max(0, Math.ceil(engine?.retry_after_seconds ?? 0)),
    errorCode: engine?.error_code ?? null,
    userMessage: engineStateMessage(engineState),
    upstreamDetail: engine?.detail ?? null,
    ctaKind,
    gate,
  };
}
