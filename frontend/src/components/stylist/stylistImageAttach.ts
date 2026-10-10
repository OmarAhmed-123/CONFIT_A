/**
 * Client-side pre-check for stylist photo attachments (Mode A).
 *
 * This mirrors the backend limits in `backend/app/services/stylist_image_intake.py`
 * so the shopper gets an immediate, specific reason. The backend remains the
 * authority: it re-validates the bytes, screens every image for safety, and
 * refuses anything it cannot decode.
 */
export const STYLIST_ATTACH_MAX_IMAGES = 3;
export const STYLIST_ATTACH_MAX_BYTES = 1024 * 1024;
export const STYLIST_ATTACH_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

export type StylistAttachError = "type" | "size" | "count";

export function validateStylistImage(
  file: { type: string; size: number },
  alreadyAttached: number,
): StylistAttachError | null {
  if (alreadyAttached >= STYLIST_ATTACH_MAX_IMAGES) return "count";
  if (!(STYLIST_ATTACH_TYPES as readonly string[]).includes(file.type)) return "type";
  if (file.size > STYLIST_ATTACH_MAX_BYTES) return "size";
  return null;
}

export function readAsDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
