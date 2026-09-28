import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "../services/apiClient";

/**
 * Makes catalogue changes reach every role without waiting out the cache.
 *
 * WHY THIS EXISTS
 * ---------------
 * Catalogue queries cache with `staleTime: 5 minutes`. That is right for
 * bandwidth and wrong for stock. When a brand sold out a size or changed a
 * price, everyone else — shoppers browsing, an admin auditing, a second brand
 * user on the same tenant — kept rendering the OLD value for up to five
 * minutes with no signal that it was stale. A shopper could add a sold-out
 * size to their bag and only discover it at checkout.
 *
 * The naive fixes are both bad: dropping `staleTime` refetches the whole
 * catalogue constantly, and a websocket is a lot of infrastructure for a
 * value that changes a few times an hour.
 *
 * So the client polls ONE tiny endpoint that returns a hash over the fields
 * shoppers actually see — stock levels, in-stock flags, prices, sale prices,
 * store quantities — and invalidates the real queries only when that hash
 * moves. Steady state costs one small request per interval and zero refetches.
 *
 * SCOPE
 * -----
 * Mounted once, at the app root, so it serves every role from one place
 * rather than each view re-implementing its own freshness rule. The queries it
 * invalidates are the shared catalogue keys, so consumer and B2B surfaces both
 * refresh from the same signal.
 *
 * HONESTY
 * -------
 * This is polling, not push: a change is visible within one interval, not
 * instantly. Stated rather than described as "real-time", because it is not.
 */

export interface CatalogRevision {
  revision: string;
  counts: {
    products: number;
    skus: number;
    store_inventory_rows: number;
  };
  sellable_units: number;
  store_units: number;
  reserved_units: number;
}

/** Fast enough that a shopper rarely acts on stale stock, cheap enough to run always. */
export const CATALOG_REVISION_POLL_MS = 30_000;

/** Query keys invalidated when the catalogue fingerprint moves. */
// Prefix keys: react-query invalidates by prefix, so ['catalog'] covers every
// filtered product list without enumerating filter permutations.
const INVALIDATED_ON_CHANGE: string[][] = [
  ["catalog", "products"],
  ["catalog", "categories"],
  ["brand", "inventory"],
  ["brand", "products"],
  ["admin", "catalog"],
];

export function useCatalogRevision(enabled: boolean = true) {
  const queryClient = useQueryClient();
  const lastSeen = useRef<string | null>(null);

  const query = useQuery({
    queryKey: ["catalog", "revision"],
    queryFn: () => request<CatalogRevision>("/catalog/revision"),
    refetchInterval: CATALOG_REVISION_POLL_MS,
    // The point of this hook is to notice change, so its own answer is never
    // served from cache.
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: true,
    // A failing fingerprint must not surface as a user-visible error: the
    // catalogue still renders, it is only freshness that degrades.
    retry: 1,
    enabled,
  });

  const revision = query.data?.revision ?? null;

  useEffect(() => {
    if (!revision) return;

    // First observation establishes the baseline. Invalidating here would
    // throw away a cache that was just populated, on every mount.
    if (lastSeen.current === null) {
      lastSeen.current = revision;
      return;
    }
    if (lastSeen.current === revision) return;

    lastSeen.current = revision;
    for (const key of INVALIDATED_ON_CHANGE) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  }, [revision, queryClient]);

  return {
    revision,
    /** Null until the first successful poll — never reported as zero. */
    sellableUnits: query.data?.sellable_units ?? null,
    isPolling: query.isFetching,
    error: query.error,
  };
}
