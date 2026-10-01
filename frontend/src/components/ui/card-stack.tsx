"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { SquareArrowOutUpRight, ChevronLeft, ChevronRight } from "lucide-react";
import { usePrefersReducedMotion } from "../common/InteractionPrimitives";

function cn(...classes: Array<string | undefined | null | false>) {
  return classes.filter(Boolean).join(" ");
}

export type CardStackItem = {
  id: string | number;
  title: string;
  description?: string;
  imageSrc?: string;
  href?: string;
  ctaLabel?: string;
  tag?: string;
};

export type CardStackProps<T extends CardStackItem> = {
  items: T[];

  /** Selected index on mount */
  initialIndex?: number;

  /** How many cards are visible around the active (odd recommended) */
  maxVisible?: number;

  /** Card sizing */
  cardWidth?: number;
  cardHeight?: number;

  /** How much cards overlap each other (0..0.8). Higher = more overlap */
  overlap?: number;

  /** Total fan angle (deg). Higher = wider arc */
  spreadDeg?: number;

  /** 3D / depth feel */
  perspectivePx?: number;
  depthPx?: number;
  tiltXDeg?: number;

  /** Active emphasis */
  activeLiftPx?: number;
  activeScale?: number;
  inactiveScale?: number;

  /** Motion */
  springStiffness?: number;
  springDamping?: number;

  /** Behavior */
  loop?: boolean;

  /** UI */
  showDots?: boolean;
  className?: string;

  /** Hooks */
  onChangeIndex?: (index: number, item: T) => void;

  /** Custom renderer (optional) */
  renderCard?: (item: T, state: { active: boolean }) => React.ReactNode;

  /**
   * Translated copy injected by the host (spec 10 §7): this ui primitive
   * must not hardcode English. Defaults exist only as a dev safety net.
   */
  labels?: {
    carousel?: string;
    previous?: string;
    next?: string;
    goTo?: (title: string) => string;
    open?: (title: string) => string;
    position?: (current: number, total: number) => string;
    noImage?: string;
  };
};

function wrapIndex(n: number, len: number) {
  if (len <= 0) return 0;
  return ((n % len) + len) % len;
}

/** Minimal signed offset from active index to i, with wrapping (for loop behavior). */
function signedOffset(i: number, active: number, len: number, loop: boolean) {
  const raw = i - active;
  if (!loop || len <= 1) return raw;

  // consider wrapped alternative
  const alt = raw > 0 ? raw - len : raw + len;
  return Math.abs(alt) < Math.abs(raw) ? alt : raw;
}

