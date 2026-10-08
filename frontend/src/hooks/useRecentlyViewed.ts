import { useEffect, useMemo, useState } from "react";
import { Product } from "../models";

/**
 * Recently-viewed pieces — DEVICE-LOCAL, like the wishlist
 * (useDeviceWishlist): there is no server endpoint for browse history
 * in this deployment, so nothing is invented and nothing leaves the
 * device. Snapshots (not ids) are stored so the rail renders without
 * N extra API calls; price/title may age, but every card links to the
 * live product page, which is the source of truth.
 *
 * Contract:
 *   · MRU first, deduped by id, capped at MAX_RECENT.
 *   · The CURRENT product is recorded but never shown to itself.
 *   · Corrupt storage degrades to an empty list, never a crash.
 */
export const RECENTLY_VIEWED_STORAGE_KEY = "confit.recently_viewed.v1";
export const MAX_RECENT = 8;

export interface RecentlyViewedSnapshot {
  id: number;
  slug: string;
  title: string;
  title_ar?: string;
  thumbnail_url: string;
  base_price: number;
  currency: string;
}

function readAll(): RecentlyViewedSnapshot[] {
  try {
    const raw = window.localStorage.getItem(RECENTLY_VIEWED_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (s): s is RecentlyViewedSnapshot =>
        !!s && typeof s.id === "number" && typeof s.slug === "string",
    );
  } catch {
    return [];
  }
}

/**
 * Records `product` into the device history when it loads and returns
 * the OTHER recently viewed snapshots for the rail.
 */
export function useRecentlyViewed(
  product: Product | null,
): RecentlyViewedSnapshot[] {
  const [items, setItems] = useState<RecentlyViewedSnapshot[]>(() =>
    typeof window === "undefined" ? [] : readAll(),
  );

  useEffect(() => {
    if (!product) return;
    const snapshot: RecentlyViewedSnapshot = {
      id: product.id,
      slug: product.slug,
      title: product.title,
      title_ar: product.title_ar,
      thumbnail_url: product.thumbnail_url,
      base_price: product.base_price,
      currency: product.currency,
    };
    const next = [
      snapshot,
      ...readAll().filter((s) => s.id !== product.id),
    ].slice(0, MAX_RECENT);
    try {
      window.localStorage.setItem(
        RECENTLY_VIEWED_STORAGE_KEY,
        JSON.stringify(next),
      );
    } catch {
      /* storage full/blocked: the rail is a convenience, never an error */
    }
    setItems(next);
  }, [product]);

  return useMemo(
    () => (product ? items.filter((s) => s.id !== product.id) : items),
    [items, product],
  );
}
