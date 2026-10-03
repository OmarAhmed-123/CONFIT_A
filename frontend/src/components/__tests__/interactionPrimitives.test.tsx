/**
 * Flight-feedback contract tests (add to bag / save).
 *
 * Written adversarially, like bnplBadge.test.tsx: each test pins the
 * UNFLATTERING branch of the spec in docs — the states a demo never shows.
 *
 *   1. "Added" may NOT render before the mutation resolves (slow network).
 *   2. One control never sends twice (double-tap while pending).
 *   3. A failure returns the control to an actionable state and ANNOUNCES
 *      the failure as text in a polite live region — not colour, not motion.
 *   4. The duplicate-SKU interception ("handled") claims neither success nor
 *      failure: the dialog owns the rest of the flow.
 *   5. Under prefers-reduced-motion the decorative flight hint is absent and
 *      the feature is fully functional through text alone.
 *   6. axe: no critical/serious violations.
 *   7. Touch targets declare ≥44px.
 *   8. The wishlist toggle tells the truth about WHERE it saved: this
 *      deployment has no wishlist endpoint, so the announcement says
 *      "on this device" and never implies an account-level save.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import React, { useState } from "react";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { axe } from "vitest-axe";
import { I18nextProvider } from "react-i18next";

import i18n, { setAppLanguage } from "../../i18n/i18n";
import {
  AsyncActionButton,
  WishlistToggle,
  type ActionOutcome,
} from "../common/InteractionPrimitives";

afterEach(() => {
  cleanup();
  setAppLanguage("en");
  vi.restoreAllMocks();
});

function wrap(ui: React.ReactElement) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

/** A mutation whose resolution the test controls explicitly. */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const IDLE = "Add to Bag";

describe("success is a server fact, not a UI guess", () => {
  it("shows pending on a slow network and never claims Added before resolve", async () => {
    const gate = deferred<ActionOutcome>();
    wrap(<AsyncActionButton onAction={() => gate.promise} idleLabel={IDLE} />);

    fireEvent.click(screen.getByRole("button", { name: /add to bag/i }));

    // While the request is in flight: pending text, disabled control,
    // and no success claim anywhere. (The copy renders both as the visible
    // label and inside the live region, so assert on the control itself.)
    const button = screen.getByRole("button");
    await waitFor(() => expect(button).toHaveTextContent("Adding…"));
    expect(button).toBeDisabled();
    expect(button).not.toHaveTextContent("Added");

    gate.resolve("success");
    await waitFor(() => expect(button).toHaveTextContent("Added"));
  });

  it("a failed mutation returns the control to an actionable state and announces the failure", async () => {
    const action = vi.fn(async (): Promise<ActionOutcome> => "error");
    wrap(<AsyncActionButton onAction={action} idleLabel={IDLE} />);

    fireEvent.click(screen.getByRole("button"));

    // The failure is text in a polite live region — the state does not
    // depend on colour or motion.
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Could not add — try again",
      );
    });
    // Actionable again: the shopper can retry, nothing is stuck.
    expect(screen.getByRole("button")).not.toBeDisabled();
  });

  it("a thrown API error behaves exactly like a returned failure (rollback to actionable)", async () => {
    const action = vi.fn(async () => {
      throw new Error("500");
    });
    wrap(<AsyncActionButton onAction={action} idleLabel={IDLE} />);

    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Could not add — try again",
      );
    });
    expect(screen.getByRole("button")).not.toBeDisabled();
  });

  it("the duplicate-SKU interception claims neither success nor failure", async () => {
    // cartStore.addItem resolves WITHOUT adding when the duplicate dialog
    // takes over; the handler maps that to "handled".
    const action = vi.fn(async (): Promise<ActionOutcome> => "handled");
    wrap(<AsyncActionButton onAction={action} idleLabel={IDLE} />);

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByRole("button")).toHaveAttribute("data-state", "idle");
    });
    expect(screen.queryAllByText("Added")).toEqual([]);
    expect(screen.queryAllByText("Could not add — try again")).toEqual([]);
  });
});

describe("unavailable NAMES the gap on the control itself (spec §5)", () => {
  it("renders the unavailable text as the visible label AND announces it politely", async () => {
    wrap(
      <AsyncActionButton
        onAction={async () => "unavailable" as ActionOutcome}
        idleLabel={IDLE}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: IDLE }));

    // The control itself says why — not just a toast the shopper may miss.
    await waitFor(() =>
      expect(screen.getByRole("button")).toHaveTextContent(
        "Unavailable — pick another size",
      ),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Unavailable — pick another size",
    );
    // Not a dead end: the control returns to an actionable state (timed
    // revert to idle is covered by the machine; it is never `disabled`).
    expect(screen.getByRole("button")).not.toBeDisabled();
  });

  it("speaks Arabic in the Arabic page — never the raw EN fallback", async () => {
    await setAppLanguage("ar");
    wrap(
      <AsyncActionButton
        onAction={async () => "unavailable" as ActionOutcome}
        idleLabel="أضف إلى الحقيبة"
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() =>
      expect(screen.getByRole("button")).toHaveTextContent(
        "غير متاح — اختر مقاسًا آخر",
      ),
    );
  });

  it("a caller-supplied unavailableLabel wins over the default", async () => {
    wrap(
      <AsyncActionButton
        onAction={async () => "unavailable" as ActionOutcome}
        idleLabel={IDLE}
        unavailableLabel="This size sold out"
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() =>
      expect(screen.getByRole("button")).toHaveTextContent("This size sold out"),
    );
  });
});

