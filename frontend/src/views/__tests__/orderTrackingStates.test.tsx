/**
 * Order tracking state behaviour (runtime).
 *
 * Mocked API states, labelled _mocked in the capture scripts:
 *  - 500 on anonymous /orders/:n  -> load-failed message with Retry, no verify form
 *  - 404 on signed-in /orders/:n  -> not-found message, no verify form
 *  - 404 on anonymous /orders/:n  -> verify form (anti-enumeration kept)
 *  - signed-in /orders            -> order list linking to /orders/:n
 *  - anonymous /orders            -> neutral prompt, no API call
 *  - list failure / empty list    -> dedicated copy, list retry works
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

const { svc, authState } = vi.hoisted(() => ({
  svc: {
    getOrderDetail: vi.fn(),
    getOrderTracking: vi.fn(),
    getOrders: vi.fn(),
  },
  authState: { isAuthenticated: true },
}));

vi.mock('../../services/apiServices', () => ({ commerceService: svc }));
vi.mock('../../stores/authStore', () => ({
  useAuthStore: () => ({ isAuthenticated: authState.isAuthenticated }),
}));
vi.mock('../../components/showcase/DesignShowcases', () => ({
  CardStackShowcase: ({ eyebrow, description }: { eyebrow: string; description: string }) => (
    <div data-testid="story">
      <span>{eyebrow}</span>
      <span>{description}</span>
    </div>
  ),
}));

import { OrderTrackingView } from '../consumer/OrderTrackingView';
import i18n, { setAppLanguage } from '../../i18n/i18n';

const ORDER = {
  id: 501,
  order_number: 'CF-240918-0042',
  user_id: 1,
  guest_email: null,
  status: 'shipped',
  total_amount: 420,
  created_at: '2026-10-02T09:30:00Z',
  payment_status: 'paid',
  payment_mode: 'demo',
  payment_method: 'card',
  fulfillment_type: 'shipping',
  bopis_store_name: null,
  bopis_pickup_code: null,
  items: [
    { id: 1, product_title: 'Midnight Wool Blazer', brand_name: 'Reiss', size: 'M', color: 'Navy', subtotal: 240, is_returned: false },
    { id: 2, product_title: 'Ivory Silk Blouse', brand_name: 'Massimo', size: 'S', color: 'Ivory', subtotal: 180, is_returned: true },
  ],
};
const TIMELINE = {
  current_status: 'shipped',
  tracking_number: 'TRK-88213',
  carrier: 'DHL',
  bopis_store_info: null,
  timeline: [
    { title: 'Order placed', description: 'We received your order.', status_key: 'placed', timestamp: '2026-10-02T09:30:00Z', is_completed: true, is_current: false },
    { title: 'Shipped', description: 'On its way with DHL.', status_key: 'shipped', timestamp: '2026-10-04T08:45:00Z', is_completed: false, is_current: true },
  ],
};

const apiError = (status: number, code: string, message: string) =>
  Object.assign(new Error(message), { status, code });

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/orders" element={<OrderTrackingView />} />
        <Route path="/orders/:orderNumber" element={<OrderTrackingView />} />
      </Routes>
    </MemoryRouter>,
  );
}

const verifyPromptTitle = () => i18n.t('order.verify_prompt_title');

beforeEach(async () => {
  vi.clearAllMocks();
  await setAppLanguage('en');
  authState.isAuthenticated = true;
  svc.getOrderDetail.mockResolvedValue(ORDER);
  svc.getOrderTracking.mockResolvedValue(TIMELINE);
  svc.getOrders.mockResolvedValue([ORDER]);
});

describe('anonymous /orders/:orderNumber', () => {
  beforeEach(() => {
    authState.isAuthenticated = false;
  });

  it('500 shows the load-failed message with Retry and never the verify form', async () => {
    svc.getOrderDetail.mockRejectedValue(apiError(500, 'INTERNAL_ERROR', 'boom'));
    svc.getOrderTracking.mockRejectedValue(apiError(500, 'INTERNAL_ERROR', 'boom'));
    renderAt('/orders/CF-240918-0042');

    expect(await screen.findByText(i18n.t('order.load_failed'))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: i18n.t('order.retry') })).toBeInTheDocument();
    expect(screen.queryByText(verifyPromptTitle())).toBeNull();
  });

  it('Retry after a 500 reloads the order', async () => {
    svc.getOrderDetail
      .mockRejectedValueOnce(apiError(500, 'INTERNAL_ERROR', 'boom'))
      .mockResolvedValueOnce(ORDER);
    svc.getOrderTracking
      .mockRejectedValueOnce(apiError(500, 'INTERNAL_ERROR', 'boom'))
      .mockResolvedValueOnce(TIMELINE);
    renderAt('/orders/CF-240918-0042');

    fireEvent.click(await screen.findByRole('button', { name: i18n.t('order.retry') }));
    expect(await screen.findByText('Midnight Wool Blazer')).toBeInTheDocument();
    expect(svc.getOrderDetail).toHaveBeenCalledTimes(2);
  });

  it('a 403 on a signed-in order shows access-denied copy, not raw backend text', async () => {
    authState.isAuthenticated = true;
    svc.getOrderDetail.mockRejectedValue(apiError(403, 'FORBIDDEN', 'Access denied: cross-customer'));
    svc.getOrderTracking.mockRejectedValue(apiError(403, 'FORBIDDEN', 'Access denied: cross-customer'));
    renderAt('/orders/CF-240918-0042');

    expect(await screen.findByText(i18n.t('order.access_denied'))).toBeInTheDocument();
    expect(screen.queryByText(/cross-customer/)).toBeNull();
  });

  it('404 keeps the neutral verify prompt (anti-enumeration)', async () => {
    svc.getOrderDetail.mockRejectedValue(apiError(404, 'NOT_FOUND', 'Not found'));
    svc.getOrderTracking.mockRejectedValue(apiError(404, 'NOT_FOUND', 'Not found'));
    renderAt('/orders/CF-240918-0042');

    expect(await screen.findByText(verifyPromptTitle())).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: i18n.t('order.retry') })).toBeNull();
  });
});

describe('signed-in /orders/:orderNumber', () => {
  it('404 shows order.not_found and no guest verify prompt', async () => {
    svc.getOrderDetail.mockRejectedValue(apiError(404, 'NOT_FOUND', 'Not found'));
    svc.getOrderTracking.mockRejectedValue(apiError(404, 'NOT_FOUND', 'Not found'));
    renderAt('/orders/CF-240918-0042');

    expect(await screen.findByRole('heading', { name: i18n.t('order.not_found') })).toBeInTheDocument();
    expect(screen.getByText(i18n.t('order.not_found_desc'))).toBeInTheDocument();
    expect(screen.queryByText(verifyPromptTitle())).toBeNull();
  });

  it('500 shows load-failed with Retry and no verify prompt', async () => {
    svc.getOrderDetail.mockRejectedValue(apiError(500, 'INTERNAL_ERROR', 'boom'));
    svc.getOrderTracking.mockRejectedValue(apiError(500, 'INTERNAL_ERROR', 'boom'));
    renderAt('/orders/CF-240918-0042');

    expect(await screen.findByText(i18n.t('order.load_failed'))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: i18n.t('order.retry') })).toBeInTheDocument();
    expect(screen.queryByText(verifyPromptTitle())).toBeNull();
  });

  it('a 5xx whose message says "not found" is still a load failure, not a missing order', async () => {
    svc.getOrderDetail.mockRejectedValue(apiError(500, 'INTERNAL_ERROR', 'Order not found'));
    svc.getOrderTracking.mockRejectedValue(apiError(500, 'INTERNAL_ERROR', 'Order not found'));
    renderAt('/orders/CF-240918-0042');

    expect(await screen.findByText(i18n.t('order.load_failed'))).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: i18n.t('order.load_failed_title') })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: i18n.t('order.not_found') })).toBeNull();
    expect(screen.getByRole('button', { name: i18n.t('order.retry') })).toBeInTheDocument();
  });

  it('renders the order detail for the mocked 200 state', async () => {
    renderAt('/orders/CF-240918-0042');
    expect(await screen.findByText('Midnight Wool Blazer')).toBeInTheDocument();
    expect(screen.getByText(i18n.t('order.fulfillment_progress'))).toBeInTheDocument();
  });

  it('shows the story copy from locale keys, not hard-coded English', async () => {
    renderAt('/orders/CF-240918-0042');
    await screen.findByText('Midnight Wool Blazer');
    expect(screen.getByText(i18n.t('order.story_eyebrow'))).toBeInTheDocument();
    expect(screen.getByText(i18n.t('order.story_description'))).toBeInTheDocument();
  });
});

describe('signed-in /orders (no number)', () => {
  it('lists the customer orders, each linking to its detail page', async () => {
    renderAt('/orders');
    const link = await screen.findByRole('link', { name: new RegExp(ORDER.order_number) });
    expect(link).toHaveAttribute('href', '/orders/CF-240918-0042');
    expect(svc.getOrders).toHaveBeenCalledTimes(1);
  });

  it('shows the empty-list copy when the customer has no orders', async () => {
    svc.getOrders.mockResolvedValue([]);
    renderAt('/orders');
    expect(await screen.findByText(i18n.t('order.list_empty_title'))).toBeInTheDocument();
  });

  it('a failed list shows the list error with a working retry', async () => {
    svc.getOrders.mockRejectedValueOnce(apiError(500, 'INTERNAL_ERROR', 'boom'));
    renderAt('/orders');

    expect(await screen.findByText(i18n.t('order.list_error_title'))).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: i18n.t('order.retry') }));
    expect(await screen.findByRole('link', { name: new RegExp(ORDER.order_number) })).toBeInTheDocument();
    expect(svc.getOrders).toHaveBeenCalledTimes(2);
  });
});

describe('anonymous /orders (no number)', () => {
  it('shows the neutral prompt and does not call the list API', async () => {
    authState.isAuthenticated = false;
    renderAt('/orders');
    expect(await screen.findByText(i18n.t('order.no_number'))).toBeInTheDocument();
    expect(svc.getOrders).not.toHaveBeenCalled();
  });
});

describe('Arabic locale', () => {
  it('load-failed and retry copy render in Arabic, not English', async () => {
    await setAppLanguage('ar');
    authState.isAuthenticated = false;
    svc.getOrderDetail.mockRejectedValue(apiError(500, 'INTERNAL_ERROR', 'boom'));
    svc.getOrderTracking.mockRejectedValue(apiError(500, 'INTERNAL_ERROR', 'boom'));
    renderAt('/orders/CF-240918-0042');

    const msg = await screen.findByText(i18n.t('order.load_failed'));
    expect(msg.textContent).toMatch(/[\u0600-\u06FF]/);
    expect(msg.textContent).not.toMatch(/We could not load/);
    expect(screen.getByRole('button', { name: i18n.t('order.retry') }).textContent).toMatch(/[\u0600-\u06FF]/);
  });
});
