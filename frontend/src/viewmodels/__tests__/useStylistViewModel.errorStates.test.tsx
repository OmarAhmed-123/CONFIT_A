/**
 * D-4 §14 — the two runtime states the delivered browser audit could not reach.
 *
 * The Arabic runtime audit (CONFIT_evidence/42-…) proves the HTTP-failure state,
 * the Retry affordance and the localized chrome in a real browser. Two states were
 * still only asserted on paper:
 *
 *   • VALIDATION FAILURE — the backend refuses the request (422). The shopper must
 *     get the localized validation sentence, no transport string, no status code,
 *     and NO Retry (retrying an invalid request is not a user remedy).
 *   • EMPTY RESPONSE — the call succeeds but carries no usable answer. Before this
 *     test the drawer appended it and rendered an empty bubble: indistinguishable
 *     from a silent failure, and not an answer. It is now a retryable, localized
 *     state and NOTHING is appended to the transcript.
 *
 * What is asserted here is the view-model contract (which key, which retryability,
 * what ends up in the transcript). Rendering of the banner itself is covered by the
 * browser audit; this file does not claim to be a browser run.
 *
 * MUTATION CONTROLS (run manually, recorded in CONFIT_evidence/51-*):
 *   M1 remove VALIDATION_ERROR from NON_RETRYABLE_CODES -> the validation test fails
 *   M2 delete the empty-answer guard                    -> the empty-response test fails
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  addItem: vi.fn().mockResolvedValue({}),
  openCart: vi.fn(),
  showToast: vi.fn(),
  chat: vi.fn(),
}));

vi.mock('../../stores/cartStore', () => ({
  useCartStore: () => ({ addItem: mocks.addItem, openCart: mocks.openCart }),
}));

vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({ showToast: mocks.showToast }),
}));

vi.mock('../../services/apiServices', () => ({
  stylistService: { chat: mocks.chat },
}));

import { useStylistViewModel } from '../useStylistViewModel';

/**
 * `TranslatableMessage` is a union (plain string | descriptor), so the key has to be
 * read through a narrowing helper. tsc caught the first version reading `error.key`
 * directly — which is the point: the type does not promise a key, and only the
 * descriptor branch carries one. Every error this view-model sets is a descriptor
 * (null, `apiErrorDescriptor(...)`, or a keyed literal), asserted below.
 */
const keyOf = (message: unknown): string | undefined =>
  typeof message === 'object' && message !== null
    ? (message as { key?: string }).key
    : undefined;

const answer = (content: string, engine = 'Grounded Styling Engine') => ({
  id: 1,
  session_id: 1,
  sender: 'assistant',
  content,
  recommendations: [],
  engine,
  created_at: new Date().toISOString(),
});

describe('D-4 stylist error states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('a refused request shows the localized validation sentence and offers no Retry', async () => {
    // Shape produced by the api client for a 422 from the backend.
    mocks.chat.mockRejectedValueOnce({
      code: 'VALIDATION_ERROR',
      message: 'Request failed with status 422',
      status: 422,
    });

    const { result } = renderHook(() => useStylistViewModel());
    await act(async () => {
      await result.current.sendPrompt('a prompt that the backend refuses');
    });

    expect(result.current.error).toBeTruthy();
    expect(keyOf(result.current.error)).toBe('errors.validation');
    expect(result.current.errorRetryable).toBe(false);
    // The transport string must never be what the banner resolves to.
    expect(JSON.stringify(result.current.error)).not.toContain('422');
    expect(JSON.stringify(result.current.error)).not.toContain('Request failed');
    // The user's own prompt stays in the transcript; no assistant answer was invented.
    const senders = result.current.messages.map((m: any) => m.sender);
    expect(senders).toEqual(['user']);
  });

  it('an answer with no usable text is reported as such, is retryable, and is not appended', async () => {
    mocks.chat.mockResolvedValueOnce(answer('   '));

    const { result } = renderHook(() => useStylistViewModel());
    await act(async () => {
      await result.current.sendPrompt('what should I wear tonight?');
    });

    expect(keyOf(result.current.error)).toBe('errors.empty_answer');
    expect(result.current.errorRetryable).toBe(true);
    const senders = result.current.messages.map((m: any) => m.sender);
    expect(senders).toEqual(['user']);
    // An empty bubble would have rendered as `''` here.
    expect(result.current.messages.some((m: any) => !String(m.content ?? '').trim())).toBe(false);
  });

  it('a real answer still lands in the transcript with its engine attribution', async () => {
    mocks.chat.mockResolvedValueOnce(answer('A navy blazer with cream trousers.'));

    const { result } = renderHook(() => useStylistViewModel());
    await act(async () => {
      await result.current.sendPrompt('what should I wear tonight?');
    });

    expect(result.current.error).toBeNull();
    const senders = result.current.messages.map((m: any) => m.sender);
    expect(senders).toEqual(['user', 'assistant']);
    expect(result.current.messages[1].engine).toBe('Grounded Styling Engine');
  });

  it('an unknown error code falls back to a generic sentence, never to a raw message', async () => {
    mocks.chat.mockRejectedValueOnce({ code: 'SOMETHING_UNMAPPED', message: 'boom: internal detail' });

    const { result } = renderHook(() => useStylistViewModel());
    await act(async () => {
      await result.current.sendPrompt('hello');
    });

    expect(keyOf(result.current.error)).toBe('errors.request_failed');
    expect(JSON.stringify(result.current.error)).not.toContain('internal detail');
  });
});
