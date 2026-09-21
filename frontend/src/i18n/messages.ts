/**
 * TranslatableMessage — the transport type for every user-facing string that
 * is produced OUTSIDE a React render (Zustand stores, view-models, service
 * libs) and rendered LATER by a component.
 *
 * WHY THIS EXISTS (audit 2026-09-21, finding "النصوص الإرشادية وحالات
 * loading/error" / i18n parity):
 *   The UI was 100% bilingual in its JSX but its *toasts and error messages*
 *   were built as English template literals —
 *   `showToast(\`No purchasable size found for ${product.title}\`)` — in 60+
 *   call sites. Those strings never passed through i18n, so an Arabic user got
 *   an Arabic page with English failure messages. The audit could not see it
 *   because nothing measured the non-JSX surface.
 *
 *   The root cause was architectural, not cosmetic: a store has no `t()`
 *   function, so the only thing it could do was concatenate English. The fix
 *   is to move translation to the render boundary — stores emit a *descriptor*
 *   (key + interpolation params), and the component that renders it resolves
 *   the key in the user's active language.
 *
 * CONTRACT:
 *   - A store/VM never concatenates a user-facing sentence.
 *   - Params are flat scalars: no HTML, no nested React nodes.
 *   - A raw `string` is still accepted so pre-existing call sites keep
 *     compiling, but the i18n CI gate fails the build when a NEW raw English
 *     literal appears in a `showToast(...)`, `message:`, or `new Error(...)`
 *     user-facing slot. See scripts/check_i18n.mjs.
 */

export type MessageParams = Record<string, string | number>;

export interface MessageDescriptor {
  /** Dotted i18n key, e.g. `toast.no_purchasable_size_for`. */
  key: string;
  /** Interpolation values — flat scalars only. */
  params?: MessageParams;
  /**
   * Last-resort text when even the source locale lacks the key. Never English
   * prose invented ad hoc: this is for genuinely un-keyed technical detail
   * (e.g. an upstream error string) that must not be swallowed.
   */
  fallback?: string;
}

export type TranslatableMessage = string | MessageDescriptor;

export function isMessageDescriptor(value: unknown): value is MessageDescriptor {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as MessageDescriptor).key === 'string' &&
    (value as MessageDescriptor).key.length > 0
  );
}

/** Build a descriptor. Keeps call sites short and type-checked. */
export function msg(key: string, params?: MessageParams): MessageDescriptor {
  return params ? { key, params } : { key };
}

/**
 * Wrap an upstream/technical string (a server message, a caught Error) as an
 * interpolation value for a keyed sentence, so the surrounding text stays
 * translated even when the inner detail cannot be.
 *
 * The result is truncated: server messages have been observed to be full
 * stack traces in some deployment modes (see useTryOnViewModel), and a toast
 * is not a log sink.
 */
export function detail(value: unknown, maxLength = 160): string {
  const raw =
    value instanceof Error
      ? value.message
      : typeof value === 'string'
        ? value
        : value == null
          ? ''
          : String(value);
  const flat = raw.replace(/\s+/g, ' ').trim();
  return flat.length > maxLength ? `${flat.slice(0, maxLength - 1)}…` : flat;
}

/**
 * Resolve a TranslatableMessage to display text.
 *
 * `t` is the bound i18next translator. Descriptors resolve through it; plain
 * strings pass through untouched (legacy call sites). A descriptor whose key
 * is absent everywhere falls back to `fallback`, then to the last dotted
 * segment humanized — the same "never render a raw key" contract the i18n
 * init already enforces for JSX.
 */
export function resolveMessage(
  message: TranslatableMessage,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (!isMessageDescriptor(message)) return message;
  const translated = t(message.key, message.params);
  // i18next returns the key itself when nothing matched and no handler ran.
  if (translated && translated !== message.key) return translated;
  if (message.fallback) return message.fallback;
  return humanizeKey(message.key);
}

export function humanizeKey(key: string): string {
  const leaf = key.split('.').pop() || key;
  return leaf.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * An Error that carries a translatable descriptor alongside its (English,
 * source-locale) `message`.
 *
 * WHY: libraries such as lib/imageUpload.ts and lib/checkoutValidation.ts are
 * pure modules with no access to a React context or the i18next singleton at
 * call time. Throwing a plain `Error('That image appears to be corrupted.')`
 * hard-codes English into the only thing the UI could display. Carrying the
 * descriptor keeps `message` useful for logs and stack traces while giving the
 * render boundary a key it can translate.
 */
export class LocalizedError extends Error {
  readonly translatable: MessageDescriptor;

  constructor(translatable: MessageDescriptor, sourceMessage?: string) {
    super(sourceMessage ?? humanizeKey(translatable.key));
    this.name = 'LocalizedError';
    this.translatable = translatable;
  }
}

/** Narrow an unknown throw to a descriptor, with an honest generic fallback. */
export function translatableFrom(error: unknown, fallbackKey = 'errors.generic'): TranslatableMessage {
  if (error instanceof LocalizedError) return error.translatable;
  const d = detail(error);
  return d ? { key: fallbackKey, params: { reason: d } } : { key: fallbackKey };
}
