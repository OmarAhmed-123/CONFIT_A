/**
 * Spec 07 — Dark Hero + Light Card. §10 required coverage:
 *   axe (contrast structure) · broken image · long Arabic text · keyboard
 *   on the card · reduced motion — plus the §5 states (no-image fallback,
 *   constant scrim) and §9 acceptance (CTA before media in DOM order,
 *   image failure never breaks layout, no fake stock/price claims).
 *
 * Structure:
 *   A. HeroSection semantics (landmark + accessible heading, h1/h2 prop,
 *      CTA group precedes the aside in DOM order)
 *   B. HeroMedia honesty (constant scrim in every branch; broken Unsplash
 *      URL → HonestProductImage placeholder, layout intact; no-image state;
 *      lazy/async/responsive attributes)
 *   C. HeroLightCard (link variant: ONE keyboard-focusable control to a
 *      real route, no nested interactives; panel variant: no link role)
 *   D. axe EN + AR/RTL with a very long Arabic title · reduced motion
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { MemoryRouter } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';

import i18n, { setAppLanguage } from '../../../i18n/i18n';
import { HeroSection, HeroMedia, HeroLightCard } from '../HeroSection';

const wrap = (ui: React.ReactElement) =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{ui}</MemoryRouter>
    </I18nextProvider>,
  );

afterEach(async () => {
  cleanup();
  await setAppLanguage('en');
});

/* ------------------------------------------------------------------ */
/* A. Semantics                                                        */
/* ------------------------------------------------------------------ */
describe('HeroSection semantics', () => {
  it('renders a real <section> labelled by a real heading (§6.1)', () => {
    wrap(<HeroSection title="First look, minutes away" />);
    const region = screen.getByRole('region', { name: 'First look, minutes away' });
    expect(region.tagName).toBe('SECTION');
    expect(screen.getByRole('heading', { level: 1, name: 'First look, minutes away' })).toBeInTheDocument();
  });

  it('demotes to h2 when the host already owns the page h1', () => {
    wrap(<HeroSection title="Editorial" headingLevel="h2" />);
    expect(screen.getByRole('heading', { level: 2, name: 'Editorial' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument();
  });

  it('keeps the CTA group BEFORE the aside media in DOM order (§9 mobile fold)', () => {
    wrap(
      <HeroSection
        title="Hero"
        actions={<button type="button">Get my first look</button>}
        aside={<div data-testid="aside-panel">media</div>}
      />,
    );
    const cta = screen.getByRole('button', { name: 'Get my first look' });
    const aside = screen.getByTestId('aside-panel');
    // compareDocumentPosition: FOLLOWING means `aside` comes after `cta`.
    expect(cta.compareDocumentPosition(aside) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('never claims stock or price in its own copy (§9 — honesty is structural)', () => {
    const { container } = wrap(
      <HeroSection title="Hero" lede="Editorial lede" support="Support copy" />,
    );
    // The component itself ships zero commerce claims; any price/stock text
    // must come from the host binding real data.
    expect(container.textContent).not.toMatch(/in stock|only \d+ left|\$\d|SALE/i);
  });
});

/* ------------------------------------------------------------------ */
/* B. HeroMedia honesty                                                */
/* ------------------------------------------------------------------ */
describe('HeroMedia', () => {
  const src = 'https://images.unsplash.com/photo-123?w=900&auto=format&fit=crop&q=80';

  it('renders a CONSTANT scrim over the image — contrast never trusts the photo (§6.2/§8)', () => {
    wrap(
      <HeroMedia src={src} alt="Example look" unavailableLabel="Image unavailable" caption={<p>Caption</p>} />,
    );
    const scrim = screen.getByTestId('hero-scrim');
    expect(scrim).toHaveAttribute('aria-hidden', 'true');
    expect(scrim.className).toContain('from-black/85');
  });

  it('keeps the scrim and layout in the NO-IMAGE state (§5 contrast fallback)', () => {
    wrap(
      <HeroMedia src={null} alt="Example look" unavailableLabel="Image unavailable" caption={<p>Readable caption</p>} />,
    );
    expect(screen.getByTestId('hero-scrim')).toBeInTheDocument();
    expect(screen.getByText('Readable caption')).toBeInTheDocument();
    // No <img> and no fake placeholder photo.
    expect(document.querySelector('img')).toBeNull();
  });

  it('broken image → honest placeholder in the same box, caption still readable (§9)', () => {
    wrap(
      <HeroMedia src={src} alt="Example look" unavailableLabel="Image unavailable" caption={<p>Caption survives</p>} />,
    );
    const img = document.querySelector('img');
    expect(img).not.toBeNull();
    fireEvent.error(img!);
    // HonestProductImage swaps to its labelled placeholder — never a fake photo.
    expect(screen.getByRole('img', { name: /Example look — Image unavailable/ })).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByText('Caption survives')).toBeInTheDocument();
    expect(screen.getByTestId('hero-scrim')).toBeInTheDocument();
  });

  it('ships lazy/async/responsive loading attributes (§6.4)', () => {
    wrap(<HeroMedia src={src} alt="Example look" unavailableLabel="Image unavailable" />);
    const img = document.querySelector('img')!;
    expect(img).toHaveAttribute('loading', 'lazy');
    expect(img).toHaveAttribute('decoding', 'async');
    expect(img.getAttribute('srcset')).toContain('w=600');
    expect(img.getAttribute('srcset')).toContain('w=1400');
    expect(img).toHaveAttribute('sizes');
  });

  it('does not fabricate a srcset for non-Unsplash sources', () => {
    wrap(
      <HeroMedia src="https://cdn.example.com/own-asset.jpg" alt="Asset" unavailableLabel="Image unavailable" />,
    );
    expect(document.querySelector('img')!.getAttribute('srcset')).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/* C. HeroLightCard                                                    */
/* ------------------------------------------------------------------ */
describe('HeroLightCard', () => {
  it('link variant is ONE keyboard-focusable control to a real route (§6.3)', () => {
    wrap(
      <HeroLightCard to="/builder" label="Example styled look — open the outfit builder">
        <p>Inner editorial content</p>
      </HeroLightCard>,
    );
    const link = screen.getByRole('link', { name: 'Example styled look — open the outfit builder' });
    expect(link).toHaveAttribute('href', '/builder');
    // Natively focusable — reachable by Tab without tabindex hacks.
    link.focus();
    expect(link).toHaveFocus();
    // No nested interactive elements inside the link (SR trap / invalid HTML).
    expect(within(link).queryAllByRole('button')).toEqual([]);
    expect(within(link).queryAllByRole('link')).toEqual([]);
    expect(link.className).toContain('min-h-11');
  });

  it('panel variant renders no link/button role (hosts mount their own controls)', () => {
    wrap(
      <HeroLightCard>
        <input aria-label="Search the catalog" />
      </HeroLightCard>,
    );
    expect(screen.queryAllByRole('link')).toEqual([]);
    expect(screen.getByRole('textbox', { name: 'Search the catalog' })).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* D. axe · Arabic long text · reduced motion                          */
/* ------------------------------------------------------------------ */
describe('HeroSection a11y & i18n resilience', () => {
  const fullHero = (title: React.ReactNode) => (
    <HeroSection
      title={title}
      lede="lede"
      support="support"
      actions={<button type="button">CTA</button>}
      aside={
        <HeroLightCard to="/discover" label="Open discover">
          <HeroMedia
            src="https://images.unsplash.com/photo-1?w=900&q=80"
            alt="Look"
            unavailableLabel="Image unavailable"
            caption={<p>caption</p>}
          />
        </HeroLightCard>
      }
    />
  );

  it('axe: no violations in EN/LTR', async () => {
    const { container } = wrap(fullHero('Editorial hero'));
    const results = await axe(container, {
      // jsdom computes no real styles; these two need a browser and are
      // covered by the deployed checks instead.
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it('axe + layout survive AR/RTL with a very long Arabic title (§6.5/§10)', async () => {
    await setAppLanguage('ar');
    const longArabic =
      'إطلالتك الأولى المنسّقة بعناية فائقة جاهزة خلال دقائق معدودة مع اقتراحات مقاسات حقيقية وأسباب تنسيق واضحة ومفصّلة لكل قطعة من القطع المختارة لك';
    const { container } = wrap(fullHero(longArabic));
    expect(document.documentElement.dir).toBe('rtl');
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading).toHaveTextContent(longArabic);
    // Long text must wrap, not vanish: the section still exposes its name.
    expect(screen.getByRole('region', { name: longArabic })).toBeInTheDocument();
    const results = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it('is fully functional under prefers-reduced-motion (no motion dependency)', () => {
    // The hero is static CSS; nothing is gated behind an animation end.
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

    let clicked = false;
    wrap(
      <HeroSection
        title="Hero"
        actions={
          <button type="button" onClick={() => (clicked = true)}>
            Primary CTA
          </button>
        }
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Primary CTA' }));
    expect(clicked).toBe(true);
    expect(screen.getByRole('heading', { level: 1, name: 'Hero' })).toBeVisible();
  });
});
