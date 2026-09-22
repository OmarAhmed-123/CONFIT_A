/**
 * The consumer-side half of the 2026-09-22 try-on honesty closure.
 *
 * What went wrong
 * ---------------
 * `/catalog/capabilities` said `vton_gpu_ready: true` while
 * `/try-on/capabilities` said `temporarily_unavailable`, AND no consumer
 * surface read either one. Eight entry points opened a try-on flow
 * unconditionally, so the honest backend verdict and the dishonest flag were
 * both inert: a shopper still uploaded a photo and waited for a render that
 * could not happen. The audit report phrased the requirement as "the presence
 * of a Try-On button does not mean the implementation works" — these tests
 * pin the rule that makes the button stop implying it does.
 *
 * The rule under test: when the engine cannot render, a try-on control must
 * offer the capability that DOES work (the no-photo fit check) under its own
 * name, and must never route into a render.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import {
  useTryOnAvailability,
  resolveTryOnCtaKind,
  engineStateMessage,
  engineStateIsWarnable,
} from '../useTryOnAvailability';

vi.mock('../../services/apiServices', () => ({
  tryOnService: { getCapabilities: vi.fn() },
}));

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
};

async function mockEngine(engineState: string | null, engine: unknown = null) {
  const { tryOnService } = await import('../../services/apiServices');
  (tryOnService.getCapabilities as ReturnType<typeof vi.fn>).mockResolvedValue({
    provider: 'fashn_vton_segfee',
    engine_state: engineState,
    supported_slots: [],
    unsupported_slots: [],
    products: [],
    engine,
    sla: null,
    user_message: 'backend english prose that must NOT be the user message',
  });
}

describe('resolveTryOnCtaKind — the honesty rule, pure', () => {
  it('offers a render when the engine can render', () => {
    expect(resolveTryOnCtaKind(true, true)).toBe('render');
    expect(resolveTryOnCtaKind(true, false)).toBe('render');
  });

  it('degrades to the fit check when a render is impossible and one exists', () => {
    expect(resolveTryOnCtaKind(false, true)).toBe('fit_check');
  });

  it('blocks rather than lying when there is nowhere honest to send the user', () => {
    expect(resolveTryOnCtaKind(false, false)).toBe('blocked');
  });

  it('does not disable a working feature while availability is unmeasured', () => {
    // null = no verdict yet (probe in flight or failed). Neither is evidence
    // that try-on is broken; the backend stays authoritative and now fails fast
    // with the same honest sentence this hook renders.
    expect(resolveTryOnCtaKind(null, true)).toBe('render');
  });
});

describe('engineStateMessage — the UI localizes from the machine state', () => {
  it('says nothing for a healthy engine (no banner fatigue)', () => {
    expect(engineStateMessage('available')).toBeNull();
    expect(engineStateIsWarnable('available')).toBe(false);
  });

  it('reuses the shipped offline copy for an unavailable engine', () => {
    expect(engineStateMessage('temporarily_unavailable')).toEqual({
      key: 'tryon.engine_offline_fallback',
    });
  });

  it('passes interpolation params for a cold start', () => {
    expect(engineStateMessage('cold_start')).toEqual({
      key: 'tryon.engine_warming_detail',
      params: { seconds: 60 },
    });
  });

  it('distinguishes "not offered here" from "broken right now"', () => {
    expect(engineStateMessage('misconfigured')).toEqual({
      key: 'tryon.engine_misconfigured_detail',
    });
  });

  it('never renders an unknown state as fine', () => {
    // An unrecognised state has no sentence; the CTA decision does not depend
    // on it (renderAvailable does), so this stays null rather than inventing copy.
    expect(engineStateMessage('something_new')).toBeNull();
  });
});

describe('useTryOnAvailability — the consumer gate', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reports the engine as unavailable and routes the CTA to the fit check', async () => {
    await mockEngine('temporarily_unavailable', {
      verdict: 'unavailable',
      production_ready: false,
      error_code: 'VTON_ENGINE_UNAVAILABLE',
      retry_after_seconds: 0,
    });
    const { result } = renderHook(() => useTryOnAvailability(), { wrapper });
    await waitFor(() => expect(result.current.engineState).toBe('temporarily_unavailable'));

    expect(result.current.renderAvailable).toBe(false);
    expect(result.current.errorCode).toBe('VTON_ENGINE_UNAVAILABLE');
    expect(result.current.ctaKind(true)).toBe('fit_check');

    // THE assertion this file exists for: a render must not be reachable.
    const render = vi.fn();
    const fitCheck = vi.fn();
    result.current.gate({ render, fitCheck })();
    expect(render).not.toHaveBeenCalled();
    expect(fitCheck).toHaveBeenCalledTimes(1);
  });

  it('does nothing at all when there is no honest fallback', async () => {
    await mockEngine('temporarily_unavailable', { verdict: 'unavailable' });
    const { result } = renderHook(() => useTryOnAvailability(), { wrapper });
    await waitFor(() => expect(result.current.renderAvailable).toBe(false));

    expect(result.current.ctaKind(false)).toBe('blocked');
    const render = vi.fn();
    result.current.gate({ render })();
    expect(render).not.toHaveBeenCalled();
  });

  it('renders normally when the engine is ready', async () => {
    await mockEngine('available', { verdict: 'ready', production_ready: true });
    const { result } = renderHook(() => useTryOnAvailability(), { wrapper });
    await waitFor(() => expect(result.current.engineState).toBe('available'));

    expect(result.current.renderAvailable).toBe(true);
    expect(result.current.userMessage).toBeNull();
    const render = vi.fn();
    result.current.gate({ render, fitCheck: vi.fn() })();
    expect(render).toHaveBeenCalledTimes(1);
  });

  it('treats a cold engine as renderable but still warns', async () => {
    await mockEngine('cold_start', { verdict: 'cold_start' });
    const { result } = renderHook(() => useTryOnAvailability(), { wrapper });
    await waitFor(() => expect(result.current.engineState).toBe('cold_start'));

    expect(result.current.renderAvailable).toBe(true);
    expect(result.current.userMessage?.key).toBe('tryon.engine_warming_detail');
  });

  it('does not present the backend English prose as the user message', async () => {
    // The mocked response carries English `user_message`; the hook must expose
    // a descriptor instead, so an Arabic shopper reads Arabic. The prose stays
    // available as `upstreamDetail` for support.
    await mockEngine('temporarily_unavailable', {
      verdict: 'unavailable',
      detail: 'GPU worker is NOT reachable: every try-on job will fail.',
    });
    const { result } = renderHook(() => useTryOnAvailability(), { wrapper });
    await waitFor(() => expect(result.current.engineState).toBe('temporarily_unavailable'));

    expect(result.current.userMessage?.key).toBe('tryon.engine_offline_fallback');
    expect(result.current.upstreamDetail).toContain('NOT reachable');
    expect(result.current.userMessage).not.toBe(result.current.upstreamDetail);
  });

  it('stays unmeasured (not "unavailable") when the probe itself fails', async () => {
    const { tryOnService } = await import('../../services/apiServices');
    (tryOnService.getCapabilities as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('network down'),
    );
    const { result } = renderHook(() => useTryOnAvailability(), { wrapper });
    // Generous timeout: the hook performs one real retry before settling, and
    // react-query's retry delay is exponential. `isProbing` is deliberately true
    // for that whole window — a probe still in flight is not a verdict.
    await waitFor(() => expect(result.current.isProbing).toBe(false), {
      timeout: 8000,
    });

    expect(result.current.renderAvailable).toBeNull();
    expect(result.current.engineState).toBeNull();
    // A monitoring outage must not be reported to the shopper as a broken
    // feature they never got to try.
    expect(result.current.ctaKind(true)).toBe('render');
  });
});
