import React from "react";
import { useTranslation } from "react-i18next";

import { Product } from "../../models";
import { useUIStore } from "../../stores/uiStore";
import { useTryOnAvailability } from "../../hooks/useTryOnAvailability";
import { TryOnIcon, RulerIcon } from "../icons/ConfitIcons";
import { resolveMessage } from "../../i18n/messages";

/**
 * The ONE try-on control.
 *
 * WHY THIS EXISTS
 * ---------------
 * `useTryOnAvailability` already centralised the *rule* (can the engine
 * render right now?). What stayed duplicated was everything around it: each
 * call site re-derived `ctaKind`, re-picked the icon, re-wrote the label
 * ternary, re-decided the disabled state and re-rendered the blocked reason.
 * `ProductCard` alone contained two copies.
 *
 * The cost of that duplication was not aesthetic. Surfaces that showed a
 * product image but were not a "card" — the wardrobe gap recommendations and
 * the saved-look tiles — simply had no try-on at all, because adding one
 * meant copying six lines of gating rather than dropping in a component.
 *
 * So the control itself lives here, once. A surface that shows a garment can
 * offer try-on by rendering this; there is nothing to re-derive and therefore
 * nothing to get subtly wrong.
 *
 * HONESTY CONTRACT (inherited, never re-implemented)
 * --------------------------------------------------
 *   render    -> says "Try On", opens the studio.
 *   fit_check -> RELABELS to the fit-check wording and opens the ruler flow.
 *                It never says "Try On" when it will not try on.
 *   blocked   -> disabled, titled with the backend's own reason.
 */

export type TryOnButtonVariant = "icon" | "compact" | "full";

export interface TryOnButtonProps {
  /** The garment to try. Partial products are accepted: wardrobe
   *  recommendations and saved-look items carry fewer fields than a catalogue
   *  row, and refusing them is what left those surfaces with no control. */
  product: Partial<Product> & { id?: number; title?: string };
  variant?: TryOnButtonVariant;
  className?: string;
  /** Overrides the accessible label; defaults to the CTA text. */
  ariaLabel?: string;
}

const VARIANT_CLASS: Record<TryOnButtonVariant, string> = {
  icon:
    "p-2 rounded-full bg-[#1B1F3B]/90 hover:bg-[#C5A059] text-white " +
    "hover:text-slate-950 shadow-sm backdrop-blur-xs",
  compact:
    "px-2.5 py-1.5 rounded-lg border border-[#7A5C28]/40 bg-[#FDF8EE] " +
    "text-[#7A5C28] hover:bg-[#7A5C28] hover:text-white text-[11px] font-semibold",
  full:
    "py-2.5 px-3 rounded-xl border border-[#7A5C28]/40 bg-[#FDF8EE] " +
    "text-[#7A5C28] hover:bg-[#7A5C28] hover:text-white text-xs font-semibold",
};

export const TryOnButton: React.FC<TryOnButtonProps> = ({
  product,
  variant = "compact",
  className = "",
  ariaLabel,
}) => {
  const { t } = useTranslation();
  const { openTryOn, openRuler } = useUIStore();
  const tryOn = useTryOnAvailability();
  // `true`: every surface using this button also offers the ruler, so a
  // non-rendering engine degrades to fit-check instead of a dead control.
  const kind = tryOn.ctaKind(true);

  const label = t(kind === "render" ? "tryon.cta_try_on" : "tryon.cta_fit_check");
  const Glyph = kind === "render" ? TryOnIcon : RulerIcon;
  const title =
    kind === "blocked" && tryOn.userMessage
      ? resolveMessage(tryOn.userMessage, t)
      : label;

  const onClick = tryOn.gate({
    render: () => openTryOn(product as Product),
    fitCheck: () => openRuler(product as Product),
  });

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={kind === "blocked"}
      title={title}
      aria-label={ariaLabel ?? label}
      data-testid="try-on-button"
      className={[
        "transition-all inline-flex items-center justify-center gap-1.5",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        VARIANT_CLASS[variant],
        className,
      ].join(" ")}
    >
      <Glyph size={variant === "full" ? 14 : 13} color="currentColor" />
      {variant !== "icon" && <span>{label}</span>}
    </button>
  );
};

export default TryOnButton;
