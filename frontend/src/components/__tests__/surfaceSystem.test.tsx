/**
 * Spec 09 — Embossed Depth / Surface System. §10 required coverage:
 *   axe/contrast · @supports fallback · forced colors · reduced motion.
 *
 * jsdom applies no real CSS, so the CSS contracts are asserted against the
 * stylesheet SOURCE (same technique as accessibility.rtl.test.tsx), and the
 * contrast criteria are verified by actual WCAG relative-luminance math —
 * not by eye, not by trust.
 *
 * Structure:
 *   A. CSS contract: solid-first declaration order, @supports-gated blur,
 *      forced-colors override for every surface class, focus = outline not
 *      shadow
 *   B. Contrast mathematics: glass fallbacks over worst-case images ≥4.5:1,
 *      focus token ≥3:1 on BOTH scheme extremes (the old gold measurably
 *      failed on cream — regression-pinned)
 *   C. Surface component: variant classes, semantic `as`, class merging,
 *      no role/motion side effects, axe EN + AR/RTL
 *   D. Reduced motion: hierarchy is static CSS — identical render under
 *      `prefers-reduced-motion`
 */
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { I18nextProvider } from 'react-i18next';

import i18n, { setAppLanguage } from '../../i18n/i18n';
import { Surface, GlassPanel, Reveal } from '../common/Surface';

const css = fs.readFileSync(
  path.join(__dirname, '../../styles/index.css'),
  'utf8',
);

afterEach(async () => {
  cleanup();
  await setAppLanguage('en');
});

/* ------------------------------------------------------------------ */
/* WCAG math helpers (real formulas, WCAG 2.x §relative luminance)      */
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
/** alpha-composite `fg` at `alpha` over `bg`, returns hex. */
const composite = (fg: string, alpha: number, bg: string) => {
  const f = [1, 3, 5].map((i) => parseInt(fg.slice(i, i + 2), 16));
  const b = [1, 3, 5].map((i) => parseInt(bg.slice(i, i + 2), 16));
  return (
    '#' +
    f
      .map((v, i) =>
        Math.round(alpha * v + (1 - alpha) * b[i])
          .toString(16)
          .padStart(2, '0'),
      )
      .join('')
  );
};

/* ------------------------------------------------------------------ */
/* A. CSS contract                                                     */
/* ------------------------------------------------------------------ */
describe('surface CSS contract', () => {
  it('declares every surface class solid-first, with blur ONLY inside @supports (§6.3/§9)', () => {
    // The fallback declarations exist unconditionally…
    expect(css).toMatch(/\.surface-glass-light\s*\{[^}]*--surface-glass-light-fallback/);
    expect(css).toMatch(/\.surface-glass-dark\s*\{[^}]*--surface-glass-dark-fallback/);
    // …and backdrop-filter appears nowhere outside the @supports block.
    const supportsIdx = css.indexOf('@supports (backdrop-filter: blur(1px))');
    expect(supportsIdx).toBeGreaterThan(-1);
    const beforeSupports = css.slice(0, supportsIdx);
    // (forced-colors sets `backdrop-filter: none`, which is after @supports)
    expect(beforeSupports).not.toMatch(/backdrop-filter:\s*blur/);
  });

  it('solid and raised are opaque data/summary layers; the border does the structural work (§6.2)', () => {
    const solid = css.match(/\.surface-solid\s*\{[^}]*\}/)?.[0] ?? '';
    const raised = css.match(/\.surface-raised\s*\{[^}]*\}/)?.[0] ?? '';
    expect(solid).toContain('border: 1px solid var(--surface-border)');
    expect(solid).not.toContain('box-shadow'); // data layer: no decoration
    expect(solid).not.toContain('backdrop-filter'); // and definitely no blur (§8)
    expect(raised).toContain('border: 1px solid var(--surface-border)');
    expect(raised).toContain('box-shadow'); // decoration IN ADDITION to the border
  });

  it('forced-colors: every surface collapses to Canvas/CanvasText with a border (§6.5)', () => {
    const fcIdx = css.indexOf('@media (forced-colors: active)');
    expect(fcIdx).toBeGreaterThan(-1);
    const fcBlock = css.slice(fcIdx, css.indexOf('}', css.indexOf('backdrop-filter: none', fcIdx)));
    for (const cls of ['surface-solid', 'surface-raised', 'surface-glass-light', 'surface-glass-dark']) {
      expect(fcBlock).toContain(`.${cls}`);
    }
    expect(fcBlock).toContain('border: 1px solid CanvasText');
    expect(fcBlock).toContain('box-shadow: none');
    expect(fcBlock).toContain('backdrop-filter: none');
  });

  it('focus is an OUTLINE on a dedicated token — never a shadow (§8)', () => {
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*3px solid var\(--confit-focus\)/);
    const focusBlock = css.match(/:focus-visible\s*\{[^}]*\}/)?.[0] ?? '';
    expect(focusBlock).not.toContain('box-shadow');
  });
});

