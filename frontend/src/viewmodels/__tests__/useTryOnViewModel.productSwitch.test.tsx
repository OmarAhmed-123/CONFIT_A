/**
 * Stale-state regression: switching the active "Try On" product must re-render
 * the NEW garment, never the previous (stale) one.
 *
 * Root cause (2026-09-06, found via real production browser E2E): the try-on
 * modal is rendered once and kept mounted in ConsumerLayout. The viewmodel
 * seeded `appliedGarments` from `initialProduct` only while it was empty, so
 * opening a second product left the first product's garment (and its rendered
 * result) in place and re-rendered the wrong item. Live evidence: a fresh
 * context tried product (renderable) -> 200, then switched to an accessory
 * card and the API was still asked to render the PREVIOUS garment (200), not
 * the accessory (which would correctly 422 pre-GPU).
 *
 * The fix re-initializes the canvas (and clears stale result/animation/history)
 * whenever the active product id changes. These tests pin that contract.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  multiRenderTryOn: vi.fn(),
  getCapabilities: vi.fn(),
  calculateNoPhotoFit: vi.fn(),
  showToast: vi.fn(),
  addItem: vi.fn(),
  openCart: vi.fn(),
}));

vi.mock("../../services/apiServices", () => ({
  tryOnService: {
    multiRenderTryOn: mocks.multiRenderTryOn,
    getCapabilities: mocks.getCapabilities,
    calculateNoPhotoFit: mocks.calculateNoPhotoFit,
  },
}));
vi.mock("../../stores/uiStore", () => ({
  useUIStore: () => ({ showToast: mocks.showToast }),
}));
vi.mock("../../stores/cartStore", () => ({
  useCartStore: () => ({ addItem: mocks.addItem, openCart: mocks.openCart }),
}));

import { useTryOnViewModel } from "../useTryOnViewModel";

const PRODUCT_A = {
  id: 3,
  title: "Relaxed Organic Poplin Oxford Shirt",
  category_name: "Tops & Shirts",
  base_price: 95,
  thumbnail_url: "https://img.example/3.jpg",
} as any;

const PRODUCT_B = {
  id: 5,
  title: "Silk Slip Column Maxi Dress with Draping",
  category_name: "Dresses",
  base_price: 240,
  thumbnail_url: "https://img.example/5.jpg",
} as any;

const OK = (n: number) => ({
  session_id: n,
  status: "completed",
  user_reference_image: "ref",
  rendered_result_url: `data:image/png;base64,IMG${n}`,
  applied_items: [],
  total_price: 1,
  fit_confidence_score: 95,
  body_fit_verdict: "Optimal",
  recommended_sizes: {},
  ai_disclosure: "test",
  traceability_hash: "T",
  layering_order: [],
});

const capabilityFor = (id: number, slot_type = "upper_inner") => ({
  product_id: id,
  product_slug: String(id),
  category_slug: "test",
  slot_type,
  state: "supported",
  reason_code: "SUPPORTED",
  message: "supported",
  provider: "test",
});

function payloadOf(i: number) {
  return mocks.multiRenderTryOn.mock.calls[i][0];
}

describe("switching the active product (stale-state regression)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.multiRenderTryOn.mockImplementation((p: any) =>
      Promise.resolve(OK(p.product_ids[0])),
    );
    mocks.calculateNoPhotoFit.mockResolvedValue({ recommended: false });
    mocks.getCapabilities.mockImplementation((ids: number[]) =>
      Promise.resolve({
        provider: "test",
        engine_state: "available",
        supported_slots: ["upper_inner", "lower", "dress"],
        unsupported_slots: [],
        products: ids.map((id) =>
          capabilityFor(
            id,
            id === 5 ? "dress" : id === 4 ? "lower" : "upper_inner",
          ),
        ),
      }),
    );
  });

  it("re-renders the NEW garment and drops the previous one when the product changes", async () => {
    const { result, rerender } = renderHook(({ p }) => useTryOnViewModel(p), {
      initialProps: { p: PRODUCT_A },
    });

    // initial auto-render for PRODUCT_A (id 3, shirt -> upper_inner)
    await waitFor(() =>
      expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(1),
    );
    expect(payloadOf(0)).toMatchObject({ product_ids: [3] });
    expect(Object.keys(result.current.appliedGarments)).toEqual([
      "upper_inner",
    ]);

    // user opens a DIFFERENT product via a fresh "Try On" click
    await act(async () => {
      rerender({ p: PRODUCT_B });
    });
    await waitFor(() =>
      expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(2),
    );

    // the new render is for PRODUCT_B (id 5), NOT the stale PRODUCT_A (id 3)
    expect(payloadOf(1)).toMatchObject({ product_ids: [5] });
    // the canvas holds only B's garment (dress slot); A's shirt is gone
    expect(Object.keys(result.current.appliedGarments)).toEqual(["dress"]);
    // the stale result (from A) is cleared, not left displayed
    expect(result.current.multiTryOnResult?.rendered_result_url).not.toBe(
      OK(3).rendered_result_url,
    );
  });

  it("blocks unsupported products using backend capability before provider render", async () => {
    mocks.getCapabilities.mockImplementation((ids: number[]) =>
      Promise.resolve({
        provider: "test",
        engine_state: "available",
        supported_slots: ["upper_inner"],
        unsupported_slots: ["accessory"],
        products: ids.map((id) => ({
          product_id: id,
          product_slug: String(id),
          category_slug: "accessories",
          slot_type: "accessory",
          state: "unsupported",
          reason_code: "CATEGORY_UNSUPPORTED_BY_ENGINE",
          message: "Accessories are not supported by virtual try-on.",
          provider: "test",
        })),
      }),
    );

    const ACCESSORY = {
      id: 9,
      title: "Structured Metallic Box Clutch",
      category_name: "Accessories",
      base_price: 180,
    } as any;
    const { result } = renderHook(() => useTryOnViewModel(ACCESSORY));

    await waitFor(() => expect(result.current.tryOnStatus).toBe("failed"));
    expect(mocks.multiRenderTryOn).not.toHaveBeenCalled();
    expect(result.current.errorMessage).toContain(
      "Accessories are not supported",
    );
  });

  it("does NOT reset the canvas when building a multi-garment outfit (same product)", async () => {
    const { result } = renderHook(() => useTryOnViewModel(PRODUCT_A));
    await waitFor(() =>
      expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(1),
    );

    // user adds a SECOND garment to the canvas (initialProduct unchanged)
    const PRODUCT_C = {
      id: 4,
      title: "Pleated Tapered Wool Trousers",
      category_name: "Bottoms & Trousers",
      base_price: 120,
    } as any;
    await act(async () => {
      result.current.addGarmentToCanvas(PRODUCT_C);
    });
    await waitFor(() =>
      expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(2),
    );

    // canvas now has BOTH garments (upper_inner + lower); not reset to one
    expect(Object.keys(result.current.appliedGarments).sort()).toEqual([
      "lower",
      "upper_inner",
    ]);
    expect(payloadOf(1)).toMatchObject({
      product_ids: expect.arrayContaining([3, 4]),
    });
  });

  it("forwards every captured body measurement to the no-photo fit contract", async () => {
    const { result } = renderHook(() => useTryOnViewModel(PRODUCT_A));

    await act(async () => {
      await result.current.runNoPhotoFit({
        height_cm: 178,
        weight_kg: 70,
        body_shape: "Athletic V-Taper",
        chest_cm: 98,
        waist_cm: 82,
        hip_cm: 96,
        shoulder_cm: 46,
        preferred_fit: "regular",
      });
    });

    expect(mocks.calculateNoPhotoFit).toHaveBeenCalledWith({
      product_id: PRODUCT_A.id,
      units: "metric",
      height: 178,
      weight: 70,
      chest: 98,
      waist: 82,
      hip: 96,
      shoulder: 46,
      body_shape: "Athletic V-Taper",
      preferred_fit: "regular",
    });
  });
});
