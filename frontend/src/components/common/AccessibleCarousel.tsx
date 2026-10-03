import React, { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight } from "lucide-react";
import clsx from "clsx";
import { twMerge } from "tailwind-merge";
import { usePrefersReducedMotion } from "./InteractionPrimitives";

/**
 * AccessibleCarousel — the project's 2D carousel primitive (spec 10).
 *
 * Deliberate choices, each tied to a spec rule:
 *  · NATIVE SCROLL-SNAP, never translateX (§8): the browser owns scrolling,
 *    so screen readers, keyboard focus, trackpads, touch and RTL all work
 *    the way the platform already works. Navigation uses
 *    `scrollIntoView(inline:"start")`, which is direction-agnostic — the
 *    same code is correct in LTR and RTL (§5/§9).
 *  · NO AUTOPLAY, by construction (§6.4): there is no timer in this file.
 *  · SWIPE IS NEVER THE ONLY WAY (§2): previous/next are real ≥44px
 *    buttons, arrow keys + Home/End work on the scroll region, and every
 *    item is a real link/button supplied by the caller (§6.5).
 *  · POSITION IS TEXT (§6.3/§7): "n of N" renders visibly and is announced
 *    through one polite live region; the announcement never depends on an
 *    animation.
 *  · APG semantics: the section is aria-roledescription="carousel"; each
 *    slide is a group labelled "slide n of N". Slides are NEVER
 *    aria-hidden (§6.6) — an off-screen slide is still reachable and the
 *    browser scrolls it in on focus.
 *  · States are honest (§5): loading renders a named skeleton, error
 *    renders the real message with a retry that re-runs the caller's
 *    fetch, empty says empty. No fake content in any state.
 *  · Reduced motion: snap behavior becomes "auto" (instant) — every
 *    function still works (§7).
 */
export interface AccessibleCarouselProps<T> {
  items: T[];
  getKey: (item: T, index: number) => string | number;
  /** Must render REAL links/buttons for item actions (§6.5). */
  renderItem: (item: T, index: number) => React.ReactNode;
  /** Translated accessible name for the whole carousel. */
  label: string;
  isLoading?: boolean;
  /** Real error message from the caller (server's reason, localized). */
  error?: string | null;
  onRetry?: () => void;
  emptyText?: string;
  className?: string;
  /** Width classes for each slide (defaults to a responsive card width). */
  itemClassName?: string;
  "data-testid"?: string;
}