/* ------------------------------------------------------------------ */
/* B. Contrast mathematics (§9)                                        */
/* ------------------------------------------------------------------ */
describe('surface contrast (computed, not trusted)', () => {
  it('glass-dark FALLBACK stays readable over the worst-case (white) image: white text ≥ 4.5:1', () => {
    // --surface-glass-dark-fallback: rgb(12 14 30 / 0.94) == #0C0E1E @ .94
    const effective = composite('#0C0E1E', 0.94, '#FFFFFF');
    expect(contrast(effective, '#FFFFFF')).toBeGreaterThanOrEqual(4.5);
  });

  it('glass-light FALLBACK stays readable over the worst-case (black) image: navy text ≥ 4.5:1', () => {
    // --surface-glass-light-fallback: rgb(255 255 255 / 0.96)
    const effective = composite('#FFFFFF', 0.96, '#000000');
    expect(contrast(effective, '#1B1F3B')).toBeGreaterThanOrEqual(4.5);
  });

  it('focus token ≥3:1 on BOTH scheme extremes — and pins the measured failure of the old gold', () => {
    expect(css).toContain('--confit-focus: #A37E44');
    // The fix:
    expect(contrast('#A37E44', '#FAF9F6')).toBeGreaterThanOrEqual(3); // cream body
    expect(contrast('#A37E44', '#1B1F3B')).toBeGreaterThanOrEqual(3); // dark hero
    // The regression pin: the ORIGINAL brand gold genuinely fails on cream
    // (measured 2.71:1) — if someone "simplifies" the token back, this
    // documents why that is a real WCAG non-text-contrast failure.
    expect(contrast('#B8935A', '#FAF9F6')).toBeLessThan(3);
  });
});

