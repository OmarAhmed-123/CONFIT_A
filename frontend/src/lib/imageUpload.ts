/**
 * Centralized client-side image validation + compression for every upload
 * path (Virtual Try-On person photo, Visual Search, Wardrobe, Body Scan).
 *
 * WHY THIS EXISTS (2026-09-06 audit, P0-02/P0-03):
 *   The Vercel serverless gateway rejects request bodies > ~4.5 MB with
 *   HTTP 413 FUNCTION_PAYLOAD_TOO_LARGE. Modern phone photos are routinely
 *   3–8 MB PNG/JPEG, so the majority of real-world uploads died with an
 *   opaque 413 before ever reaching the API. Every previous upload path
 *   read the raw File via FileReader.readAsDataURL() and sent the bytes
 *   untouched. There was no shared, tested pipeline.
 *
 * CONTRACT:
 *   - Reject non-image MIME types up front (MIME spoofing guard — the
 *     backend re-validates magic bytes; this is UX, not security).
 *   - Downscale the longest edge to `maxDim` (default 1024px — the VTON
 *     worker's working resolution) and re-encode as JPEG q0.85.
 *   - Guarantee the OUTPUT stays under `maxOutputBytes` (default 3 MB,
 *     a safety margin below the 4.5 MB gateway limit including the ~33%
 *     base64 expansion). If one pass is not enough, re-encode at a lower
 *     quality/size until it fits or the floor is hit — then fail honestly.
 *   - NEVER fabricate success: every failure path throws with a message
 *     the UI can show directly.
 */

export interface ImageValidationResult {
  ok: boolean;
  error?: string;
}

export const ALLOWED_IMAGE_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;

/** Raw-file guard before any expensive work (default 20 MB — generous ceiling). */
export const MAX_INPUT_BYTES = 20 * 1024 * 1024;

/**
 * Output ceiling. Base64 inflates by ~4/3, and the JSON envelope adds the
 * rest — 3 MB raw encodes to ~4 MB base64, safely under the ~4.5 MB gateway
 * limit even with the rest of the request payload.
 */
export const MAX_OUTPUT_BYTES = 3 * 1024 * 1024;

export const DEFAULT_MAX_DIM = 1024;
export const DEFAULT_QUALITY = 0.85;
const QUALITY_FLOOR = 0.5;
const MIN_DIM = 256;

export function validateImageFile(file: { type?: string; size?: number; name?: string }): ImageValidationResult {
  const type = (file.type || '').toLowerCase();
  if (!ALLOWED_IMAGE_MIME_TYPES.includes(type as any)) {
    return {
      ok: false,
      error: 'Unsupported image format. Please upload a JPG, PNG or WebP photo.',
    };
  }
  if ((file.size || 0) > MAX_INPUT_BYTES) {
    return {
      ok: false,
      error: `That photo is too large (${(file.size! / (1024 * 1024)).toFixed(1)} MB). The maximum is 20 MB — try a smaller photo.`,
    };
  }
  if ((file.size || 0) === 0) {
    return { ok: false, error: 'The selected file is empty.' };
  }
  return { ok: true };
}

export interface CompressedImage {
  dataUrl: string;
  width: number;
  height: number;
  bytes: number; // approximate decoded output size
  originalBytes: number;
  passes: number;
}

/** Injectable canvas factory so tests can run without a real canvas. */
export type CanvasFactory = (w: number, h: number) => {
  width: number;
  height: number;
  getContext: (type: '2d') => CanvasRenderingContext2D | null;
  toDataURL: (mime: string, quality?: number) => string;
} | null;

const defaultCanvasFactory: CanvasFactory = (w, h) => {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
};

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('That file could not be read as an image.'));
    img.src = src;
  });
}

function readFileAsDataUrl(file: File | Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error('The file could not be read.'));
    reader.readAsDataURL(file);
  });
}

/** Approximate byte size of a data URL's payload. */
export function dataUrlBytes(dataUrl: string): number {
  const idx = dataUrl.indexOf(',');
  if (idx < 0) return 0;
  const b64 = dataUrl.length - idx - 1;
  const padding = b64 >= 2 && dataUrl.endsWith('==') ? 2 : dataUrl.endsWith('=') ? 1 : 0;
  return Math.floor((b64 * 3) / 4) - padding;
}

/**
 * Validate + compress an uploaded image file into a payload-safe data URL.
 * Throws Error with a user-presentable message on any failure.
 */
export async function compressImageToDataUrl(
  file: File | Blob,
  opts: {
    maxDim?: number;
    quality?: number;
    maxOutputBytes?: number;
    canvasFactory?: CanvasFactory;
  } = {}
): Promise<CompressedImage> {
  const validation = validateImageFile(file as File);
  if (!validation.ok) throw new Error(validation.error);

  const maxDim = opts.maxDim ?? DEFAULT_MAX_DIM;
  const maxOutputBytes = opts.maxOutputBytes ?? MAX_OUTPUT_BYTES;
  const canvasFactory = opts.canvasFactory ?? defaultCanvasFactory;

  const sourceUrl = await readFileAsDataUrl(file);
  const img = await loadImage(sourceUrl);
  if (!img.naturalWidth || !img.naturalHeight) {
    throw new Error('That image appears to be corrupted.');
  }

  const originalBytes = file.size ?? dataUrlBytes(sourceUrl);
  let dim = Math.min(maxDim, Math.max(img.naturalWidth, img.naturalHeight));
  let quality = opts.quality ?? DEFAULT_QUALITY;
  let passes = 0;
  let lastDataUrl = '';

  while (dim >= MIN_DIM) {
    const scale = dim / Math.max(img.naturalWidth, img.naturalHeight);
    const w = Math.max(1, Math.round(img.naturalWidth * scale));
    const h = Math.max(1, Math.round(img.naturalHeight * scale));
    const canvas = canvasFactory(w, h);
    if (!canvas) throw new Error('Your browser could not process this image.');
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Your browser could not process this image.');
    ctx.drawImage(img as unknown as CanvasImageSource, 0, 0, w, h);
    lastDataUrl = canvas.toDataURL('image/jpeg', quality);
    passes += 1;
    if (dataUrlBytes(lastDataUrl) <= maxOutputBytes) {
      return { dataUrl: lastDataUrl, width: w, height: h, bytes: dataUrlBytes(lastDataUrl), originalBytes, passes };
    }
    // Too big after re-encode: step down quality first, then resolution.
    if (quality > QUALITY_FLOOR) {
      quality = Math.max(QUALITY_FLOOR, quality - 0.15);
    } else {
      dim = Math.floor(dim * 0.75);
      quality = opts.quality ?? DEFAULT_QUALITY;
    }
  }
  throw new Error(
    'That photo could not be compressed small enough to upload safely. Please try a different photo.'
  );
}
