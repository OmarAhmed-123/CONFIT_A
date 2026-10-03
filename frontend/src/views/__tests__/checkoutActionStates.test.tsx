/**
 * Spec 01 finalisation — checkout cart mutations as a REAL state machine.
 *
 * Pinned here (each was a live violation before this pass):
 *   · qty/remove/promo buttons show pending (aria-busy + spinner) instead
 *     of mutating silently;
 *   · no double submit: a second click while in flight issues NO request;
 *   · failure is honest AND translated — the old hardcoded English toasts
 *     ('Could not update quantity', …) are gone; the UI never claims
 *     success when the server refused;
 *   · promo failure keeps the user's code in the input (context preserved)
 *     and announces via role="alert";
 *   · money is locale-formatted through Intl and LTR-isolated (<bdi>) —
 *     no more `$x.toFixed(2)` in the Arabic page;
 *   · axe-clean in EN and AR.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import { axe } from "vitest-axe";

import i18n, { setAppLanguage } from "../../i18n/i18n";
import en from "../../i18n/en.json";
import ar from "../../i18n/ar.json";

/* ------------------------------------------------------------------ */
/* Controllable store fakes                                            */
/* ------------------------------------------------------------------ */
const updateQuantity = vi.fn<(id: number, q: number) => Promise<void>>();
const removeItem = vi.fn<(id: number) => Promise<void>>();
const applyPromo = vi.fn<(code: string) => Promise<void>>();
const fetchCart = vi.fn(async () => {});
const showToast = vi.fn();
const openAuthModal = vi.fn();

const cart = {
  id: 1,
  currency: "USD",
  items_count: 1,
  subtotal: 149.5,
  discount_amount: 0,
  tax_amount: 7.48,
  shipping_amount: 12,
  total: 168.98,
  promo_code: null,
  items: [
    {
      id: 11,
      product_title: "Navy Blazer",
      brand_name: "Atelier",
      size: "M",
      quantity: 2,
      subtotal: 149.5,
      image_url: "https://example.com/x.jpg",
    },
  ],
};

vi.mock("../../stores/cartStore", () => ({
  useCartStore: () => ({ cart, fetchCart, applyPromo, updateQuantity, removeItem }),
}));
vi.mock("../../stores/authStore", () => ({
  useAuthStore: () => ({ user: { id: 1, email: "a@b.c" }, isAuthenticated: true }),
}));
vi.mock("../../stores/uiStore", () => ({
  useUIStore: () => ({ showToast, openAuthModal }),
}));
vi.mock("../../services/apiServices", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/apiServices")>();
  return {
    ...actual,
    catalogService: {
      ...actual.catalogService,
      getBopisStoresForSKU: vi.fn(async () => []),
    },
    commerceService: {
      ...actual.commerceService,
      checkout: vi.fn(),
      getPaymentMethods: vi.fn(async () => ({ available_methods: [] })),
    },
  };
});

import { CheckoutView } from "../consumer/CheckoutView";

const ui = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/checkout"]}>
        <CheckoutView />
      </MemoryRouter>
    </I18nextProvider>,
  );

/** A promise whose settlement the test controls. */
const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { (resolve = res), (reject = rej); });
  return { promise, resolve, reject };
};

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(async () => {
  cleanup();
  await setAppLanguage("en");
});

