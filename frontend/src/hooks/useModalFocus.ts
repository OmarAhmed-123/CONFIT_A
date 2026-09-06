import { useEffect, useRef } from 'react';

/**
 * P1-05 (a11y): keyboard + focus contract for modal dialogs.
 *
 * WCAG 2.1/2.2 keyboard operability (2.1.1/2.1.2): every modal must
 *  - close on Escape,
 *  - keep Tab focus trapped inside the panel (no keyboard escape to background),
 *  - move focus into the panel on open and restore it to the opener on close.
 *
 * Stacked modals (e.g. stylist drawer opens try-on): only the modal that
 * currently owns focus reacts — guard via `node.contains(activeElement)`.
 */
const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useModalFocus<T extends HTMLElement>(onClose: () => void, active = true) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    if (!active) return;
    const node = ref.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = node ? Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)) : [];
    (focusables[0] ?? node)?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (!node) return;
      // Only the focused (top-most) modal may react — see docblock.
      if (!node.contains(document.activeElement)) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      // The selector itself excludes disabled controls; no visibility filter —
      // jsdom has no layout, and hidden-but-focusable elements are the caller's
      // markup responsibility (panels here are always visible while open).
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      previouslyFocused?.focus?.();
    };
  }, [onClose, active]);

  return ref;
}
