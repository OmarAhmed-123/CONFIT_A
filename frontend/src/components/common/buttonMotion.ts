/**
 * Button Motion System — the typed contract for `src/styles/button-motion.css`.
 *
 * WHY THIS MODULE EXISTS
 * ----------------------
 * The animation engine is CSS, but an animation that is only CSS cannot be
 * reviewed, counted or tested: a typo in `data-motion="finacial"` produces a
 * perfectly silent, unstyled button. So the intents live here as data —
 * a single source of truth that:
 *
 *   · types every `data-motion` value at the call site (the compiler catches
 *     a misspelt intent instead of shipping a dead button);
 *   · lets the button-motion contract test assert that the registry and the
 *     stylesheet describe EXACTLY the same set of intents, in both directions
 *     (an intent with no CSS, or CSS with no intent, fails `npm test`);
 *   · keeps the catalog in docs/BUTTON_MOTION_SYSTEM.md mechanically true.
 *
 * No JavaScript animates anything here. This module only returns attribute
 * names; the paint is 100% CSS.
 */

/**
 * The functional families every button in CONFIT belongs to. Grouped by what
 * the control DOES, not by where it lives — the same `destructive` recipe
 * therefore governs a consumer's "Remove item" and an admin's "Revoke key".
 */
export const BUTTON_INTENTS = [
  /** Forward motion: create, save, continue, submit — growth + trust. */
  "progressive",
  /** Generative surfaces: try-on, stylist, generate, complete-the-look. */
  "creative",
  /** Money: checkout, place order, pay, wallet. Gold, and never rushed. */
  "financial",
  /** Irreversible harm: delete, revoke, archive, disconnect. Rose + amber. */
  "destructive",
  /** Authority verbs: approve, publish, feature, verify, bulk-run. Navy→gold. */
  "admin",
  /** The control gains content: upload, import, capture, attach. */
  "upload",
  /** The control releases content: download, export, invoice, report. */
  "download",
  /** Outward hand-off: share, invite, copy link, refer. */
  "share",
  /** Second chances: retry, refresh, resend, restore, undo. Amber→green. */
  "recovery",
  /** Identity: sign in, sign up, verify, OTP, password, MFA. */
  "auth",
  /** Cancels, closes, dismissals, steppers, pagination — deliberate chrome. */
  "neutral",
  /** Chips, segments, tabs, sort toggles: a rule under the label, not a wash. */
  "filter",
  /** Bag and wardrobe verbs: add to bag, wishlist, quantity. */
  "commerce",
] as const;

export type ButtonIntent = (typeof BUTTON_INTENTS)[number];

/**
 * Geometry variants. `icon` makes the wash bloom from the centre of the target
 * (an icon-only control has no label to sweep behind); `quiet` is the
 * whisper-quiet presence a dense admin table row needs.
 */
export const BUTTON_MOTION_TONES = ["auto", "icon", "quiet"] as const;
export type ButtonMotionTone = (typeof BUTTON_MOTION_TONES)[number];

/**
 * The app's own vocabulary for a phase (`pending`, `done`, `failed`, …) mapped
 * onto the engine's three states. A surface that already tracks a phase can
 * therefore drive the animation without inventing a second state machine.
 * Anything unrecognised returns `undefined` — no attribute, no animation,
 * no invented state.
 */
export type MotionState = "loading" | "success" | "error" | "quiet";

const PHASE_ALIASES: Record<string, MotionState | undefined> = {
  idle: undefined, // explicit: idle is the absence of a state, not a 5th one
  loading: "loading",
  pending: "loading",
  busy: "loading",
  running: "loading",
  uploading: "loading",
  rendering: "loading",
  success: "success",
  done: "success",
  complete: "success",
  saved: "success",
  error: "error",
  failed: "error",
  failure: "error",
  offline: "error",
  unavailable: "quiet",
  unauthorized: "quiet",
  blocked: "quiet",
};

export type MotionPhase =
  | "idle"
  | "loading"
  | "pending"
  | "busy"
  | "running"
  | "uploading"
  | "rendering"
  | "success"
  | "done"
  | "complete"
  | "saved"
  | "error"
  | "failed"
  | "failure"
  | "offline"
  | "unavailable"
  | "unauthorized"
  | "blocked"
  | (string & {});

export function motionStateAlias(
  phase: MotionPhase | undefined | null,
): MotionState | undefined {
  if (!phase) return undefined;
  return PHASE_ALIASES[phase];
}

export interface ButtonMotionOptions {
  intent: ButtonIntent;
  tone?: ButtonMotionTone;
  /** Optional explicit state, for surfaces that own their own phase. */
  phase?: MotionPhase | undefined | null;
}

export interface ButtonMotionAttributes {
  "data-motion": ButtonIntent;
  "data-motion-tone"?: ButtonMotionTone;
  "data-motion-state"?: MotionState;
}

/**
 * Spread onto a `<button>`:
 *
 *     <button {...buttonMotion({ intent: "financial" })}>Pay now</button>
 *
 * Attributes the engine already reads from the platform (`:hover`,
 * `:focus-visible`, `:active`, `:disabled`, `aria-busy`) are NOT duplicated
 * here — an animation must never be the only place a state is recorded.
 */
export function buttonMotion({
  intent,
  tone = "auto",
  phase,
}: ButtonMotionOptions): ButtonMotionAttributes {
  const state = motionStateAlias(phase);
  return {
    "data-motion": intent,
    ...(tone !== "auto" ? { "data-motion-tone": tone } : {}),
    ...(state ? { "data-motion-state": state } : {}),
  };
}

/** True when `value` is a registered intent — used by tests and the codemod. */
export function isButtonIntent(value: string): value is ButtonIntent {
  return (BUTTON_INTENTS as readonly string[]).includes(value);
}
