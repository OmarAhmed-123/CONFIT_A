import { useCallback, useEffect, useState } from "react";
import i18n from "../i18n/i18n";
import { profileService } from "../services/apiServices";
import { useAuthStore } from "../stores/authStore";
import { useUIStore } from "../stores/uiStore";

/**
 * Unified Favorites / Wishlist hook across grid cards, quick actions & PDP.
 *
 * Behaviour:
 * - Guest sessions persist optimistically in `localStorage` (`confit.wishlist.v1`)
 *   and broadcast updates across every mounted component in real time.
 * - Authenticated sessions merge any device items onto `/api/v1/me/wishlist/sync`
 *   on sign-in without duplicating existing items, clear the anonymous device
 *   cache once merged so shared devices never leak saved items across accounts,
 *   perform optimistic `PUT` / `DELETE` mutations with automatic rollback + error
 *   surfacing on failure, and clear state cleanly on sign-out.
 */
export const WISHLIST_STORAGE_KEY = "confit.wishlist.v1";

type Listener = () => void;

const listeners = new Set<Listener>();
let memoryWishlist: number[] | null = null;
let syncedForUserId: number | null = null;
let syncInFlight: Promise<void> | null = null;

function readStorageWishlist(): number[] {
  try {
    const raw = window.localStorage.getItem(WISHLIST_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? Array.from(new Set(parsed.filter((n) => typeof n === "number" && Number.isFinite(n))))
      : [];
  } catch {
    return [];
  }
}

function writeStorageWishlist(ids: number[]): void {
  try {
    if (ids.length === 0) {
      window.localStorage.removeItem(WISHLIST_STORAGE_KEY);
    } else {
      window.localStorage.setItem(WISHLIST_STORAGE_KEY, JSON.stringify(ids));
    }
  } catch {
    // Private browsing or quota errors degrade cleanly to session state.
  }
}

function getSnapshot(): number[] {
  if (memoryWishlist === null) {
    memoryWishlist = readStorageWishlist();
  }
  return memoryWishlist;
}

function publishWishlist(next: number[], persistLocal: boolean): void {
  const deduped = Array.from(new Set(next));
  memoryWishlist = deduped;
  if (persistLocal) {
    writeStorageWishlist(deduped);
  }
  listeners.forEach((fn) => fn());
}

/** Test-friendly reset helper when tests seed `localStorage` directly between cases. */
export function resetWishlistCacheForTests(): void {
  memoryWishlist = null;
  syncedForUserId = null;
  syncInFlight = null;
}

export function useDeviceWishlist() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const userId = useAuthStore((s) => s.user?.id ?? null);

  // Re-read localStorage on fresh mount when unauthenticated so unit tests that
  // populate localStorage before rendering see those IDs immediately.
  const [wishlist, setWishlist] = useState<number[]>(() => {
    if (!isAuthenticated) {
      const fresh = readStorageWishlist();
      memoryWishlist = fresh;
      return fresh;
    }
    return getSnapshot();
  });
  const [wishlistError, setWishlistError] = useState<boolean>(false);

  useEffect(() => {
    const onChange = () => setWishlist(getSnapshot());
    listeners.add(onChange);
    return () => {
      listeners.delete(onChange);
    };
  }, []);

  useEffect(() => {
    // Logout transition: clear account state so another shopper on this device
    // never sees the previous user's wishlist.
    if (!isAuthenticated || !userId) {
      if (syncedForUserId !== null) {
        syncedForUserId = null;
        publishWishlist([], true);
      }
      return;
    }

    if (syncedForUserId === userId) {
      return;
    }

    if (!syncInFlight) {
      const guestSeed = readStorageWishlist();
      syncedForUserId = userId;
      syncInFlight = (async () => {
        try {
          const response =
            guestSeed.length > 0
              ? await profileService.syncWishlist(guestSeed)
              : await profileService.getWishlist();
          writeStorageWishlist([]);
          publishWishlist(response.product_ids ?? [], false);
          setWishlistError(false);
        } catch {
          // Keep optimistic seed visible if offline during bootstrap.
          syncedForUserId = null;
        } finally {
          syncInFlight = null;
        }
      })();
    }
  }, [isAuthenticated, userId]);

  const toggleWishlist = useCallback(
    (productId: number) => {
      setWishlistError(false);
      const prev = getSnapshot();
      const removing = prev.includes(productId);
      const optimistic = removing
        ? prev.filter((id) => id !== productId)
        : [...prev, productId];

      publishWishlist(optimistic, !isAuthenticated);

      if (isAuthenticated && userId) {
        const op = removing
          ? profileService.removeWishlistItem(productId)
          : profileService.addWishlistItem(productId);
        void op
          .then((res) => {
            if (Array.isArray(res?.product_ids)) {
              publishWishlist(res.product_ids, false);
            }
          })
          .catch(() => {
            publishWishlist(prev, false);
            setWishlistError(true);
            useUIStore.getState().showToast(i18n.t("wishlist.sync_failed"), "error");
          });
      }

      return optimistic;
    },
    [isAuthenticated, userId],
  );

  const isWishlisted = useCallback(
    (productId: number) => wishlist.includes(productId),
    [wishlist],
  );

  return { wishlist, toggleWishlist, isWishlisted, wishlistError };
}
