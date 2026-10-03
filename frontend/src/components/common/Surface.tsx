import React from "react";
import clsx from "clsx";
import { twMerge } from "tailwind-merge";

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
  className?: string;
  children?: React.ReactNode;
} & Omit<React.ComponentPropsWithoutRef<T>, "as" | "className" | "children">;

export const Surface = <T extends React.ElementType = "div">({
  variant,
  as,
  className,
  children,
  ...rest
}: SurfaceProps<T>) => {
  const Tag = (as ?? "div") as React.ElementType;
  return (
    <Tag className={twMerge(clsx(VARIANT_CLASS[variant], className))} {...rest}>
      {children}
    </Tag>
  );
};

/** §4 names this component GlassPanel — alias kept so intent is greppable. */
export const GlassPanel = Surface;
