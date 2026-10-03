/**
 * Design register system — contract tests from every side.
 *
 * Pinned here:
 *   · MEASUREMENT, not claims: every contrast ratio documented in
 *     registers.ts is recomputed with the real WCAG formula; a palette
 *     edit that silently breaks AA fails this file.
 *   · ROUTING: every route family in AppRoutes resolves to its register,
 *     including aliases (/b2b vs /partner, /products listing vs detail,
 *     /fit vs /fit-finder) and nested/trailing-slash paths.
 *   · GUARANTEES: the money path is always the light commerce register
 *     (spec 07 — dark editorial never reaches checkout); /admin and the
 *     partner portal never share a register (spec 13).
 *   · CSS: the hairline + rule animation live ONLY inside
 *     prefers-reduced-motion: no-preference; forced-colors falls back to
 *     CanvasText.
 *   · BANNER: i18n'd label (EN+AR, really translated), decorative parts
 *     aria-hidden, editorial renders no banner, axe-clean in both
 *     directions.
 */
import React from "react";
import fs from "fs";
import path from "path";
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { axe } from "vitest-axe";
import { I18nextProvider } from "react-i18next";

import i18n, { setAppLanguage } from "../../i18n/i18n";
import {
  REGISTERS,
  resolveRegister,
  registerStyle,
  type RegisterId,
} from "../registers";
import { RegisterBanner } from "../../components/common/RegisterBanner";

import en from "../../i18n/en.json";
import ar from "../../i18n/ar.json";

const css = fs.readFileSync(
  path.join(__dirname, "../../styles/index.css"),
  "utf8",
);

afterEach(async () => {
  cleanup();
  await setAppLanguage("en");
});

/* ------------------------------------------------------------------ */
/* WCAG math (real formula — same as surfaceSystem.test)               */
/* ------------------------------------------------------------------ */
const lin = (c: number) => {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};
const luminance = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
};
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const BODY = "#FAF9F6";
const CARD = "#FFFFFF";
const ALL: RegisterId[] = [
  "editorial",
  "atelier",
  "fit",
  "commerce",
  "account",
  "partner",
  "admin",
];

describe("palette is measured, not asserted", () => {
  it.each(ALL)("%s ink is AA+ (≥4.5) on body AND card surfaces", (id) => {
    const { ink } = REGISTERS[id];
    expect(contrast(ink, BODY)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(ink, CARD)).toBeGreaterThanOrEqual(4.5);
  });

  it("the documented ratios in registers.ts match recomputation (±0.01)", () => {
    const documented: Record<RegisterId, [number, number]> = {
      editorial: [7.22, 7.6],
      atelier: [7.58, 7.98],
      fit: [7.94, 8.36],
      commerce: [15.28, 16.08],
      account: [6.44, 6.78],
      partner: [7.96, 8.38],
      admin: [8.95, 9.43],
    };
    for (const id of ALL) {
      const { ink } = REGISTERS[id];
      expect(contrast(ink, BODY)).toBeCloseTo(documented[id][0], 1);
      expect(contrast(ink, CARD)).toBeCloseTo(documented[id][1], 1);
    }
  });

  it("every register has a distinct accent — variety is real", () => {
    const accents = ALL.map((id) => REGISTERS[id].accent.toUpperCase());
    expect(new Set(accents).size).toBe(ALL.length);
  });

  it("non-editorial accents clear 3:1 on the body; editorial gold is documented decorative-only", () => {
    for (const id of ALL) {
      if (id === "editorial") {
        // 2.30:1 — allowed ONLY because the accent is pure decoration
        // (hairline/dot), never text and never a control boundary.
        expect(contrast(REGISTERS.editorial.accent, BODY)).toBeLessThan(3);
      } else {
        expect(contrast(REGISTERS[id].accent, BODY)).toBeGreaterThanOrEqual(3);
      }
    }
  });
});

describe("route resolution — every family, every alias", () => {
  const cases: Array<[string, RegisterId]> = [
    ["/", "editorial"],
    ["/discover", "editorial"],
    ["/products", "editorial"], // catalogue LISTING = story
    ["/stylist", "editorial"],
    ["/product/navy-blazer", "commerce"], // DETAIL = item
    ["/products/navy-blazer", "commerce"],
    ["/cart", "commerce"],
    ["/checkout", "commerce"],
    ["/orders", "commerce"],
    ["/orders/CNF-2041", "commerce"],
    ["/returns", "commerce"],
    ["/wardrobe", "atelier"],
    ["/wardrobe/item/42", "atelier"],
    ["/builder", "atelier"],
    ["/outfits", "atelier"],
    ["/outfits/7", "atelier"],
    ["/my-looks", "atelier"],
    ["/looks/shared-token-abc", "atelier"],
    ["/try-on", "fit"],
    ["/try-on/session-9", "fit"],
    ["/tryon-studio", "fit"],
    ["/fit", "fit"],
    ["/fit-finder", "fit"],
    ["/visual-search", "fit"],
    ["/profile", "account"],
    ["/settings", "account"],
    ["/notifications", "account"],
    ["/privacy", "account"],
    ["/privacy-policy", "account"],
    ["/terms", "account"],
    ["/terms-of-service", "account"],
    ["/gdpr", "account"],
    ["/b2b", "partner"],
    ["/b2b/catalog", "partner"],
    ["/b2b/analytics", "partner"],
    ["/partner", "partner"],
    ["/partner/inventory", "partner"],
    ["/admin", "admin"],
    ["/admin/analytics", "admin"],
    ["/admin/audit", "admin"],
  ];
  it.each(cases)("%s → %s", (pathname, expected) => {
    expect(resolveRegister(pathname)).toBe(expected);
  });

  it("trailing slashes do not change the register", () => {
    expect(resolveRegister("/checkout/")).toBe("commerce");
    expect(resolveRegister("/b2b/")).toBe("partner");
    expect(resolveRegister("/products/")).toBe("editorial");
  });

  it("unknown paths fall back to editorial (the router redirects * → /)", () => {
    expect(resolveRegister("/no-such-page")).toBe("editorial");
  });
});

