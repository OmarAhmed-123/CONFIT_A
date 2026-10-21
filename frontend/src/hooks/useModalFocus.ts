import { useEffect, useRef } from 'react';

/**
 * P1-05 (a11y): keyboard + focus + AT background-isolation contract for modal dialogs.
 *
 * WCAG 2.1/2.2 keyboard & name/role/value operability (2.1.1, 2.1.2, 4.1.2): every modal must
 *  - close on Escape,
 *  - keep Tab focus trapped inside the panel (no keyboard escape to background),
 *  - hide outside sibling subtrees from assistive-technology browse/virtual cursors
 *    (`Orca` AT-SPI2, `NVDA`, `JAWS`, `VoiceOver`, `TalkBack`) while preserving live regions,
 *  - move focus into the panel on open and restore it to the opener on close.
 *
 * Stacked modals (e.g. stylist drawer opens try-on): only the modal that
 * currently owns focus reacts — guard via `node.contains(activeElement)`.
 */
const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function isLiveRegionElement(el: Element): boolean {
  const role = el.getAttribute('role');
  if (role === 'alert' || role === 'status' || role === 'log') return true;
  if (el.hasAttribute('aria-live')) return true;
  if (el.querySelector('[aria-live], [role="alert"], [role="status"]')) return true;
  return false;
}

export function useModalFocus<T extends HTMLElement>(onClose: () => void, active = true) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    if (!active) return;
    const node = ref.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    // Hide sibling subtrees along the ancestor path from AT virtual cursors
    // while keeping live announcers and ancestor containers intact.
    const restoredSiblings: Array<{ el: Element; prev: string | null }> = [];
    if (node) {
      let cur: Element | null = node;
      while (cur && cur !== document.body && cur.parentElement) {
        const parentEl: HTMLElement = cur.parentElement;
        for (const sibling of Array.from(parentEl.children)) {
          if (
            sibling === cur ||
            sibling.tagName === 'SCRIPT' ||
            sibling.tagName === 'STYLE' ||
            isLiveRegionElement(sibling)
          ) {
            continue;
          }
          restoredSiblings.push({
            el: sibling,
            prev: sibling.getAttribute('aria-hidden'),
          });
          sibling.setAttribute('aria-hidden', 'true');
          sibling.setAttribute('data-modal-aria-hidden', 'true');
        }
        cur = parentEl;
      }
    }

    const focusables = node ? Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)) : [];
    (focusables[0] ?? node)?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (!node) return;
      if (!node.contains(document.activeElement)) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
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
      for (const { el, prev } of restoredSiblings) {
        el.removeAttribute('data-modal-aria-hidden');
        if (prev === null) {
          el.removeAttribute('aria-hidden');
        } else {
          el.setAttribute('aria-hidden', prev);
        }
      }
      previouslyFocused?.focus?.();
    };
  }, [onClose, active]);

  return ref;
}
