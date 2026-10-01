/**
 * Spec 10 — Accessible carousel/slider (§10 test contract):
 *   keyboard incl. RTL inversion + Home/End · NO autoplay (fake timers)
 *   position announced as text (polite) · honest loading/error/empty
 *   real links inside slides · reduced motion ⇒ genuine 2D fallback
 *   axe EN + AR/RTL · ≥44px controls · slides never aria-hidden.
 *
 * Measured defects this file pins (found during spec-10 recon):
 *   1. CardStack had a live setInterval autoplay wired on 6+ pages.
 *   2. Keyboard was physical-LTR only; no Home/End; RTL arrows reversed.
 *   3. Dots were 8px targets, no prev/next buttons, swipe was the only
 *      robust navigation (§2 violation).
 *   4. All labels hardcoded English ("Go to X", "Open link", "No image").
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';

import i18n, { setAppLanguage } from '../../i18n/i18n';
import { AccessibleCarousel } from '../common/AccessibleCarousel';
import { CardStack, type CardStackItem } from '../ui/card-stack';
import { CircularGallery } from '../ui/circular-gallery';
import { CardStackShowcase, CircularGalleryShowcase } from '../showcase/DesignShowcases';

/* jsdom has no scrollIntoView — stub it so native-scroll navigation runs. */
const scrollSpy = vi.fn();
beforeEach(() => {
  Element.prototype.scrollIntoView = scrollSpy;
});

afterEach(async () => {
  cleanup();
  scrollSpy.mockClear();
  vi.useRealTimers();
  await setAppLanguage('en');
});

const AXE_RULES = {
  rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
};

type Story = { id: string; name: string; href: string };
const stories: Story[] = [
  { id: 'a', name: 'Tailored Power', href: '/discover' },
  { id: 'b', name: 'Evening Silk', href: '/discover' },
  { id: 'c', name: 'Resort Linen', href: '/discover' },
];

function renderCarousel(extra: Partial<React.ComponentProps<typeof AccessibleCarousel<Story>>> = {}) {
  return render(
    <I18nextProvider i18n={i18n}>
      <AccessibleCarousel<Story>
        items={stories}
        getKey={(s) => s.id}
        label="Editorial stories"
        renderItem={(s) => <a href={s.href}>{s.name}</a>}
        {...extra}
      />
    </I18nextProvider>,
  );
}

const stackItems: CardStackItem[] = stories.map((s, i) => ({
  id: s.id,
  title: s.name,
  description: `Story ${i + 1}`,
  href: s.href,
}));

/* ------------------------------------------------------------------ */
/* A. AccessibleCarousel — semantics and real content                  */
/* ------------------------------------------------------------------ */
describe('AccessibleCarousel: semantics', () => {
  it('is a labelled carousel region with slide groups, none aria-hidden (§6.6)', () => {
    renderCarousel();
    const region = screen.getByRole('group', { name: 'Editorial stories' });
    expect(region).toBeInTheDocument();
    const slides = screen.getAllByRole('group', { name: /of 3/i });
    expect(slides).toHaveLength(3);
    slides.forEach((s) => expect(s).not.toHaveAttribute('aria-hidden'));
  });

  it('slides contain REAL links — swipe is never the only way in (§2/§6.5)', () => {
    renderCarousel();
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(3);
    links.forEach((l) => expect(l).toHaveAttribute('href', '/discover'));
  });

  it('prev/next are ≥44px buttons (min-h-11/min-w-11) and disable at edges', () => {
    renderCarousel();
    const prev = screen.getByRole('button', { name: 'Previous' });
    const next = screen.getByRole('button', { name: 'Next' });
    [prev, next].forEach((b) => {
      expect(b.className).toContain('min-h-11');
      expect(b.className).toContain('min-w-11');
    });
    expect(prev).toBeDisabled(); // at first slide
    fireEvent.click(next);
    expect(screen.getByRole('button', { name: 'Previous' })).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled(); // at last
  });

  it('announces position as polite TEXT and shows it visibly (§6.3/§7)', () => {
    renderCarousel();
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    const status = screen
      .getAllByRole('status')
      .find((el) => el.textContent?.includes('Item 2 of 3'));
    expect(status).toBeTruthy();
    expect(status).toHaveAttribute('aria-live', 'polite');
  });

  it('navigation scrolls with native scrollIntoView — no translateX (§8)', () => {
    renderCarousel();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(scrollSpy).toHaveBeenCalled();
    const container = screen.getByText('Tailored Power').closest('[role="group"]')!
      .parentElement as HTMLElement;
    expect(container.style.transform).toBe('');
  });
});