describe("one button never sends twice", () => {
  it("ignores a second tap while the first mutation is in flight", async () => {
    const gate = deferred<ActionOutcome>();
    const action = vi.fn(() => gate.promise);
    wrap(<AsyncActionButton onAction={action} idleLabel={IDLE} />);

    const button = screen.getByRole("button");
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    gate.resolve("success");
    await waitFor(() => expect(button).toHaveTextContent("Added"));
    expect(action).toHaveBeenCalledTimes(1);
  });
});

describe("unauthorized: the fix is signing in, not retrying (spec 01 §5)", () => {
  it("a 401 opens auth WITHOUT losing context and never claims success or generic failure", async () => {
    const onUnauthorized = vi.fn();
    const action = vi.fn(async () => {
      throw Object.assign(new Error("auth"), { status: 401, code: "AUTH_REQUIRED" });
    });
    wrap(
      <AsyncActionButton
        onAction={action}
        onUnauthorized={onUnauthorized}
        idleLabel={IDLE}
      />,
    );

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      expect(button).toHaveAttribute("data-state", "unauthorized");
    });
    // Auth was opened exactly once — as a modal, so the page (context) stays.
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    // The control says what the next step is, as text.
    expect(button).toHaveTextContent("Sign in to continue — your selection is kept.");
    // No success claim, no generic "try again" lie about a retryable failure.
    expect(button).not.toHaveTextContent("Added");
    expect(screen.queryAllByText("Could not add — try again")).toEqual([]);
    // Still actionable after signing in.
    expect(button).not.toBeDisabled();
  });
});

describe("offline: a request that never left the device is neither success nor failure", () => {
  it("names the offline condition and keeps retry available", async () => {
    const onLineSpy = vi
      .spyOn(window.navigator, "onLine", "get")
      .mockReturnValue(false);
    const action = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    wrap(<AsyncActionButton onAction={action} idleLabel={IDLE} />);

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      expect(button).toHaveAttribute("data-state", "offline");
    });
    expect(button).toHaveTextContent(
      "You appear to be offline — check your connection and try again.",
    );
    expect(button).not.toHaveTextContent("Added");
    expect(button).not.toBeDisabled();
    // The live region carries the same truth for screen readers.
    expect(screen.getByRole("status")).toHaveTextContent(/offline/i);

    onLineSpy.mockRestore();
  });
});

describe("aria-busy mirrors the pending state (spec 01 §5)", () => {
  it("is true while the mutation is in flight and false after it resolves", async () => {
    const gate = deferred<ActionOutcome>();
    wrap(<AsyncActionButton onAction={() => gate.promise} idleLabel={IDLE} />);

    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-busy", "false");

    fireEvent.click(button);
    await waitFor(() => expect(button).toHaveAttribute("aria-busy", "true"));

    gate.resolve("success");
    await waitFor(() => expect(button).toHaveAttribute("aria-busy", "false"));
  });
});

describe("reduced motion: the feature IS the text, the motion is garnish", () => {
  function forceReducedMotion() {
    window.matchMedia = ((query: string) => ({
      matches: /prefers-reduced-motion/.test(query),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }

  it("completes the whole idle→pending→success cycle with no flight hint", async () => {
    forceReducedMotion();
    const action = vi.fn(async (): Promise<ActionOutcome> => "success");
    wrap(<AsyncActionButton onAction={action} idleLabel={IDLE} />);

    const button = screen.getByRole("button");
    fireEvent.click(button);
    await waitFor(() => expect(button).toHaveTextContent("Added"));
    // The decorative lift-off is absent — and nothing broke without it.
    expect(screen.queryByTestId("flight-hint")).not.toBeInTheDocument();
  });
});

describe("accessibility of the controls themselves", () => {
  it("axe: no critical/serious violations in idle state", async () => {
    const { container } = wrap(
      <AsyncActionButton onAction={() => "success" as const} idleLabel={IDLE} />,
    );
    const results = await axe(container);
    const serious = results.violations.filter((v) =>
      ["critical", "serious"].includes(v.impact ?? ""),
    );
    expect(serious).toEqual([]);
  });

  it("declares a ≥44px touch target on both primitives", () => {
    wrap(
      <>
        <AsyncActionButton onAction={() => undefined} idleLabel={IDLE} />
        <WishlistToggle isWishlisted={false} onToggle={() => {}}>
          <span>♥</span>
        </WishlistToggle>
      </>,
    );
    const [bag, heart] = screen.getAllByRole("button");
    expect(bag.className).toContain("min-h-[44px]");
    expect(heart.className).toContain("min-w-[44px]");
    expect(heart.className).toContain("min-h-[44px]");
  });
});

describe("the wishlist tells the truth about where it saved", () => {
  function Harness() {
    const [liked, setLiked] = useState(false);
    return (
      <WishlistToggle isWishlisted={liked} onToggle={() => setLiked((v) => !v)}>
        <span>♥</span>
      </WishlistToggle>
    );
  }

  it("announces a device-local save — never an account-level claim", async () => {
    wrap(<Harness />);
    const button = screen.getByRole("button");

    fireEvent.click(button);
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Saved to wishlist on this device",
      );
    });
    expect(button).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(button);
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Removed from wishlist",
      );
    });
    expect(button).toHaveAttribute("aria-pressed", "false");
  });
});
