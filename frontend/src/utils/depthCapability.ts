/**
 * Spec 11 — capability gate for the optional 2.5D depth gallery.
 *
 * The gallery is a P2 "wow moment", never a requirement: ANY doubt about
 * the device downgrades to the static 2D fallback (§5 state contract).
 * Order of checks is the spec's own order and each refusal carries its
 * reason so the UI/tests can assert WHY the fallback rendered:
 *   flag-off → unsupported (no preserve-3d) → low-memory → reduced-motion.
 *
 * No WebGL anywhere (§2): the only capability we need is CSS
 * `transform-style: preserve-3d`, probed through CSS.supports. A missing
 * CSS.supports (ancient engine) counts as unsupported — fail closed.
 */
export type DepthBlockReason =
  | "flag-off"
  | "unsupported"
  | "low-memory"
  | "reduced-motion"
  | null;

export interface DepthCapability {
  ok: boolean;
  reason: DepthBlockReason;
}

/** deviceMemory is a Chromium-only hint (GiB). Absent ⇒ no judgement. */
const LOW_MEMORY_GIB = 2;

export function assessDepthCapability(opts: {
  flagOn: boolean;
  reduceMotion: boolean;
}): DepthCapability {
  if (!opts.flagOn) return { ok: false, reason: "flag-off" };

  const supports3D =
    typeof CSS !== "undefined" &&
    typeof CSS.supports === "function" &&
    CSS.supports("transform-style", "preserve-3d");
  if (!supports3D) return { ok: false, reason: "unsupported" };

  const mem = (navigator as Navigator & { deviceMemory?: number })
    .deviceMemory;
  if (typeof mem === "number" && mem < LOW_MEMORY_GIB) {
    return { ok: false, reason: "low-memory" };
  }

  if (opts.reduceMotion) return { ok: false, reason: "reduced-motion" };

  return { ok: true, reason: null };
}

/** Build-time feature flag (safe default: OFF ⇒ 2D everywhere). */
export function isDepthGalleryFlagOn(): boolean {
  return import.meta.env.VITE_ENABLE_DEPTH_GALLERY === "true";
}
