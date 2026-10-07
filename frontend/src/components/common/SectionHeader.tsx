import React from "react";
import { Link } from "react-router-dom";

/**
 * SectionHeader — the single authority for every curated-section header.
 *
 * Before this component HomeView carried FIVE hand-rolled copies of the
 * same "eyebrow / serif title / border / view-all →" block, each subtly
 * different: some arrows lacked aria-hidden, none flipped in RTL (the
 * project convention is `rtl:rotate-180`, see AccessibleCarousel), and the
 * action links were ~32px tall — under the 44px touch floor this design
 * system promises. One component now owns the geometry, the easing token
 * (ease-luxury) and the a11y contract; call sites only supply content.
 *
 * Functional: optional eyebrow/hint/icon; `titleId` for aria-labelledby;
 * action renders a real <Link> when `to` is given, else a <button>.
 * Non-functional: min-h-11 action target, aria-hidden directional glyph
 * with RTL mirror, focus-visible ring, variable-length titles never break
 * alignment (items-end + flex-wrap on the row).
 */
export interface SectionHeaderAction {
  label: string;
  to?: string;
  onClick?: () => void;
}

export const SectionHeader: React.FC<{
  title: string;
  titleId?: string;
  eyebrow?: string;
  hint?: string;
  icon?: React.ReactNode;
  action?: SectionHeaderAction;
}> = ({ title, titleId, eyebrow, hint, icon, action }) => {
  const actionInner = action ? (
    <>
      <span>{action.label}</span>
      <span
        aria-hidden="true"
        className="rtl:rotate-180 transition-transform duration-300 ease-luxury group-hover/shaction:translate-x-1 rtl:group-hover/shaction:-translate-x-1"
      >
        →
      </span>
    </>
  ) : null;
  const actionClass =
    "group/shaction inline-flex min-h-11 items-center gap-1 self-start text-xs font-semibold text-[#1B1F3B] transition-colors duration-300 ease-luxury hover:text-[#C5A059] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] rounded-lg sm:self-auto";

  return (
    <div className="flex flex-col justify-between gap-2 border-b border-slate-200/80 pb-4 sm:flex-row sm:items-end">
      <div>
        {eyebrow && (
          <span className="block text-[10px] font-bold uppercase tracking-widest text-[#7A5C28]">
            {eyebrow}
          </span>
        )}
        <div className="mt-1 flex items-center gap-2">
          {icon && <span aria-hidden="true">{icon}</span>}
          <h2
            id={titleId}
            className="font-serif text-2xl font-bold text-[#1B1F3B]"
          >
            {title}
          </h2>
        </div>
        {hint && (
          <p className="mt-0.5 text-xs font-light text-slate-500 sm:text-sm">
            {hint}
          </p>
        )}
      </div>

      {action &&
        (action.to ? (
          <Link to={action.to} className={actionClass}>
            {actionInner}
          </Link>
        ) : (
          <button type="button" onClick={action.onClick} className={actionClass}>
            {actionInner}
          </button>
        ))}
    </div>
  );
};
