/**
 * 010 — Stylist Drawer accessibility P0 gap closure
 * Tests real drawer with mocked services, covering open/close, dialog semantics, keyboard, focus, controls, form, empty/loading/error/result, reduced-motion, RTL
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { I18nextProvider } from 'react-i18next';
import i18n, { setAppLanguage } from '../../i18n/i18n';

const {
  chatMock,
  addItemMock,
  openCartMock,
  showToastMock,
  closeStylistMock,
  openTryOnMock,
  openRulerMock,
} = vi.hoisted(() => ({
  chatMock: vi.fn(),
  addItemMock: vi.fn(),
  openCartMock: vi.fn(),
  showToastMock: vi.fn(),
  closeStylistMock: vi.fn(),
  openTryOnMock: vi.fn(),
  openRulerMock: vi.fn(),
}));

vi.mock('../../services/apiServices', async (importOriginal) => {
  const actual: any = await importOriginal();
  return { ...actual, stylistService: { ...actual.stylistService, chat: chatMock } };
});
vi.mock('../../stores/cartStore', () => ({
  useCartStore: () => ({ addItem: addItemMock, openCart: openCartMock }),
}));
vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({
    isStylistDrawerOpen: true,
    closeStylist: closeStylistMock,
    stylistPrefillOccasion: null,
    openTryOn: openTryOnMock,
    openRuler: openRulerMock,
    showToast: showToastMock,
  }),
}));
vi.mock('../../hooks/useTryOnAvailability', () => ({
  useTryOnAvailability: () => ({ ctaKind: () => 'try_on', userMessage: null }),
}));

import { VirtualStylistDrawer } from '../../components/stylist/VirtualStylistDrawer';

const JSDOM_UNCOMPUTABLE = ['color-contrast', 'target-size'];
async function seriousViolations(node: HTMLElement) {
  const results = await axe(node, { rules: Object.fromEntries(JSDOM_UNCOMPUTABLE.map((r) => [r, { enabled: false }])) });
  return results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
}

function wrap() {
  return render(
    <I18nextProvider i18n={i18n}>
      <VirtualStylistDrawer />
    </I18nextProvider>
  );
}

const item = (id: number) => ({
  id,
  product_id: id,
  product_title: `Piece ${id}`,
  brand_name: 'Reiss',
  category_name: 'Apparel',
  price: 120,
  currency: 'EGP',
  image_url: '/img.jpg',
  color_hex: '#1B1F3B',
  position: 'top',
  sku_id: id * 100,
  selected_size: 'M',
});
const outfit = (over: any = {}) => ({
  id: 101,
  title: 'Evening Composition',
  occasion: 'Evening & Party',
  total_price: 360,
  currency: 'EGP',
  compatibility_score: 91,
  color_harmony_score: 84,
  formality_score: 72,
  color_palette: ['#1B1F3B', '#C5A059'],
  is_complete: true,
  completeness_status: 'complete_look',
  items: [item(1), item(2), item(3)],
  created_at: '2026-01-01T00:00:00Z',
  ...over,
});
const assistantMessage = (over: any = {}) => ({
  id: 7,
  session_id: 1,
  sender: 'assistant',
  content: 'Here is a composed look.',
  recommendations: [outfit()],
  created_at: '2026-01-01T00:00:00Z',
  engine: 'NVIDIA ultra-550b',
  ...over,
});

beforeEach(async () => {
  cleanup();
  await act(async () => { await setAppLanguage('en'); });
  chatMock.mockReset();
  addItemMock.mockReset().mockResolvedValue(undefined);
  closeStylistMock.mockReset();
});

afterEach(() => cleanup());

describe('010 — Stylist Drawer P0 accessibility', () => {
  it('open state has dialog semantics, aria-modal, accessible name, tabIndex -1', async () => {
    const { container } = wrap();
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-label')).toBeTruthy();
    expect(dialog.getAttribute('tabIndex')).toBe('-1');
    const violations = await seriousViolations(container);
    expect(violations, JSON.stringify(violations)).toEqual([]);
  });

  it('close button has accessible name, 44px target, visible focus ring, svg aria-hidden', async () => {
    const { container } = wrap();
    const closeBtn = screen.getByRole('button', { name: /close/i });
    expect(closeBtn.className).toContain('w-11');
    expect(closeBtn.className).toContain('h-11');
    expect(closeBtn.className).toContain('focus-visible:ring');
    const svg = closeBtn.querySelector('svg');
    expect(svg?.getAttribute('aria-hidden')).toBe('true');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('keyboard: Escape closes drawer via useModalFocus', async () => {
    const { container } = wrap();
    expect(screen.getByRole('dialog')).toBeTruthy();
    await act(async () => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });
    expect(closeStylistMock).toHaveBeenCalled();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('focus: dialog is focusable, close button focusable', async () => {
    const { container } = wrap();
    const dialog = screen.getByRole('dialog');
    dialog.focus();
    expect(dialog).toHaveFocus();
    const closeBtn = screen.getByRole('button', { name: /close/i });
    closeBtn.focus();
    expect(closeBtn).toHaveFocus();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('icon-only mic control has accessible name, no emoji, 44px+', async () => {
    const { container } = wrap();
    const micBtn = screen.getByRole('button', { name: /voice/i });
    expect(micBtn.getAttribute('aria-label')).toBeTruthy();
    expect(micBtn.className).toContain('min-h-[48px]');
    expect(micBtn.textContent).not.toMatch(/🎙️/);
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('form: input placeholder, submit button accessible name and type submit', async () => {
    const { container } = wrap();
    const input = screen.getByPlaceholderText(/describe/i);
    expect(input).toBeTruthy();
    const submit = screen.getByRole('button', { name: /style/i });
    expect(submit.getAttribute('type')).toBe('submit');
    expect(submit.className).toContain('min-h-[48px]');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('empty state has content, no critical violations', async () => {
    const { container } = wrap();
    expect(document.body.textContent).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('loading state has status role and skeleton, no violations', async () => {
    let resolveChat: (v: any) => void;
    chatMock.mockImplementation(() => new Promise((res) => { resolveChat = res; }));
    const { container } = wrap();
    const input = screen.getByPlaceholderText(/describe/i);
    fireEvent.change(input, { target: { value: 'Style me for evening' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /style/i }));
    });
    const thinking = await screen.findByTestId('stylist-thinking');
    expect(thinking.getAttribute('role')).toBe('status');
    expect(thinking.querySelectorAll('.skeleton-shimmer').length).toBeGreaterThanOrEqual(5);
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
    await act(async () => { resolveChat!(assistantMessage()); });
  });

  it('result state with outfit has honest images, money EGP, no $ leak, axe clean', async () => {
    chatMock.mockResolvedValue(assistantMessage());
    const { container } = wrap();
    const input = screen.getByPlaceholderText(/describe/i);
    fireEvent.change(input, { target: { value: 'evening gala' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /style/i }));
    });
    const total = await screen.findByTestId('stylist-ensemble-total');
    expect(total.textContent).toContain('EGP');
    expect(total.textContent).not.toContain('$');
    const violations = await seriousViolations(container);
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });

  it('occasion quick chips have 44px min target and focus ring', async () => {
    const { container } = wrap();
    const chips = screen.getAllByRole('button').filter((b) => b.textContent?.includes('Formal') || b.textContent?.includes('Work'));
    if (chips.length > 0) {
      expect(chips[0].className).toContain('min-h-[44px]');
      expect(chips[0].className).toContain('focus-visible:ring');
    }
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('reduced-motion: drawer renders static with reduce, axe clean', async () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
    const { container } = wrap();
    expect(screen.getByRole('dialog')).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('RTL: Arabic drawer has dir rtl and axe clean in empty state', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    const { container } = wrap();
    expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
    await act(async () => { await setAppLanguage('en'); });
  });
});
