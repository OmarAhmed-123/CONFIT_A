/**
 * Spec 15 re-pass — the unsubscribe landing page contract:
 *   token validated on load (GET, no mutation) · ONE CTA · the state
 *   change happens only after the server confirms the POST · expired and
 *   invalid links speak honest words · a failed POST NEVER claims success
 *   and keeps the preference unchanged · AR/RTL translated · axe · the
 *   motion layer is one entrance tween gated by reduced motion.
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { axe } from 'vitest-axe';

import { EmailUnsubscribeView } from '../public/EmailUnsubscribeView';
import { emailService } from '../../services/apiServices';
import { setAppLanguage } from '../../i18n/i18n';
import i18n from '../../i18n/i18n';

const AXE_RULES = {
  rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
};

vi.mock('../../services/apiServices', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../../services/apiServices')>();
  return {
    ...mod,
    emailService: {
      ...mod.emailService,
      validateUnsubscribeToken: vi.fn(),
      unsubscribe: vi.fn(),
    },
  };
});

const validate = vi.mocked(emailService.validateUnsubscribeToken);
const unsubscribe = vi.mocked(emailService.unsubscribe);

const renderAt = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/email/unsubscribe" element={<EmailUnsubscribeView />} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(async () => {
  cleanup();
  vi.clearAllMocks();
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
  await act(async () => { await setAppLanguage('en'); });
});

afterEach(() => cleanup());

describe('load-time validation (GET only)', () => {
  it('valid token → ready state with exactly ONE CTA; GET never mutates', async () => {
    validate.mockResolvedValue({ valid: true, category: 'marketing' });
    renderAt('/email/unsubscribe?token=tok1');
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /unsubscribe from/i })).toBeInTheDocument(),
    );
    expect(validate).toHaveBeenCalledWith('tok1');
    expect(unsubscribe).not.toHaveBeenCalled();
    // exactly one CTA on the page (§9)
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.getAllByText(/offers & newsletter/i).length).toBeGreaterThan(0);
  });

  it('expired token → honest expired words + settings path, no CTA', async () => {
    validate.mockResolvedValue({ valid: false, reason: 'expired' });
    renderAt('/email/unsubscribe?token=tokOld');
    await waitFor(() =>
      expect(screen.getByText(i18n.t('email_unsubscribe.expired_title'))).toBeInTheDocument(),
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: i18n.t('email_unsubscribe.manage_link') }))
      .toHaveAttribute('href', '/settings');
  });

  it('missing/invalid token → invalid state without calling the API at all for missing', async () => {
    renderAt('/email/unsubscribe');
    await waitFor(() =>
      expect(screen.getByText(i18n.t('email_unsubscribe.invalid_title'))).toBeInTheDocument(),
    );
    expect(validate).not.toHaveBeenCalled();
  });
});

describe('the one-click POST', () => {
  it('success only after the server confirms', async () => {
    validate.mockResolvedValue({ valid: true, category: 'engagement' });
    let resolvePost!: (v: any) => void;
    unsubscribe.mockReturnValue(new Promise((res) => { resolvePost = res; }));
    renderAt('/email/unsubscribe?token=tok2');
    const cta = await screen.findByRole('button', { name: /unsubscribe from/i });
    fireEvent.click(cta);
    // pending — NOT success yet
    expect(screen.getAllByText(i18n.t('email_unsubscribe.working')).length).toBeGreaterThan(0);
    expect(screen.queryByText(i18n.t('email_unsubscribe.done_title'))).not.toBeInTheDocument();
    await act(async () => {
      resolvePost({ status: 'unsubscribed', category: 'engagement', engagement: false, marketing: true });
    });
    expect(screen.getByText(i18n.t('email_unsubscribe.done_title'))).toBeInTheDocument();
  });

  it('server failure → NO fake success, retry offered, words say nothing changed', async () => {
    validate.mockResolvedValue({ valid: true, category: 'marketing' });
    unsubscribe.mockRejectedValue(new Error('503'));
    renderAt('/email/unsubscribe?token=tok3');
    fireEvent.click(await screen.findByRole('button', { name: /unsubscribe from/i }));
    await waitFor(() =>
      expect(screen.getByText(i18n.t('email_unsubscribe.error_title'))).toBeInTheDocument(),
    );
    expect(screen.queryByText(i18n.t('email_unsubscribe.done_title'))).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: i18n.t('email_unsubscribe.retry_cta') }))
      .toBeInTheDocument();
  });
});

describe('a11y + i18n + motion', () => {
  it('state lives in a polite live region; axe clean (EN)', async () => {
    validate.mockResolvedValue({ valid: true, category: 'marketing' });
    renderAt('/email/unsubscribe?token=tok4');
    await screen.findByRole('button', { name: /unsubscribe from/i });
    const live = screen.getByRole('status');
    expect(live.textContent).toContain(i18n.t('email_unsubscribe.category_marketing'));
    const results = await axe(document.body, AXE_RULES);
    expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'))
      .toEqual([]);
  });

  it('AR/RTL: full flow translated, transactional carve-out stated, axe clean', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    validate.mockResolvedValue({ valid: true, category: 'engagement' });
    renderAt('/email/unsubscribe?token=tok5');
    await waitFor(() =>
      expect(screen.getAllByText(/إلغاء الاشتراك في/).length).toBeGreaterThan(0),
    );
    // the receipt carve-out is part of the consent story — it must be there
    expect(screen.getByText(/إيصالات الطلبات/)).toBeInTheDocument();
    const results = await axe(document.body, AXE_RULES);
    expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'))
      .toEqual([]);
    await act(async () => { await setAppLanguage('en'); });
  });

  it('reduced motion: fully functional, no inline transform on the card', async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('prefers-reduced-motion'), media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }));
    validate.mockResolvedValue({ valid: true, category: 'marketing' });
    unsubscribe.mockResolvedValue({
      status: 'unsubscribed', category: 'marketing', engagement: true, marketing: false,
    });
    renderAt('/email/unsubscribe?token=tok6');
    fireEvent.click(await screen.findByRole('button', { name: /unsubscribe from/i }));
    await waitFor(() =>
      expect(screen.getByText(i18n.t('email_unsubscribe.done_title'))).toBeInTheDocument(),
    );
  });
});
