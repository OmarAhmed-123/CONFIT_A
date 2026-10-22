/**
 * The "we have no answer" capabilities object.
 *
 * Why this lives in its own module instead of `useCapabilities.ts`:
 *
 * `AnnouncementSlot` must tell a FAILED fetch apart from a real answer that
 * happens to say "no free-shipping policy". Both arrive with
 * `free_shipping_threshold: null` and `shipping_currency: null` — identical by
 * value. The only honest signal is object identity against this sentinel.
 *
 * A component that imported the sentinel from the hook module broke every
 * existing test that mocks `useCapabilities` (a `vi.mock` factory replaces the
 * whole module, so the constant stopped existing and the component threw).
 * Requiring each such test to re-export an internal sentinel would make a
 * layout detail responsible for dozens of unrelated mocks. The constant is data,
 * not hook behaviour, so it belongs in a module nobody has a reason to mock.
 */
import type { Capabilities } from './useCapabilities';

export const HONEST_FALLBACK_CAPABILITIES: Capabilities = {
  payments_live: false,
  payments_live_methods: [],
  cod_live: false,
  payments_mode: 'demo',
  bnpl_live: false,
  vton_gpu_ready: false,
  vton_engine_state: 'temporarily_unavailable',
  vton_offered: false,
  vton_renderable: false,
  ai_stylist_live: false,
  photo_upload_available: false,
  bopis_live: false,
  bopis_store_count: 0,
  storage_mode: 'local',
  returns_window_days: 30,
  // No flags fetched -> no shipping promise. The honest degradation is an
  // absent announcement, never a stale or invented threshold.
  free_shipping_threshold: null,
  standard_shipping_fee: null,
  shipping_currency: null,
};
