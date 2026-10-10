/**
 * Client-side handling for stylist photo attachments (Mode A).
 *
 * THE CONTRACT THAT STAYS FIXED: at most 3 photos per message, each JPEG, PNG or
 * WebP, and each at most 1 MB once it is sent. The backend enforces the same
 * numbers (`backend/app/services/stylist_image_intake.py`) and remains the
 * authority: it re-decodes every byte and screens every image.
 *
 * WHAT CHANGED: a 1 MB limit on the ORIGINAL file rejected almost every phone
 * photo before it was read. The browser now accepts an ordinary photo (up to
 * STYLIST_ATTACH_MAX_SOURCE_BYTES) and reduces it to fit the 1 MB limit, so the
 * contract is met by what is actually sent. A photo that cannot be reduced is
 * refused with a specific reason, not sent anyway.
 */
export const STYLIST_ATTACH_MAX_IMAGES = 3;
/** Per image, as sent to the backend (decoded bytes). */
export const STYLIST_ATTACH_MAX_BYTES = 1024 * 1024;
/** Largest original the browser will try to reduce. Above this, refuse early. */
export const STYLIST_ATTACH_MAX_SOURCE_BYTES = 20 * 1024 * 1024;
export const STYLIST_ATTACH_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
/** Longest side after resizing. Enough for garment colour and cut. */
export const STYLIST_ATTACH_MAX_SIDE_PX = 1600;

export type StylistAttachError = "type" | "size" | "count" | "source_size";

export function validateStylistImage(
  file: { type: string; size: number },
  alreadyAttached: number,
): StylistAttachError | null {
  if (alreadyAttached >= STYLIST_ATTACH_MAX_IMAGES) return "count";
  if (!(STYLIST_ATTACH_TYPES as readonly string[]).includes(file.type)) return "type";
  if (file.size > STYLIST_ATTACH_MAX_SOURCE_BYTES) return "source_size";
  return null;
}

/** Scale (w, h) so the longer side is at most maxSide. Never enlarges. */
export function targetDimensions(width: number, height: number, maxSide: number): { width: number; height: number } {
  if (width <= 0 || height <= 0) return { width: 0, height: 0 };
  const longest = Math.max(width, height);
  if (longest <= maxSide) return { width, height };
  const scale = maxSide / longest;
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

export function readAsDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export type PreparedImage = { dataUrl: string } | { error: "size" };

/**
 * Returns a data URL no larger than STYLIST_ATTACH_MAX_BYTES, or an error.
 * A photo already within the limit is sent as the shopper chose it.
 * Otherwise it is decoded, resized, and re-encoded as JPEG (white background,
 * so transparency does not turn black), trying lower quality and then a smaller
 * size until it fits.
 */
export async function prepareStylistImage(file: Blob): Promise<PreparedImage> {
  if (file.size <= STYLIST_ATTACH_MAX_BYTES) {
    return { dataUrl: await readAsDataUrl(file) };
  }
  const bitmap = await decodeToBitmap(file);
  if (!bitmap) return { error: "size" };
  try {
    for (const maxSide of [STYLIST_ATTACH_MAX_SIDE_PX, 1024]) {
      const { width, height } = targetDimensions(bitmap.width, bitmap.height, maxSide);
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) return { error: "size" };
      ctx.fillStyle = "#FFFFFF";
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(bitmap, 0, 0, width, height);
      for (const quality of [0.85, 0.75, 0.6]) {
        const blob = await canvasToBlob(canvas, quality);
        if (blob && blob.size <= STYLIST_ATTACH_MAX_BYTES) {
          return { dataUrl: await readAsDataUrl(blob) };
        }
      }
    }
    return { error: "size" };
  } finally {
    bitmap.close?.();
  }
}

async function decodeToBitmap(file: Blob): Promise<ImageBitmap | null> {
  try {
    return await createImageBitmap(file);
  } catch {
    return null;
  }
}

function canvasToBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/jpeg", quality));
}
