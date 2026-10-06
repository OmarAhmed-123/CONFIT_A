import React from "react";
import clsx from "clsx";
import { twMerge } from "tailwind-merge";
import { motion } from "framer-motion";
import { usePrefersReducedMotion } from "./InteractionPrimitives";

/**
 * Surface — the embossed-depth surface system (spec 09).
 *
 * Three honest layers, each tied to a CONTENT contract, not a mood:
 *
 *  · `solid`  — the DATA layer (§2): specs, lists, long copy, anything the
 *    shopper actually reads. Opaque background + structural border, no
 *    shadow, never translucent. Blur over data is forbidden (§8).
 *  · `raised` — the SUMMARY layer: buy boxes, verdict cards, recap panels.
 *    Same opaque background; the border still does the structural work
 *    (§6.2) and a soft shadow only decorates — it never replaces the
 *    border and never marks focus (§8).
 *  · `glass-light` / `glass-dark` — contextual overlays ONLY over
 *    uncluttered imagery or gradients (§2): image badges, short-label
 *    controls floating on photos. The CSS is declared solid-first; the
 *    translucent + backdrop-filter upgrade applies exclusively inside
 *    `@supports (backdrop-filter: blur(1px))`, so a browser without it
 *    renders a near-opaque panel that was verified readable over the
 *    worst-case image by computation (see surfaceSystem.test.tsx).
 *    NEVER put glass behind long text or tables (§8) — if you are about
 *    to, the content is data and belongs on `solid`.
 *
 * Forced colors: all four classes collapse to Canvas/CanvasText with a
 * CanvasText border (index.css §6.5) — hierarchy survives as borders.
 * Reduced motion: surfaces are static CSS; hierarchy never depends on an
 * animation (§5).
 */
export type SurfaceVariant = "solid" | "raised" | "glass-light" | "glass-dark";

const VARIANT_CLASS: Record<SurfaceVariant, string> = {
  solid: "surface-solid",
  raised: "surface-raised",
  "glass-light": "surface-glass-light",
  "glass-dark": "surface-glass-dark",
};

type SurfaceProps<T extends React.ElementType> = {
  variant: SurfaceVariant;
  /** Rendered element — div by default; use section/article when semantic. */
  as?: T;
  /**
   * Re-pass: optional entrance reveal (opacity/translate only — no layout
   * shift §9, no spring). Pure decoration: under prefers-reduced-motion the
   * exact static element renders instead, same classes, same hierarchy (§5).
   */
  reveal?: boolean;
  /** Stagger offset in seconds for sibling reveals. */
  revealDelay?: number;
  className?: string;
  children?: React.ReactNode;
} & Omit<React.ComponentPropsWithoutRef<T>, "as" | "className" | "children">;

export const Surface = <T extends React.ElementType = "div">({
  variant,
  as,
  reveal = false,
  revealDelay = 0,
  className,
  children,
  ...rest
}: SurfaceProps<T>) => {
  const Tag = (as ?? "div") as React.ElementType;
  const reduceMotion = usePrefersReducedMotion();
  const cls = twMerge(clsx(VARIANT_CLASS[variant], className));

  if (reveal && !reduceMotion) {
    // One memoized motion component per element type (motion() inside
    // render would remount the subtree on every render).
    const MotionTag = getMotionTag(Tag);
    return (
      <MotionTag
        className={cls}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: revealDelay, ease: "easeOut" }}
        {...rest}
      >
        {children}
      </MotionTag>
    );
  }

  return (
    <Tag className={cls} {...rest}>
      {children}
    </Tag>
  );
};

/** Cache of motion-wrapped tags — stable component identity across renders. */
const motionTagCache = new Map<React.ElementType, React.ElementType>();
function getMotionTag(Tag: React.ElementType): React.ElementType {
  let cached = motionTagCache.get(Tag);
  if (!cached) {
    cached = motion.create(Tag as React.ComponentType);
    motionTagCache.set(Tag, cached);
  }
  return cached;
}

/** §4 names this component GlassPanel — alias kept so intent is greppable. */
export const GlassPanel = Surface;

type RevealProps<T extends React.ElementType> = {
  /** Rendered element — div by default; use section/article when semantic. */
  as?: T;
  /** Stagger offset in seconds for sibling reveals. */
  delay?: number;
  className?: string;
  children?: React.ReactNode;
} & Omit<React.ComponentPropsWithoutRef<T>, "as" | "className" | "children">;

/**
 * Reveal — the Surface entrance motion WITHOUT the surface chrome.
 *
 * For sections that already own their visual treatment (admin cards,
 * tables, filter panels) and only need the spec-09 reveal contract:
 * opacity/translate entrance, no layout shift, no spring; under
 * prefers-reduced-motion the byte-identical static element renders
 * instead — same tag, same classes, full function (§5/§7).
 */
export const Reveal = <T extends React.ElementType = "div">({
  as,
  delay = 0,
  className,
  children,
  ...rest
}: RevealProps<T>) => {
  const Tag = (as ?? "div") as React.ElementType;
  const reduceMotion = usePrefersReducedMotion();

  if (!reduceMotion) {
    const MotionTag = getMotionTag(Tag);
    return (
      <MotionTag
        className={className}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay, ease: "easeOut" }}
        {...rest}
      >
        {children}
      </MotionTag>
    );
  }

  return (
    <Tag className={className} {...rest}>
      {children}
    </Tag>
  );
};
