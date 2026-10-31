import type { TFunction } from "i18next";

/** Backend colour family sentinel for garments whose colour could not be classified. */
export const UNKNOWN_COLOR = "Unknown";

/**
 * Human label for a stored colour family. Known families are shown as stored;
 * the Unknown sentinel is localised so the UI never prints a bare "Unknown"
 * (or pretends a colour was identified).
 */
export function colorLabel(colorName: string | null | undefined, t: TFunction): string {
  if (!colorName || colorName === UNKNOWN_COLOR) return t("wardrobe.color_unknown");
  return colorName;
}