export function CardStack<T extends CardStackItem>({
  items,
  initialIndex = 0,
  maxVisible = 7,

  cardWidth = 520,
  cardHeight = 320,

  overlap = 0.48,
  spreadDeg = 48,

  perspectivePx = 1100,
  depthPx = 140,
  tiltXDeg = 12,

  activeLiftPx = 22,
  activeScale = 1.03,
  inactiveScale = 0.94,

  springStiffness = 280,
  springDamping = 28,

  loop = true,

  showDots = true,
  className,

  onChangeIndex,
  renderCard,
  labels,
}: CardStackProps<T>) {
  // Deterministic media-query read — framer's useReducedMotion caches the
  // value in a module singleton and goes stale (see InteractionPrimitives).
  const reduceMotion = usePrefersReducedMotion();
  const len = items.length;

  const L = {
    carousel: labels?.carousel ?? "Carousel",
    previous: labels?.previous ?? "Previous card",
    next: labels?.next ?? "Next card",
    goTo: labels?.goTo ?? ((title: string) => `Go to ${title}`),
    open: labels?.open ?? ((title: string) => `Open ${title}`),
    position:
      labels?.position ??
      ((current: number, total: number) => `Card ${current} of ${total}`),
    noImage: labels?.noImage ?? "No image",
  };

  const [active, setActive] = React.useState(() =>
    wrapIndex(initialIndex, len),
  );

  // keep active in bounds if items change
  React.useEffect(() => {
    setActive((a) => wrapIndex(a, len));
  }, [len]);

  React.useEffect(() => {
    if (!len) return;
    onChangeIndex?.(active, items[active]!);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const maxOffset = Math.max(0, Math.floor(maxVisible / 2));

  const cardSpacing = Math.max(10, Math.round(cardWidth * (1 - overlap)));
  const stepDeg = maxOffset > 0 ? spreadDeg / maxOffset : 0;

  const canGoPrev = loop || active > 0;
  const canGoNext = loop || active < len - 1;

  const prev = React.useCallback(() => {
    if (!len) return;
    if (!canGoPrev) return;
    setActive((a) => wrapIndex(a - 1, len));
  }, [canGoPrev, len]);

  const next = React.useCallback(() => {
    if (!len) return;
    if (!canGoNext) return;
    setActive((a) => wrapIndex(a + 1, len));
  }, [canGoNext, len]);

  // Keyboard navigation (when container focused). Physical arrows map to
  // VISUAL direction: on an RTL page the arrow pointing at the next card
  // is ArrowLeft, so the handlers swap (§5 RTL direction).
  const onKeyDown = (e: React.KeyboardEvent) => {
    const isRtl =
      typeof document !== "undefined" &&
      document.documentElement.dir === "rtl";
    const nextKey = isRtl ? "ArrowLeft" : "ArrowRight";
    const prevKey = isRtl ? "ArrowRight" : "ArrowLeft";
    if (e.key === nextKey) {
      e.preventDefault();
      next();
    } else if (e.key === prevKey) {
      e.preventDefault();
      prev();
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(len - 1);
    }
  };

  // Spec 10 §6.4: the autoplay machinery was REMOVED from this component —
  // a carousel that moves by itself moves focus targets under the user.
  // Navigation is now exclusively user-initiated (buttons, keys, swipe,
  // card click).

  if (!len) return null;

  const activeItem = items[active]!;

  return (
    <div className={cn("w-full", className)}>
      {/* Stage — a labelled carousel group; the live region below carries
          the position as text so the state never depends on motion (§7). */}
      <div
        className="relative w-full"
        style={{ height: Math.max(380, cardHeight + 80) }}
        tabIndex={0}
        role="group"
        aria-roledescription="carousel"
        aria-label={L.carousel}
        onKeyDown={onKeyDown}
      >
        {/* background wash / spotlight (unique feel) */}
        <div
          className="pointer-events-none absolute inset-x-0 top-6 mx-auto h-48 w-[70%] rounded-full bg-black/5 blur-3xl dark:bg-white/5"
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 mx-auto h-40 w-[76%] rounded-full bg-black/10 blur-3xl dark:bg-black/30"
          aria-hidden="true"
        />

        <div
          className="absolute inset-0 flex items-end justify-center"
          style={{
            perspective: `${perspectivePx}px`,
          }}
        >
          <AnimatePresence initial={false}>
            {items.map((item, i) => {
              const off = signedOffset(i, active, len, loop);
              const abs = Math.abs(off);
              const visible = abs <= maxOffset;

              // hide far-away cards cleanly
              if (!visible) return null;

              // fan geometry
              const rotateZ = off * stepDeg;
              const x = off * cardSpacing;
              const y = abs * 10; // subtle arc-down feel
              const z = -abs * depthPx;

              const isActive = off === 0;

              const scale = isActive ? activeScale : inactiveScale;
              const lift = isActive ? -activeLiftPx : 0;

              const rotateX = isActive ? 0 : tiltXDeg;

              const zIndex = 100 - abs;

              // drag only on the active card
              const dragProps = isActive
                ? {
                    drag: "x" as const,
                    dragConstraints: { left: 0, right: 0 },
                    dragElastic: 0.18,
                    onDragEnd: (
                      _e: any,
                      info: { offset: { x: number }; velocity: { x: number } },
                    ) => {
                      if (reduceMotion) return;
                      const travel = info.offset.x;
                      const v = info.velocity.x;
                      const threshold = Math.min(160, cardWidth * 0.22);

                      // swipe logic
                      if (travel > threshold || v > 650) prev();
                      else if (travel < -threshold || v < -650) next();
                    },
                  }
                : {};

              return (
                <motion.div
                  key={item.id}
                  className={cn(
                    "absolute bottom-0 overflow-hidden rounded-2xl border-4 border-black/10 shadow-xl dark:border-white/10",
                    "will-change-transform select-none",
                    isActive
                      ? "cursor-grab active:cursor-grabbing"
                      : "cursor-pointer",
                  )}
                  style={{
                    width: cardWidth,
                    height: cardHeight,
                    zIndex,
                    transformStyle: "preserve-3d",
                  }}
                  initial={
                    reduceMotion
                      ? false
                      : {
                          opacity: 0,
                          y: y + 40,
                          x,
                          rotateZ,
                          rotateX,
                          scale,
                        }
                  }
                  animate={{
                    opacity: 1,
                    x,
                    y: y + lift,
                    rotateZ,
                    rotateX,
                    // framer doesn't support translateZ directly in animate on all setups,
                    // so we use a custom transform via style below.
                    scale,
                  }}
                  transition={
                    reduceMotion
                      ? { duration: 0 }
                      : {
                          type: "spring",
                          stiffness: springStiffness,
                          damping: springDamping,
                        }
                  }
                  // translateZ via style transform (kept stable w/ motion values above)
                  // We apply translateZ by using a CSS transform in a child wrapper.
                  onClick={() => setActive(i)}
                  {...dragProps}
                >
                  <div
                    className="h-full w-full"
                    style={{
                      transform: `translateZ(${z}px)`,
                      transformStyle: "preserve-3d",
                    }}
                  >
                    {renderCard ? (
                      renderCard(item, { active: isActive })
                    ) : (
                      <DefaultFanCard item={item} active={isActive} />
                    )}
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      </div>

      {/* Controls: swipe is never the only way (§2). Previous/next are
          real ≥44px buttons; the position is visible text AND a polite
          announcement; dots are secondary jump targets at the WCAG 2.5.8
          minimum (24px). */}
      <div className="mt-4 flex items-center justify-center gap-3">
        <button
          type="button"
          onClick={prev}
          disabled={!canGoPrev}
          aria-label={L.previous}
          className="min-h-11 min-w-11 flex items-center justify-center rounded-xl border border-black/10 text-foreground/70 hover:bg-black/5 disabled:opacity-40"
        >
          <span aria-hidden="true" className="rtl:rotate-180">
            <ChevronLeft className="h-4 w-4" />
          </span>
        </button>

        <span className="text-[11px] font-semibold text-foreground/60" dir="ltr">
          {active + 1} / {len}
        </span>
        <span className="sr-only" role="status" aria-live="polite">
          {L.position(active + 1, len)}
        </span>

        {showDots ? (
          <div className="flex items-center">
            {items.map((it, idx) => {
              const on = idx === active;
              return (
                <button
                  key={it.id}
                  type="button"
                  onClick={() => setActive(idx)}
                  aria-label={L.goTo(it.title)}
                  aria-current={on ? "true" : undefined}
                  className="flex h-6 min-w-6 items-center justify-center"
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "h-2 w-2 rounded-full transition",
                      on
                        ? "bg-foreground"
                        : "bg-foreground/30 hover:bg-foreground/50",
                    )}
                  />
                </button>
              );
            })}
          </div>
        ) : null}

        <button
          type="button"
          onClick={next}
          disabled={!canGoNext}
          aria-label={L.next}
          className="min-h-11 min-w-11 flex items-center justify-center rounded-xl border border-black/10 text-foreground/70 hover:bg-black/5 disabled:opacity-40"
        >
          <span aria-hidden="true" className="rtl:rotate-180">
            <ChevronRight className="h-4 w-4" />
          </span>
        </button>

        {activeItem.href ? (
          <a
            href={activeItem.href}
            className="min-h-11 min-w-11 flex items-center justify-center text-muted-foreground transition hover:text-foreground"
            aria-label={L.open(activeItem.title)}
          >
            <span aria-hidden="true">
              <SquareArrowOutUpRight className="h-4 w-4" />
            </span>
          </a>
        ) : null}
      </div>
    </div>
  );
}

function DefaultFanCard({ item }: { item: CardStackItem; active: boolean }) {
  return (
    <div className="relative h-full w-full">
      {/* image */}
      <div className="absolute inset-0">
        {item.imageSrc ? (
          <img
            src={item.imageSrc}
            alt={item.title}
            className="h-full w-full object-cover"
            draggable={false}
            loading="eager"
          />
        ) : (
          <div
            aria-hidden="true"
            className="flex h-full w-full items-center justify-center bg-secondary"
          />
        )}
      </div>

      {/* subtle gradient overlay at bottom for text readability */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />

      {/* content */}
      <div className="relative z-10 flex h-full flex-col justify-end p-5">
        <div className="truncate text-lg font-semibold text-white">
          {item.title}
        </div>
        {item.description ? (
          <div className="mt-1 line-clamp-2 text-sm text-white/80">
            {item.description}
          </div>
        ) : null}
      </div>
    </div>
  );
}