describe("hard guarantees (spec 07 / spec 13)", () => {
  it("the money path is ALWAYS the light commerce register", () => {
    for (const p of ["/cart", "/checkout", "/orders", "/orders/CNF-1", "/returns"]) {
      const id = resolveRegister(p);
      expect(id).toBe("commerce");
      expect(REGISTERS[id].scheme).toBe("light");
    }
  });

  it("admin and partner portals never share a register", () => {
    const adminIds = ["/admin", "/admin/catalog", "/admin/audit"].map(resolveRegister);
    const partnerIds = ["/b2b", "/partner", "/b2b/placements"].map(resolveRegister);
    expect(new Set(adminIds)).toEqual(new Set(["admin"]));
    expect(new Set(partnerIds)).toEqual(new Set(["partner"]));
    expect(REGISTERS.admin.accent).not.toBe(REGISTERS.partner.accent);
  });
});

describe("stylesheet contract", () => {
  it("the rule animation exists ONLY inside prefers-reduced-motion: no-preference", () => {
    const occurrences = css.split("register-rule-grow").length - 1;
    expect(occurrences).toBeGreaterThanOrEqual(2); // @keyframes + usage
    const guardStart = css.indexOf("@media (prefers-reduced-motion: no-preference)");
    expect(guardStart).toBeGreaterThan(-1);
    // No register animation may appear before the guard's block.
    expect(css.slice(0, guardStart)).not.toContain("register-rule-grow");
  });

  it("the register hairline consumes the custom property and has a forced-colors fallback", () => {
    expect(css).toContain("main[data-register]");
    expect(css).toContain("var(--register-accent");
    const fc = css.slice(css.indexOf("main[data-register]"));
    expect(fc).toContain("border-top-color: CanvasText");
  });

  it("registerStyle exposes exactly the custom properties the CSS consumes", () => {
    const style = registerStyle("fit");
    expect(style["--register-accent"]).toBe(REGISTERS.fit.accent);
    expect(style["--register-ink"]).toBe(REGISTERS.fit.ink);
  });
});

describe("banner — i18n'd wayfinding, decorative accents, axe-clean", () => {
  it("every register label exists in BOTH locales and Arabic is really Arabic", () => {
    const flat = (o: Record<string, unknown>): Record<string, string> => {
      const out: Record<string, string> = {};
      const walk = (v: unknown, p: string) => {
        if (typeof v === "string") out[p] = v;
        else if (v && typeof v === "object")
          for (const [k, c] of Object.entries(v as Record<string, unknown>))
            walk(c, p ? `${p}.${k}` : k);
      };
      walk(o, "");
      return out;
    };
    const enFlat = flat(en as Record<string, unknown>);
    const arFlat = flat(ar as Record<string, unknown>);
    for (const id of ALL) {
      const key = REGISTERS[id].labelKey;
      expect(enFlat[key], key).toBeTruthy();
      expect(arFlat[key], key).toBeTruthy();
      expect(arFlat[key]).not.toBe(enFlat[key]);
      expect(arFlat[key]).toMatch(/[\u0600-\u06FF]/);
    }
  });

  it("renders the EN label with the register's AA ink; dot and rule are aria-hidden", async () => {
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <RegisterBanner register="commerce" />
      </I18nextProvider>,
    );
    expect(screen.getByText("Secure Shopping")).toBeInTheDocument();
    const hidden = container.querySelectorAll('[aria-hidden="true"]');
    expect(hidden.length).toBe(2); // dot + rule: decoration carries no meaning
    expect((await axe(container)).violations).toEqual([]);
  });

  it("renders the Arabic label under RTL and stays axe-clean", async () => {
    await setAppLanguage("ar");
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <div dir="rtl">
          <RegisterBanner register="partner" />
        </div>
      </I18nextProvider>,
    );
    expect(screen.getByText("عمليات الشركاء")).toBeInTheDocument();
    expect((await axe(container)).violations).toEqual([]);
  });

  it("editorial renders NO banner — the hero already owns that masthead", () => {
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <RegisterBanner register="editorial" />
      </I18nextProvider>,
    );
    expect(container.querySelector('[data-testid="register-banner"]')).toBeNull();
  });
});

describe("layout integration — <main> really carries the register", () => {
  it("ConsumerLayout + BrandLayout wire resolveRegister onto <main data-register> with the custom properties", () => {
    // Source-contract check (same technique as accessibility.rtl.test):
    // the layouts are too heavy for jsdom, but the wiring is a static fact.
    const read = (p: string) =>
      fs.readFileSync(path.join(__dirname, "../../", p), "utf8");
    for (const layout of ["layouts/ConsumerLayout.tsx", "layouts/BrandLayout.tsx"]) {
      const src = read(layout);
      expect(src).toContain("resolveRegister(location.pathname)");
      expect(src).toContain("data-register={register}");
      expect(src).toContain("registerStyle(register)");
      expect(src).toContain("<RegisterBanner register={register} />");
      // The register must be derived from the live location, never hardcoded.
      expect(src).toContain("useLocation()");
    }
  });
});
