import React from "react";
import { useCatalogRevision } from "../../hooks/useCatalogRevision";

/**
 * Mounts the catalogue freshness poll once, for every role.
 *
 * Renders nothing. It exists because `useCatalogRevision` needs to live
 * INSIDE the QueryClientProvider (it calls `useQueryClient`), and putting a
 * hook call directly in `App` would tie the poll's lifetime to the provider's
 * own render rather than to a component that can be moved or disabled.
 *
 * One mount, one interval, all roles — a shopper, a brand user and an admin
 * all learn about a stock change from the same signal instead of each view
 * inventing its own refresh rule.
 */
export const CatalogFreshness: React.FC = () => {
  useCatalogRevision(true);
  return null;
};

export default CatalogFreshness;