describe("quantity buttons — pending, no double submit, honest failure", () => {
  it("click → aria-busy pending; a second click issues NO extra request", async () => {
    const d = deferred<void>();
    updateQuantity.mockReturnValue(d.promise);
    ui();
    const inc = screen.getByRole("button", { name: en.commerce.qty_increase });
    fireEvent.click(inc);
    expect(updateQuantity).toHaveBeenCalledTimes(1);
    expect(updateQuantity).toHaveBeenCalledWith(11, 3);
    await waitFor(() => expect(inc).toHaveAttribute("aria-busy", "true"));
    // In-flight: both qty buttons and remove are locked (one op per line).
    fireEvent.click(inc);
    fireEvent.click(screen.getByRole("button", { name: en.commerce.qty_decrease }));
    expect(updateQuantity).toHaveBeenCalledTimes(1);
    d.resolve();
    await waitFor(() => expect(inc).toHaveAttribute("aria-busy", "false"));
  });

  it("server refusal → translated error toast, never a success state", async () => {
    updateQuantity.mockRejectedValue(new Error("409"));
    ui();
    fireEvent.click(screen.getByRole("button", { name: en.commerce.qty_increase }));
    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith(en.checkout.qty_update_failed, "error"),
    );
    // No optimistic success claim anywhere.
    expect(showToast).not.toHaveBeenCalledWith(expect.anything(), "success");
  });

  it("remove failure uses the translated catalogue string (hardcoded English is gone)", async () => {
    removeItem.mockRejectedValue(new Error("500"));
    ui();
    fireEvent.click(screen.getByRole("button", { name: en.commerce.remove_item }));
    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith(en.checkout.remove_failed, "error"),
    );
    expect(showToast).not.toHaveBeenCalledWith("Could not remove item", "error");
  });
});

describe("promo code — pending label, alert on failure, context preserved", () => {
  it("pending shows the translated applying label and blocks a second submit", async () => {
    const d = deferred<void>();
    applyPromo.mockReturnValue(d.promise);
    ui();
    const input = screen.getByLabelText(en.checkout.promo_code);
    fireEvent.change(input, { target: { value: "GOLD10" } });
    const btn = screen.getByRole("button", { name: en.common.apply });
    fireEvent.click(btn);
    expect(await screen.findByText(en.checkout.applying)).toBeInTheDocument();
    fireEvent.click(screen.getByText(en.checkout.applying));
    expect(applyPromo).toHaveBeenCalledTimes(1);
    d.resolve();
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(en.checkout.promo_applied, "success"));
  });

  it("failure announces via role=alert and the typed code is NOT wiped", async () => {
    applyPromo.mockRejectedValue(new Error(""));
    ui();
    const input = screen.getByLabelText(en.checkout.promo_code) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "BADCODE" } });
    fireEvent.click(screen.getByRole("button", { name: en.common.apply }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(en.checkout.promo_failed);
    expect(input.value).toBe("BADCODE"); // context preserved for retry
    expect(showToast).not.toHaveBeenCalledWith(en.checkout.promo_applied, "success");
  });
});

describe("money is Intl-formatted and LTR-isolated", () => {
  it("EN: totals render through Intl (no raw toFixed concatenation)", () => {
    const { container } = ui();
    const bdis = Array.from(container.querySelectorAll('bdi[dir="ltr"]')).map(
      (b) => b.textContent,
    );
    expect(bdis).toEqual(expect.arrayContaining(["$149.50", "$7.48", "$12.00", "$168.98"]));
  });

  it("AR: the Arabic page keeps every amount inside <bdi dir='ltr'>", async () => {
    await setAppLanguage("ar");
    const { container } = ui();
    const bdiTexts = Array.from(container.querySelectorAll('bdi[dir="ltr"]'));
    expect(bdiTexts.length).toBeGreaterThanOrEqual(4);
    // And the qty failure toast is Arabic, really Arabic.
    expect(ar.checkout.qty_update_failed).toMatch(/[\u0600-\u06FF]/);
  });
});

describe("accessibility", () => {
  it("touch targets: qty buttons are 44px class-sized, remove has min-h-11", () => {
    ui();
    const inc = screen.getByRole("button", { name: en.commerce.qty_increase });
    expect(inc.className).toContain("w-11");
    expect(inc.className).toContain("h-11");
    const remove = screen.getByRole("button", { name: en.commerce.remove_item });
    expect(remove.className).toContain("min-h-11");
  });

  it("axe: no violations in EN or AR", async () => {
    const { container, unmount } = ui();
    expect((await axe(container)).violations).toEqual([]);
    unmount();
    await setAppLanguage("ar");
    const { container: arC } = ui();
    expect((await axe(arC)).violations).toEqual([]);
  });
});
