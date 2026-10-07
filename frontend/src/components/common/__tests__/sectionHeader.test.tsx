/**
 * Home pass 3 — SectionHeader contract.
 *
 * The component replaces five hand-rolled header blocks in HomeView, so
 * these tests pin the contract every section now inherits:
 *   A. content slots (eyebrow / title+titleId / hint / icon)
 *   B. action variants — real <Link> when `to` given, <button> otherwise;
 *      ≥44px target class; directional glyph aria-hidden + RTL mirror class
 *   C. axe EN + AR (serious/critical only)
 */
import React from "react";
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { axe } from "vitest-axe";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import { vi } from "vitest";

import i18n, { setAppLanguage } from "../../../i18n/i18n";
import { SectionHeader } from "../SectionHeader";

const wrap = (ui: React.ReactElement) =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{ui}</MemoryRouter>
    </I18nextProvider>,
  );

afterEach(() => {
  cleanup();
});

describe("A. content slots", () => {
  it("renders eyebrow, h2 title with the given id, and hint", () => {
    wrap(
      <SectionHeader
        eyebrow="Just landed"
        title="New in"
        titleId="sh-test-title"
        hint="Fresh from the maisons"
      />,
    );
    const heading = screen.getByRole("heading", { level: 2, name: "New in" });
    expect(heading.id).toBe("sh-test-title");
    expect(screen.getByText("Just landed")).toBeInTheDocument();
    expect(screen.getByText("Fresh from the maisons")).toBeInTheDocument();
  });

  it("renders no interactive element at all when there is no action", () => {
    wrap(<SectionHeader title="Occasions" />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("B. action variants", () => {
  it("`to` renders a real router link with a ≥44px target and a hidden RTL-mirrored glyph", () => {
    wrap(
      <SectionHeader
        title="New in"
        action={{ label: "View the catalogue", to: "/discover" }}
      />,
    );
    const link = screen.getByRole("link", { name: "View the catalogue" });
    expect(link.getAttribute("href")).toBe("/discover");
    // 44px touch floor comes from the shared action class, not the call site.
    expect(link.className).toContain("min-h-11");
    const glyph = link.querySelector('[aria-hidden="true"]');
    expect(glyph).not.toBeNull();
    // Project convention for directional glyphs (see AccessibleCarousel).
    expect(glyph!.className).toContain("rtl:rotate-180");
    // The arrow is decorative: the accessible name is ONLY the label.
    expect(link).toHaveAccessibleName("View the catalogue");
  });

  it("`onClick` renders a button that fires exactly once per click", () => {
    const onClick = vi.fn();
    wrap(
      <SectionHeader
        title="Today's picks"
        action={{ label: "Ask the stylist", onClick }}
      />,
    );
    const button = screen.getByRole("button", { name: "Ask the stylist" });
    expect(button.getAttribute("type")).toBe("button");
    expect(button.className).toContain("min-h-11");
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("C. axe", () => {
  const runAxe = async (el: HTMLElement) => {
    const results = await axe(el, {
      rules: {
        "color-contrast": { enabled: false },
        "target-size": { enabled: false },
      },
    });
    return results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
  };

  it("EN header with link action has no serious/critical violations", async () => {
    const { container } = wrap(
      <SectionHeader
        eyebrow="Just landed"
        title="New in"
        hint="Fresh pieces"
        action={{ label: "View all", to: "/discover" }}
      />,
    );
    expect(await runAxe(container)).toEqual([]);
  });

  it("AR/RTL header has no serious/critical violations", async () => {
    await setAppLanguage("ar");
    try {
      const { container } = wrap(
        <SectionHeader
          eyebrow="وصل حديثًا"
          title="الجديد لدينا"
          hint="قطع جديدة من الدور العالمية"
          action={{ label: "تصفح الكتالوج", to: "/discover" }}
        />,
      );
      expect(await runAxe(container)).toEqual([]);
    } finally {
      await setAppLanguage("en");
    }
  });
});
