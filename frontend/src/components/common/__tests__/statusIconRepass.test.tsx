/**
 * Spec 14 re-pass — the dynamic layer + the §8 purge:
 *   · a status CHANGE on a mounted StatusIcon replays its one-shot
 *     entrance (key-remount) and swaps the glyph atomically — previously
 *     loading→success→error transitions played nothing after first mount
 *   · each status owns its motion dialect, but under reduced motion the
 *     SAME transition renders as a plain static span — function identical
 *   · AsyncActionButton success no longer renders a unicode "✓" — the
 *     shared semantic shape, decorative beside the visible label
 *   · the Try-On studio error boundary announces with role=alert and the
 *     WARNING SHAPE, not an emoji
 *   · SOURCE GUARD: no production file may use ✓/✔/✗/✅/❌/⚠️ as a status
 *     channel or a bare `animate-spin` that ignores prefers-reduced-motion
 *     — the purge is pinned at the repo level, not just where we looked.
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import fs from 'node:fs';
import path from 'node:path';

import { StatusIcon, AsyncActionButton } from '../InteractionPrimitives';
import { TryOnStudioErrorBoundary } from '../../tryon/TryOnStudioErrorBoundary';
import { setAppLanguage } from '../../../i18n/i18n';

const stubMatchMedia = (reduce: boolean) => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: reduce && query.includes('prefers-reduced-motion'),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
};

beforeEach(async () => {
  cleanup();
  stubMatchMedia(false);
  await act(async () => { await setAppLanguage('en'); });
});

afterEach(() => cleanup());

/* ------------------------------------------------------------------ */
/* A. Status change replays the entrance (key remount)                 */
/* ------------------------------------------------------------------ */
describe('status transitions on a mounted icon', () => {
  it('success → error swaps the glyph and the data-status atomically', () => {
    const { rerender } = render(<StatusIcon status="success" data-testid="icon" />);
    const before = screen.getByTestId('icon');
    expect(before).toHaveAttribute('data-status', 'success');

    rerender(<StatusIcon status="error" data-testid="icon" />);
    const after = screen.getByTestId('icon');
    expect(after).toHaveAttribute('data-status', 'error');
    // key={status} forces a REMOUNT — the entrance is replayed, and the
    // element identity changes (this is what made the animation fire).
    expect(after).not.toBe(before);
    // exactly one glyph — no stale sibling left behind
    expect(screen.getAllByTestId('icon')).toHaveLength(1);
  });

  it('loading → success: the spinner leaves with the status, no double icon', () => {
    const { rerender } = render(<StatusIcon status="loading" data-testid="icon" />);
    expect(screen.getByTestId('icon').querySelector('svg')?.getAttribute('class'))
      .toContain('motion-safe:animate-spin');
    rerender(<StatusIcon status="success" data-testid="icon" />);
    const icons = screen.getAllByTestId('icon');
    expect(icons).toHaveLength(1);
    expect(icons[0]).toHaveAttribute('data-status', 'success');
    expect(icons[0].querySelector('svg')?.getAttribute('class') ?? '')
      .not.toContain('animate-spin');
  });

  it('reduced motion: the same transition renders plain static spans', () => {
    stubMatchMedia(true);
    const { rerender } = render(<StatusIcon status="success" data-testid="icon" />);
    rerender(<StatusIcon status="error" data-testid="icon" />);
    const el = screen.getByTestId('icon');
    expect(el).toHaveAttribute('data-status', 'error');
    // framer sets an inline transform during entrances; the static branch
    // must have NO inline style transform at all.
    expect(el.style.transform).toBe('');
  });
});

/* ------------------------------------------------------------------ */
/* B. AsyncActionButton: the "✓" is gone, the shape arrived            */
/* ------------------------------------------------------------------ */
describe('AsyncActionButton success glyph', () => {
  it('renders the semantic success SHAPE, never a unicode check', async () => {
    vi.useFakeTimers();
    try {
      render(
        <AsyncActionButton
          onAction={() => 'success'}
          idleLabel="Save look"
          pendingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Could not save"
        />,
      );
      fireEvent.click(screen.getByRole('button', { name: /save look/i }));
      await act(async () => { await vi.advanceTimersByTimeAsync(50); });
      const button = screen.getByRole('button');
      expect(button.textContent).not.toContain('✓');
      const shape = button.querySelector('[data-status="success"]');
      expect(shape).not.toBeNull();
      expect(shape!).toHaveAttribute('aria-hidden', 'true');
    } finally {
      vi.useRealTimers();
    }
  });
});

/* ------------------------------------------------------------------ */
/* C. Studio error boundary: alert + warning shape, no emoji           */
/* ------------------------------------------------------------------ */
describe('TryOnStudioErrorBoundary fallback', () => {
  it('role=alert with the warning shape — not an emoji badge', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const Boom: React.FC = () => { throw new Error('render exploded'); };
    render(
      <MemoryRouter>
        <TryOnStudioErrorBoundary>
          <Boom />
        </TryOnStudioErrorBoundary>
      </MemoryRouter>,
    );
    const alert = screen.getByRole('alert');
    expect(alert.textContent).not.toMatch(/[✓✔✗✅❌⚠]/u);
    expect(alert.querySelector('[data-status="warning"]')).not.toBeNull();
    // retry stays usable
    expect(screen.getAllByRole('button').length).toBeGreaterThan(0);
    spy.mockRestore();
  });
});

/* ------------------------------------------------------------------ */
/* D. SOURCE GUARD — the purge is repo-wide and stays that way         */
/* ------------------------------------------------------------------ */
describe('source guard (§8/§7)', () => {
  const SRC = path.resolve(__dirname, '../../..');
  const offenders: { file: string; line: number; text: string }[] = [];
  const spinOffenders: { file: string; line: number }[] = [];

  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
        walk(full);
      } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.test.')) {
        const lines = fs.readFileSync(full, 'utf8').split('\n');
        lines.forEach((line, i) => {
          const code = line.split('//')[0]; // ignore trailing comments
          if (/[✓✔✗✅❌⚠]/u.test(code) && !/['"`]use/.test(code)) {
            offenders.push({ file: full, line: i + 1, text: line.trim().slice(0, 80) });
          }
          if (/(?<!motion-safe:)animate-spin/.test(code)) {
            spinOffenders.push({ file: full, line: i + 1 });
          }
        });
      }
    }
  };

  it('no production .tsx uses unicode/emoji as a status channel', () => {
    walk(SRC);
    expect(offenders).toEqual([]);
  });

  it('no LOCALE STRING carries a unicode status glyph — the purge covers i18n too', () => {
    // Found live on Vercel: the .tsx sweep was clean while the shipped
    // bundle still carried '✓ Within budget' etc. — the glyphs lived in
    // en.json/ar.json. Status shape belongs to StatusIcon, words to i18n.
    for (const loc of ['en', 'ar']) {
      const raw = fs.readFileSync(path.join(SRC, 'i18n', `${loc}.json`), 'utf8');
      const hits = raw.split('\n')
        .map((l, i) => ({ line: i + 1, text: l }))
        .filter(({ text }) => /[✓✔✗✅❌⚠]/u.test(text));
      expect(hits, `${loc}.json`).toEqual([]);
    }
  });

  it('every animate-spin is motion-safe gated', () => {
    expect(spinOffenders).toEqual([]);
  });
});
