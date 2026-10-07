import { useState } from "react";

/**
 * The ONE device-side wishlist.
 *
 * WHY THIS EXISTS (C03 finding, 2026-10-08)
 * -----------------------------------------
 * Discover persisted hearts to localStorage while the product page kept
 * them in a bare useState(false): the SAME product looked saved on the
 * grid and unsaved on its own page, and the PDP heart silently reset on
 * every reload — a dead control pretending to save. Two surfaces, two
 * truths. The storage key, the parse guard and the toggle rule now live
 * here once (DRY), so every surface reads and writes the same list.
 *
 * HONESTY CEILING
 * ---------------
 * No wishlist API exists (documented gap) — localStorage is the honest
 * ceiling, and copy must say "on this device", never imply an account
 * sync.
 */
export const WISHLIST_STORAGE_KEY = "confit.wishlist.v1";

function readWishlist(): number[] {
  try {
    const raw = window.localStorage.getItem(WISHLIST_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((n) => typeof n === "number")
      : [];
  } catch {
    return [];
  }
}

export function useDeviceWishlist() {
  const [wishlist, setWishlist] = useState<number[]>(readWishlist);

  const toggleWishlist = (productId: number) => {
    setWishlist((prev) => {
      const next = prev.includes(productId)
        ? prev.filter((id) => id !== productId)
        : [...prev, productId];
      try {
        window.localStorage.setItem(
          WISHLIST_STORAGE_KEY,
          JSON.stringify(next),
        );
      } catch {
        // Private mode / quota: the in-memory state still works for the
        // session; nothing to claim beyond that.
      }
      return next;
    });
  };

  const isWishlisted = (productId: number) => wishlist.includes(productId);

  return { wishlist, toggleWishlist, isWishlisted };
}