export function AccessibleCarousel<T>({
  items,
  getKey,
  renderItem,
  label,
  isLoading = false,
  error = null,
  onRetry,
  emptyText,
  className,
  itemClassName,
  "data-testid": dataTestId,
}: AccessibleCarouselProps<T>) {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [active, setActive] = useState(0);
  const isRtl =
    typeof document !== "undefined" && document.documentElement.dir === "rtl";

  const count = items.length;

  const goTo = useCallback(
    (index: number) => {
      if (!count) return;
      const clamped = Math.max(0, Math.min(count - 1, index));
      setActive(clamped);
      const child = trackRef.current?.children[clamped] as
        | HTMLElement
        | undefined;
      // scrollIntoView with a logical alignment is RTL-correct for free —
      // no sign flipping, no mirrored math (§9 RTL).
      child?.scrollIntoView({
        behavior: reduceMotion ? "auto" : "smooth",
        inline: "start",
        block: "nearest",
      });
    },
    [count, reduceMotion],
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    // Physical arrows map to VISUAL direction, so in RTL the roles swap —
    // pressing the arrow that points toward the next visible card always
    // moves to the next card (§5 RTL direction).
    const nextKey = isRtl ? "ArrowLeft" : "ArrowRight";
    const prevKey = isRtl ? "ArrowRight" : "ArrowLeft";
    if (e.key === nextKey) {
      e.preventDefault();
      goTo(active + 1);
    } else if (e.key === prevKey) {
      e.preventDefault();
      goTo(active - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      goTo(0);
    } else if (e.key === "End") {
      e.preventDefault();
      goTo(count - 1);
    }
  };

  /* ---------------- honest non-content states (§5) ---------------- */
  if (isLoading) {
    return (
      <section
        aria-roledescription="carousel"
        aria-label={label}
        aria-busy="true"
        data-testid={dataTestId}
        className={twMerge(clsx("relative", className))}
      >
        <p role="status" aria-live="polite" className="sr-only">
          {t("carousel.loading")}
        </p>
        <div className="flex gap-4 overflow-hidden" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-56 w-64 shrink-0 animate-pulse rounded-2xl bg-slate-200"
            />
          ))}
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section
        aria-roledescription="carousel"
        aria-label={label}
        data-testid={dataTestId}
        className={twMerge(
          clsx("surface-solid rounded-2xl p-5 text-center", className),
        )}
      >
        {/* The server's real reason — never a swallowed generic (§11). */}
        <p role="status" aria-live="polite" className="text-sm text-slate-700">
          {error}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 min-h-11 rounded-xl border border-slate-300 px-4 text-xs font-semibold hover:bg-slate-100"
          >
            {t("carousel.retry")}
          </button>
        )}
      </section>
    );
  }

  if (count === 0) {
    return (
      <section
        aria-roledescription="carousel"
        aria-label={label}
        data-testid={dataTestId}
        className={twMerge(
          clsx("surface-solid rounded-2xl p-5 text-center", className),
        )}
      >
        <p className="text-sm text-slate-500">
          {emptyText ?? t("carousel.empty")}
        </p>
      </section>
    );
  }

  /* ---------------- content state ---------------- */
  return (
    <section
      aria-roledescription="carousel"
      aria-label={label}
      data-testid={dataTestId}
      className={twMerge(clsx("relative", className))}
    >
      {/* Controls BEFORE the track in DOM order so keyboard users meet
          them first; both are real ≥44px buttons (§6.2). */}
      <div className="mb-3 flex items-center justify-between gap-3">
        {/* Visible position text — the indicator required by §1, kept LTR
            because "2 / 5" is a numeric code even on the Arabic page. */}
        <span className="text-[11px] font-semibold text-slate-500" dir="ltr">
          {active + 1} / {count}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => goTo(active - 1)}
            disabled={active === 0}
            aria-label={t("carousel.previous")}
            className="min-h-11 min-w-11 flex items-center justify-center rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-100 disabled:opacity-40"
          >
            {/* Chevrons are decorative; direction comes from rtl:flip. */}
            <span aria-hidden="true" className="rtl:rotate-180">
              <ChevronLeft size={18} />
            </span>
          </button>
          <button
            type="button"
            onClick={() => goTo(active + 1)}
            disabled={active === count - 1}
            aria-label={t("carousel.next")}
            className="min-h-11 min-w-11 flex items-center justify-center rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-100 disabled:opacity-40"
          >
            <span aria-hidden="true" className="rtl:rotate-180">
              <ChevronRight size={18} />
            </span>
          </button>
        </div>
      </div>

      {/* One polite live region announces position as TEXT (§7). */}
      <span className="sr-only" role="status" aria-live="polite">
        {t("carousel.position", { current: active + 1, total: count })}
      </span>

      <div
        ref={trackRef}
        role="group"
        tabIndex={0}
        aria-label={label}
        onKeyDown={onKeyDown}
        className="flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth pb-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44]"
      >
        {items.map((item, index) => (
          <div
            key={getKey(item, index)}
            role="group"
            aria-roledescription="slide"
            aria-label={t("carousel.position", {
              current: index + 1,
              total: count,
            })}
            className={twMerge(
              clsx(
                "snap-start shrink-0 w-64 sm:w-72 min-w-0",
                itemClassName,
              ),
            )}
          >
            {renderItem(item, index)}
          </div>
        ))}
      </div>
    </section>
  );
}
