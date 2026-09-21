import React from 'react';
import { useTranslation } from 'react-i18next';

/**
 * SkipLink — WCAG 2.4.1 Bypass Blocks (Level A).
 *
 * WHY: the consumer shell renders a full navigation bar, a language switcher,
 * a search control, a cart control and a floating stylist button BEFORE the
 * page content. A keyboard user had to tab through every one of them on every
 * single navigation to reach the page they asked for. The audit recorded that
 * keyboard traversal was never tested; this is the standard remedy.
 *
 * IMPLEMENTATION NOTES (both are the usual reasons a skip link silently does
 * nothing):
 *   1. It is hidden with `sr-only`, NOT `display:none` / `visibility:hidden`.
 *      Both of those remove the element from the tab order, so the link could
 *      never be reached in the first place.
 *   2. The target must be focusable. `MainContent` (see layouts) carries
 *      `tabIndex={-1}`, so activating the link MOVES FOCUS rather than only
 *      scrolling — a skip link that scrolls without moving focus leaves the
 *      user's next Tab back at the top of the nav.
 *
 * Placed as the first focusable element inside each layout, before the header.
 */
export const SKIP_TARGET_ID = 'confit-main-content';

export const SkipLink: React.FC<{ targetId?: string }> = ({ targetId = SKIP_TARGET_ID }) => {
  const { t } = useTranslation();
  return (
    <a
      href={`#${targetId}`}
      data-testid="skip-link"
      className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:start-3 focus:z-[100] focus:px-4 focus:py-2.5 focus:rounded-xl focus:bg-[#1B1F3B] focus:text-white focus:text-xs focus:font-bold focus:shadow-2xl focus:border focus:border-[#C5A059]"
    >
      {t('a11y.skip_to_content')}
    </a>
  );
};