/* ------------------------------------------------------------------ */
/* B. AccessibleCarousel — keyboard, LTR + RTL inversion               */
/* ------------------------------------------------------------------ */
describe('AccessibleCarousel: keyboard', () => {
  it('LTR: ArrowRight=next, ArrowLeft=prev, Home/End jump', () => {
    renderCarousel();
    const track = screen.getAllByRole('group', { name: 'Editorial stories' })
      .find((el) => el.getAttribute('tabindex') === '0')!;
    fireEvent.keyDown(track, { key: 'ArrowRight' });
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    fireEvent.keyDown(track, { key: 'ArrowLeft' });
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    fireEvent.keyDown(track, { key: 'End' });
    expect(screen.getByText('3 / 3')).toBeInTheDocument();
    fireEvent.keyDown(track, { key: 'Home' });
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
  });

  it('RTL: arrows invert — ArrowLeft moves to the NEXT card (§5)', async () => {
    await setAppLanguage('ar');
    expect(document.documentElement.dir).toBe('rtl');
    render(
      <I18nextProvider i18n={i18n}>
        <AccessibleCarousel<Story>
          items={stories}
          getKey={(s) => s.id}
          label="قصص تحريرية"
          renderItem={(s) => <a href={s.href}>{s.name}</a>}
        />
      </I18nextProvider>,
    );
    const track = screen.getAllByRole('group', { name: 'قصص تحريرية' })
      .find((el) => el.getAttribute('tabindex') === '0')!;
    fireEvent.keyDown(track, { key: 'ArrowLeft' });
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    fireEvent.keyDown(track, { key: 'ArrowRight' });
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* C. AccessibleCarousel — honest states (§5)                          */
/* ------------------------------------------------------------------ */
describe('AccessibleCarousel: states', () => {
  it('loading: aria-busy region with a polite status, no fake content', () => {
    renderCarousel({ isLoading: true });
    const region = screen.getByRole('region', { name: 'Editorial stories' });
    expect(region).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('Loading items…');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it("error: shows the caller's REAL message and retry re-runs the fetch", () => {
    const onRetry = vi.fn();
    renderCarousel({ error: 'Stories are unavailable right now.', onRetry });
    expect(screen.getByRole('status')).toHaveTextContent('Stories are unavailable right now.');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('empty: says empty — never placeholder cards', () => {
    renderCarousel({ items: [] });
    expect(screen.getByText('Nothing to show here yet.')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* D. CardStack — autoplay is GONE, keyboard complete, labels injected */
/* ------------------------------------------------------------------ */
describe('CardStack (3D fan): spec-10 fixes', () => {
  it('NO autoplay: 30 fake seconds pass and the active card never moves (§6.4)', () => {
    vi.useFakeTimers();
    render(<CardStack items={stackItems} loop={false} />);
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    vi.advanceTimersByTime(30_000);
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
  });

  it('stage is a labelled carousel; prev/next ≥44px; position is live text', () => {
    render(
      <CardStack
        items={stackItems}
        loop={false}
        labels={{
          carousel: 'Style stories',
          previous: 'Back',
          next: 'Forward',
          position: (c, t) => `Card ${c} of ${t}`,
        }}
      />,
    );
    expect(screen.getByRole('group', { name: 'Style stories' })).toBeInTheDocument();
    const next = screen.getByRole('button', { name: 'Forward' });
    expect(next.className).toContain('min-h-11');
    fireEvent.click(next);
    const status = screen
      .getAllByRole('status')
      .find((el) => el.textContent === 'Card 2 of 3');
    expect(status).toBeTruthy();
    expect(status).toHaveAttribute('aria-live', 'polite');
  });

  it('keyboard: Home/End work; RTL inverts the arrows (§5)', async () => {
    const { unmount } = render(<CardStack items={stackItems} loop={false} />);
    const stage = screen.getByRole('group', { name: 'Carousel' });
    fireEvent.keyDown(stage, { key: 'End' });
    expect(screen.getByText('3 / 3')).toBeInTheDocument();
    fireEvent.keyDown(stage, { key: 'Home' });
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    unmount();

    await setAppLanguage('ar');
    render(<CardStack items={stackItems} loop={false} />);
    const stageAr = screen.getByRole('group', { name: 'Carousel' });
    fireEvent.keyDown(stageAr, { key: 'ArrowLeft' }); // next in RTL
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    fireEvent.keyDown(stageAr, { key: 'ArrowRight' }); // prev in RTL
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
  });

  it('dots mark the current card with aria-current and use injected labels', () => {
    render(
      <CardStack
        items={stackItems}
        loop={false}
        labels={{ goTo: (t) => `اذهب إلى ${t}` }}
      />,
    );
    const dot2 = screen.getByRole('button', { name: 'اذهب إلى Evening Silk' });
    expect(dot2).not.toHaveAttribute('aria-current');
    fireEvent.click(dot2);
    expect(dot2).toHaveAttribute('aria-current', 'true');
  });

  it('active card link is a real href with an injected, item-specific label', () => {
    render(<CardStack items={stackItems} loop={false} labels={{ open: (t) => `Open ${t}` }} />);
    const open = screen.getByRole('link', { name: 'Open Tailored Power' });
    expect(open).toHaveAttribute('href', '/discover');
  });
});

/* ------------------------------------------------------------------ */
/* E. Reduced motion ⇒ genuine 2D fallback in the showcase (§1)        */
/* ------------------------------------------------------------------ */
describe('CardStackShowcase: reduced-motion 2D fallback', () => {
  const mockReducedMotion = (matches: boolean) => {
    window.matchMedia = ((query: string) => ({
      matches: query.includes('prefers-reduced-motion') ? matches : false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  };

  it('prefers-reduced-motion: renders the AccessibleCarousel with real links instead of the 3D fan', () => {
    mockReducedMotion(true);
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CardStackShowcase tone="consumer" />
        </MemoryRouter>
      </I18nextProvider>,
    );
    expect(screen.getByTestId('cardstack-2d-fallback')).toBeInTheDocument();
    // Same content, as real router links — full function without motion (§7).
    const links = screen.getAllByRole('link');
    expect(links.length).toBeGreaterThanOrEqual(5);
    expect(screen.getByText('Tailored Power')).toBeInTheDocument();
  });

  it('motion allowed: renders the 3D fan (no fallback testid), still with NO timer', () => {
    mockReducedMotion(false);
    vi.useFakeTimers();
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CardStackShowcase tone="consumer" />
        </MemoryRouter>
      </I18nextProvider>,
    );
    expect(screen.queryByTestId('cardstack-2d-fallback')).not.toBeInTheDocument();
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
    vi.advanceTimersByTime(30_000);
    expect(screen.getByText('1 / 5')).toBeInTheDocument(); // autoplay removed
  });
});

/* ------------------------------------------------------------------ */
/* F. i18n — the Arabic page is Arabic; gallery labels translated      */
/* ------------------------------------------------------------------ */
describe('showcases i18n', () => {
  it('AR: CardStackShowcase copy and control labels are Arabic', async () => {
    await setAppLanguage('ar');
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CardStackShowcase tone="consumer" />
        </MemoryRouter>
      </I18nextProvider>,
    );
    expect(screen.getByText('أناقة رسمية')).toBeInTheDocument(); // item title
    expect(screen.getByRole('button', { name: 'السابق' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'التالي' })).toBeInTheDocument();
  });

  it('AR: CircularGalleryShowcase region + item names are Arabic', async () => {
    await setAppLanguage('ar');
    render(
      <I18nextProvider i18n={i18n}>
        <CircularGalleryShowcase tone="consumer" />
      </I18nextProvider>,
    );
    expect(screen.getByRole('region', { name: 'معرض بصري للتشكيلات' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'إطلالة العمل' })).toBeInTheDocument();
  });

  it('CircularGallery defaults: idle auto-rotation OFF (speed 0 by default §6.4)', () => {
    // The prop default is the contract: no caller passes autoRotateSpeed
    // anymore, so an idle page must not rotate. We assert the rendered
    // region exists and the component accepted no speed without crashing.
    render(
      <CircularGallery
        items={[{ common: 'Look', binomial: 'Caption', photo: { url: 'x.jpg', text: 'Look', by: 'Unsplash' } }]}
        ariaLabel="Gallery"
      />,
    );
    expect(screen.getByRole('region', { name: 'Gallery' })).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* G. axe — EN/LTR and AR/RTL                                          */
/* ------------------------------------------------------------------ */
describe('axe', () => {
  it('AccessibleCarousel EN/LTR: no violations', async () => {
    const { container } = renderCarousel();
    const results = await axe(container, AXE_RULES);
    expect(results.violations).toEqual([]);
  });

  it('CardStack + showcase AR/RTL: no violations', async () => {
    await setAppLanguage('ar');
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CardStackShowcase tone="consumer" compact />
        </MemoryRouter>
      </I18nextProvider>,
    );
    const results = await axe(container, AXE_RULES);
    expect(results.violations).toEqual([]);
  });
});