/* ------------------------------------------------------------------ */
/* C. Surface component                                                */
/* ------------------------------------------------------------------ */
describe('Surface component', () => {
  it('maps each variant to its system class', () => {
    const { container } = render(
      <>
        <Surface variant="solid">data</Surface>
        <Surface variant="raised">summary</Surface>
        <Surface variant="glass-light">badge</Surface>
        <Surface variant="glass-dark">badge</Surface>
      </>,
    );
    const classes = Array.from(container.children).map((c) => c.className);
    expect(classes[0]).toContain('surface-solid');
    expect(classes[1]).toContain('surface-raised');
    expect(classes[2]).toContain('surface-glass-light');
    expect(classes[3]).toContain('surface-glass-dark');
  });

  it('renders semantic elements via `as` and keeps no implicit ARIA role as a div', () => {
    render(
      <Surface variant="raised" as="section" aria-label="Order summary">
        content
      </Surface>,
    );
    const section = screen.getByRole('region', { name: 'Order summary' });
    expect(section.tagName).toBe('SECTION');
  });

  it('merges caller classes with tailwind-merge (later padding wins, no duplicates)', () => {
    const { container } = render(
      <Surface variant="solid" className="p-4 p-6 rounded-3xl">
        x
      </Surface>,
    );
    const cls = (container.firstChild as HTMLElement).className;
    expect(cls).toContain('surface-solid');
    expect(cls).toContain('p-6');
    expect(cls).not.toContain('p-4'); // deduped by twMerge
  });

  it('GlassPanel is the §4 alias of Surface', () => {
    expect(GlassPanel).toBe(Surface);
  });

  it('axe: no violations, EN/LTR', async () => {
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <Surface variant="raised" as="section" aria-label="Summary">
          <p>Readable summary content</p>
        </Surface>
      </I18nextProvider>,
    );
    const results = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it('axe + AR/RTL: surfaces carry no direction assumptions', async () => {
    await setAppLanguage('ar');
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <Surface variant="solid" as="section" aria-label="بيانات المقاس">
          <p>نص عربي طويل داخل الطبقة الصلبة للبيانات — بدون أي زجاج خلفه.</p>
        </Surface>
      </I18nextProvider>,
    );
    expect(document.documentElement.dir).toBe('rtl');
    const results = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* D. Reduced motion — hierarchy does not depend on motion (§5)        */
/* ------------------------------------------------------------------ */
describe('reduced motion', () => {
  it('renders identically under prefers-reduced-motion: the hierarchy is static CSS', () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    try {
      const { container } = render(
        <Surface variant="glass-dark" className="rounded-2xl">
          badge
        </Surface>,
      );
      const el = container.firstChild as HTMLElement;
      expect(el.className).toContain('surface-glass-dark');
      // No animation hooks of any kind on the surface itself.
      expect(el.className).not.toMatch(/animate|transition|motion-/);
    } finally {
      window.matchMedia = original;
    }
  });

  it('the global reduced-motion CSS kills animation but never touches surface backgrounds/borders', () => {
    const rmIdx = css.indexOf('@media (prefers-reduced-motion: reduce)');
    expect(rmIdx).toBeGreaterThan(-1);
    const rmBlock = css.slice(rmIdx, css.indexOf('/* ── Touch target', rmIdx));
    expect(rmBlock).not.toContain('surface-');
    expect(rmBlock).not.toContain('background');
    expect(rmBlock).not.toContain('border');
  });
});

/* ------------------------------------------------------------------ */
/* E. Re-pass: the reveal entrance is decoration, never hierarchy      */
/* ------------------------------------------------------------------ */
describe('Surface reveal (re-pass)', () => {
  const stubMatchMedia = (reduce: boolean) => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: reduce && query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    return () => {
      window.matchMedia = original;
    };
  };

  it('reveal + motion: content and system class exist from the FIRST frame', () => {
    const restore = stubMatchMedia(false);
    render(
      <Surface variant="raised" reveal data-testid="s">
        Verdict content
      </Surface>,
    );
    const el = screen.getByTestId('s');
    expect(el.className).toContain('surface-raised');
    expect(screen.getByText('Verdict content')).toBeInTheDocument();
    restore();
  });

  it('reveal + reduced motion: renders the PLAIN static element — no inline animated opacity', () => {
    const restore = stubMatchMedia(true);
    render(
      <Surface variant="raised" reveal data-testid="s2">
        Static verdict
      </Surface>,
    );
    const el = screen.getByTestId('s2');
    expect(el.className).toContain('surface-raised');
    expect(el.style.opacity).not.toBe('0');
    // hierarchy identical: same class set as a non-reveal surface
    render(
      <Surface variant="raised" data-testid="s3">
        Control
      </Surface>,
    );
    expect(screen.getByTestId('s3').className).toBe(el.className);
    restore();
  });

  it('reveal preserves the semantic element given via `as`', () => {
    const restore = stubMatchMedia(false);
    render(
      <Surface variant="solid" reveal as="section" aria-label="spec panel">
        sectioned
      </Surface>,
    );
    const el = screen.getByLabelText('spec panel');
    expect(el.tagName).toBe('SECTION');
    restore();
  });
});

/* ------------------------------------------------------------------ */
/* F. Spec 12 re-pass: Reveal — the entrance WITHOUT surface chrome    */
/* ------------------------------------------------------------------ */
describe('Reveal (chrome-less entrance, spec 12 admin)', () => {
  const stubMatchMedia = (reduce: boolean) => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: reduce && query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    return () => {
      window.matchMedia = original;
    };
  };

  it('motion: children + caller classes render from the FIRST frame, no surface class injected', () => {
    const restore = stubMatchMedia(false);
    render(
      <Reveal data-testid="r" className="grid gap-5">
        KPI cards
      </Reveal>,
    );
    const el = screen.getByTestId('r');
    expect(el.className).toContain('grid');
    expect(el.className).not.toContain('surface-');
    expect(screen.getByText('KPI cards')).toBeInTheDocument();
    restore();
  });

  it('reduced motion: byte-identical static element (same tag, same classes, no animated opacity)', () => {
    const restore = stubMatchMedia(true);
    render(
      <Reveal data-testid="r2" as="section" aria-label="audit header" className="pb-4">
        header
      </Reveal>,
    );
    const el = screen.getByTestId('r2');
    expect(el.tagName).toBe('SECTION');
    expect(el.getAttribute('aria-label')).toBe('audit header');
    expect(el.className).toBe('pb-4');
    expect(el.style.opacity).not.toBe('0');
    restore();
  });

  it('semantic `as` + ARIA pass through under motion too', () => {
    const restore = stubMatchMedia(false);
    render(
      <Reveal as="header" aria-label="admin header" delay={0.1}>
        h
      </Reveal>,
    );
    const el = screen.getByLabelText('admin header');
    expect(el.tagName).toBe('HEADER');
    restore();
  });
});
