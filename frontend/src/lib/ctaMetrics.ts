/**
 * Spec 08 §6.5 — non-sensitive CTA telemetry for product improvement.
 *
 * What is recorded: a STATIC action id (e.g. "builder.save_look"), the
 * wall-clock duration of the attempt, and the outcome word. Nothing else —
 * no payloads, no prices, no emails, no order numbers, no user ids. The
 * buffer is in-memory only (last 50 entries) and is surfaced via
 * `console.debug` in dev builds; nothing is sent anywhere until the
 * project wires a real telemetry endpoint (documented, not invented).
 */
export type CtaMetric = {
  /** Static action identifier — never derived from user data. */
  id: string;
  durationMs: number;
  outcome: string;
  /** Epoch ms, for ordering only. */
  at: number;
};

const MAX_ENTRIES = 50;
const buffer: CtaMetric[] = [];

export function recordCtaMetric(m: Omit<CtaMetric, "at">): void {
  const entry: CtaMetric = { ...m, durationMs: Math.round(m.durationMs), at: Date.now() };
  buffer.push(entry);
  if (buffer.length > MAX_ENTRIES) buffer.shift();
  try {
    if (import.meta.env?.DEV) {
      // eslint-disable-next-line no-console
      console.debug("[cta-metric]", entry.id, entry.outcome, `${entry.durationMs}ms`);
    }
  } catch {
    /* non-Vite environments: metrics stay silent */
  }
}

export function getCtaMetrics(): CtaMetric[] {
  return [...buffer];
}

export function clearCtaMetrics(): void {
  buffer.length = 0;
}
