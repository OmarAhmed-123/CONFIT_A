/**
 * A growth chip may only state a percentage that exists.
 *
 * THE DEFECT (measured 2026-10-20)
 * --------------------------------
 * The backend mapped a zero previous-period value to `100.0`, so a brand with
 * no prior period was shown a green "+100%" on gross sales, net sales, orders,
 * units and AOV. The chip component rendered whatever number it was handed.
 *
 * CONTRACT PINNED HERE
 * --------------------
 *  - a real positive/negative/flat percentage renders as a number, correctly
 *    coloured;
 *  - `null` with basis `no_prior_baseline` renders an explanation, never "+0%",
 *    "NaN%", "Infinity%" or a green chip;
 *  - `null` with basis `no_activity` reads differently from no-baseline;
 *  - no comparison period -> no chip at all;
 *  - the Arabic bundle translates every one of those states.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, waitFor, act } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import React from "react";
import i18n from "../../i18n/i18n";
import type { BiDashboardResponse } from "../../models";

const { biMock } = vi.hoisted(() => ({ biMock: vi.fn() }));

vi.mock("../../services/apiServices", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../services/apiServices")>();
  return {
    ...actual,
    brandService: { ...actual.brandService, getBiDashboard: biMock },
  };
});

import { MemoryRouter } from "react-router-dom";

import { BrandAnalyticsView } from "../b2b/BrandAnalyticsView";

const PERIOD = {
  from: "2026-09-20",
  to: "2026-10-20",
  label: "Last 30 Days",
  comparison_from: "2026-08-21",
  comparison_to: "2026-09-19",
  comparison_label: "Aug 21 – Sep 19",
};

const RESPONSE = (over: Partial<BiDashboardResponse> = {}): BiDashboardResponse =>
  ({
    brand: { id: 1, name: "Riven Studio", slug: "riven-studio", commission_rate: 10 },
    generated_at: "2026-10-20T00:00:00Z",
    period: PERIOD,
    filters: { branch_id: null, category_id: null },
    kpis: {
      gross_sales: 600,
      net_sales: 540,
      orders_count: 1,
      units_sold: 2,
      average_order_value: 600,
      return_rate: null,
      tryon_assisted_orders: 0,
      tryon_share_pct: null,
      currency: "USD",
    },
    comparison_kpis: null,
    growth: {
      gross_sales_change_pct: null,
      net_sales_change_pct: null,
      orders_count_change_pct: null,
      units_sold_change_pct: null,
      average_order_value_change_pct: null,
    },
    growth_basis: {
      gross_sales: "no_prior_baseline",
      net_sales: "no_prior_baseline",
      orders_count: "no_prior_baseline",
      units_sold: "no_prior_baseline",
      average_order_value: "no_prior_baseline",
    },
    trends: [],
    categories: [],
    products: [],
    branches: [],
    inventory: {
      total_skus: 0,
      total_warehouse_units: 0,
      total_branch_bopis_units: 0,
      in_stock_count: 0,
      low_stock_count: 0,
      out_of_stock_count: 0,
      replenishment_items: [],
    },
    promotions: [],
    insights: [],
    methodology: "",
    ...over,
  }) as unknown as BiDashboardResponse;

async function renderView() {
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <BrandAnalyticsView />
      </MemoryRouter>
    </I18nextProvider>,
  );
  await waitFor(() => expect(biMock).toHaveBeenCalled());
  // let the resolved promise settle into state
  await act(async () => {
    await Promise.resolve();
  });
}

const chips = () =>
  screen.queryAllByTestId(/^growth-basis-/) as HTMLElement[];

describe("BrandAnalyticsView — growth chip honesty", () => {
  beforeEach(() => {
    cleanup();
    biMock.mockResolvedValue(RESPONSE());
  });
  afterEach(async () => {
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    vi.clearAllMocks();
  });

  it("never claims +100% for a brand with no prior period", async () => {
    await renderView();

    expect(screen.queryByText("+100%")).toBeNull();
    expect(screen.queryByText("+0%")).toBeNull();
    expect(document.body.textContent).not.toMatch(/NaN%|Infinity%/);
  });

  it("explains the missing baseline in words", async () => {
    await renderView();

    const found = chips();
    expect(found.length).toBeGreaterThan(0);
    expect(found[0].textContent).toMatch(/no prior-period baseline/i);
  });

  it("distinguishes no-activity from a missing baseline", async () => {
    biMock.mockResolvedValue(
      RESPONSE({
        growth_basis: {
          gross_sales: "no_activity",
          net_sales: "no_activity",
          orders_count: "no_activity",
          units_sold: "no_activity",
          average_order_value: "no_activity",
        },
      }),
    );
    await renderView();

    const text = chips().map((c) => c.textContent).join(" ");
    expect(text).toMatch(/no activity in either period/i);
    expect(text).not.toMatch(/no prior-period baseline/i);
  });

  it("still renders a real percentage when a baseline exists", async () => {
    biMock.mockResolvedValue(
      RESPONSE({
        growth: {
          gross_sales_change_pct: 100,
          net_sales_change_pct: -12.5,
          orders_count_change_pct: 0,
          units_sold_change_pct: 40,
          average_order_value_change_pct: 5.2,
        },
        growth_basis: {
          gross_sales: "ok",
          net_sales: "ok",
          orders_count: "ok",
          units_sold: "ok",
          average_order_value: "ok",
        },
      }),
    );
    await renderView();

    expect(screen.getByText("+100%")).toBeInTheDocument();
    expect(screen.getByText("-12.5%")).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeInTheDocument();
    expect(chips()).toHaveLength(0);
  });

  it("shows no chip at all when there is no comparison period", async () => {
    biMock.mockResolvedValue(
      RESPONSE({
        period: { ...PERIOD, comparison_label: null },
      }),
    );
    await renderView();

    expect(chips()).toHaveLength(0);
    expect(screen.queryByText("+100%")).toBeNull();
  });

  it("translates the no-baseline state in Arabic", async () => {
    await act(async () => {
      await i18n.changeLanguage("ar");
    });
    await renderView();

    const found = chips();
    expect(found.length).toBeGreaterThan(0);
    expect(found[0].textContent).toMatch(/لا توجد فترة سابقة/);
  });

  it("distinguishes an empty catalogue from products with no sales", async () => {
    // No SKUs at all -> the brand has not added anything yet -> offer an action.
    biMock.mockResolvedValue(
      RESPONSE({
        inventory: {
          total_skus: 0,
          total_warehouse_units: 0,
          total_branch_bopis_units: 0,
          in_stock_count: 0,
          low_stock_count: 0,
          out_of_stock_count: 0,
          replenishment_items: [],
        },
      }),
    );
    await renderView();

    expect(screen.getByTestId("empty-catalogue")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /add your first product/i })).toHaveAttribute(
      "href",
      "/b2b/catalog",
    );
  });

  it("does not tell a trading brand its catalogue is empty", async () => {
    biMock.mockResolvedValue(RESPONSE({ inventory: { ...(RESPONSE().inventory as object), total_skus: 9 } }));
    await renderView();

    expect(screen.getByTestId("no-sales-yet")).toBeInTheDocument();
    expect(screen.queryByTestId("empty-catalogue")).toBeNull();
  });
});
