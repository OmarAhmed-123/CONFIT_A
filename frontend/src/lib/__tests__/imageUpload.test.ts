import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  validateImageFile,
  dataUrlBytes,
  compressImageToDataUrl,
  CanvasFactory,
  MAX_OUTPUT_BYTES,
} from '../imageUpload';

describe('validateImageFile', () => {
  it('rejects non-image MIME types (MIME spoofing guard)', () => {
    const r = validateImageFile({ type: 'application/pdf', size: 1000, name: 'x.pdf' });
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/Unsupported image format/i);
  });

  it('rejects files above the input ceiling with a size-aware message', () => {
    const r = validateImageFile({ type: 'image/jpeg', size: 21 * 1024 * 1024 });
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/too large/i);
  });

  it('rejects empty files', () => {
    expect(validateImageFile({ type: 'image/png', size: 0 }).ok).toBe(false);
  });

  it('accepts jpeg/png/webp within limits', () => {
    for (const type of ['image/jpeg', 'image/png', 'image/webp']) {
      expect(validateImageFile({ type, size: 5000 }).ok).toBe(true);
    }
  });
});

describe('dataUrlBytes', () => {
  it('computes decoded byte size (no padding)', () => {
    // 'AAAA' -> 4 base64 chars -> 3 bytes
    expect(dataUrlBytes('data:image/jpeg;base64,AAAA')).toBe(3);
  });
  it('accounts for single padding char', () => {
    expect(dataUrlBytes('data:image/jpeg;base64,AAA=')).toBe(2);
  });
  it('returns 0 for malformed input', () => {
    expect(dataUrlBytes('not-a-data-url')).toBe(0);
  });
});

// ---- compression pipeline (canvas + Image mocked; jsdom has neither) ----

class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  naturalWidth = 2000;
  naturalHeight = 3000;
  private _src = '';
  set src(v: string) {
    this._src = v;
    setTimeout(() => this.onload?.(), 0);
  }
  get src(): string {
    return this._src;
  }
}
class FakeFileReader {
  onload: ((e: { target: { result: string } }) => void) | null = null;
  onerror: (() => void) | null = null;
  readAsDataURL(_blob: Blob) {
    setTimeout(() => this.onload?.({ target: { result: 'data:image/jpeg;base64,AAAA' } }), 0);
  }
}

function fakeCanvasFactory(responses: string[]): CanvasFactory {
  let call = 0;
  return (w, h) => ({
    width: w,
    height: h,
    getContext: () => ({
      drawImage: vi.fn(),
    } as unknown as CanvasRenderingContext2D),
    toDataURL: () => {
      const r = responses[Math.min(call, responses.length - 1)];
      call += 1;
      return r;
    },
  });
}

const small = `data:image/jpeg;base64,${'A'.repeat(64)}`;
// base64 decodes to ~3/4 of its char count — overshoot so decoded > MAX_OUTPUT_BYTES
const huge = `data:image/jpeg;base64,${'A'.repeat(Math.ceil((MAX_OUTPUT_BYTES * 4) / 3) + 4096)}`;

beforeEach(() => {
  vi.stubGlobal('Image', FakeImage);
  vi.stubGlobal('FileReader', FakeFileReader);
});

describe('compressImageToDataUrl', () => {
  const blob = new Blob(['x'], { type: 'image/jpeg' });

  it('resolves on the first pass when output fits, scaling to maxDim', async () => {
    const r = await compressImageToDataUrl(blob, { canvasFactory: fakeCanvasFactory([small]) });
    expect(r.passes).toBe(1);
    expect(r.dataUrl).toBe(small);
    // longest edge 3000 -> scale to 1024: 2000x3000 -> 683x1024
    expect(r.width).toBe(683);
    expect(r.height).toBe(1024);
  });

  it('steps quality down and retries when the first encode is too big', async () => {
    const r = await compressImageToDataUrl(blob, { canvasFactory: fakeCanvasFactory([huge, small]) });
    expect(r.passes).toBe(2);
    expect(r.dataUrl).toBe(small);
  });

  it('fails honestly when it can never fit under the limit', async () => {
    await expect(
      compressImageToDataUrl(blob, { canvasFactory: fakeCanvasFactory([huge]) })
    ).rejects.toThrow(/could not be compressed small enough/i);
  });

  it('propagates validation errors before any encoding work', async () => {
    const bad = new Blob(['x'], { type: 'application/pdf' });
    await expect(compressImageToDataUrl(bad, { canvasFactory: fakeCanvasFactory([small]) })).rejects.toThrow(
      /Unsupported image format/i
    );
  });
});
