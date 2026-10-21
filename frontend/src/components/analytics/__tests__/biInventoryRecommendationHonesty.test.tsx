/**
 * A replenishment number must say what it is.
 *
 * THE DEFECT (measured 2026-10-20)
 * --------------------------------
 * `BiInventoryHealthCard` rendered `+{item.recommended_reorder} units` in bold
 * coral, which reads as a calculated recommendation. The value is a fixed rule:
 * `20` when the SKU is out of stock, otherwise `15 - stock_level`. No sales
 * velocity, lead time or safety stock is involved. It also rendered
 * unconditionally, so a null would have printed "+null units".
 *
 * The card additionally hard-coded the English status words in a bilingual
 * product, and its out-of-stock label used `t(key, 'Out of Stock SKUs (0)')` —
 * a default value containing a literal count that would print "(0)" whatever
 * the real number was.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, act } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import React from "react";
import i18n from "../../../i18n/i18n";
import { BiInventoryHealthCard } from "../BiInventoryHealthCard";

const INVENTORY = (over: Record<string, unknown> = {}) =>
  ({
    total_skus: 3,
    total_warehouse_units: 12,
    total_branch_bopis_units: 0,
    in_stock_count: 1,
    low_stock_count: 1,
    out_of_stock_count: 1,
    replenishment_items: [
      {
        sku_id: 11,
        sku_code: "MD-BLZ-NVY-S",
        product_id: 1,
        product_title: "Midnight Wool Blazer",
        size: "S",
        color: "Navy",
        stock_level: 0,
        status: "out_of_stock",
        recommended_reorder: 20,
        reorder_basis: "rule_of_thumb",
      },
    ],
    ...over,
  }) as never;

function renderCard(inventory: unknown = INVENTORY()) {
  return render(
    <I18nextProvider i18n={i18n}>
      <BiInventoryHealthCard inventory={inventory as never} />
    </I18nextProvider>,
  );
}

describe("BiInventoryHealthCard — recommendation honesty", () => {
  afterEach(async () => {
    cleanup();
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    vi.clearAllMocks();
  });

  it("labels the quantity as an estimate, not a calculation", () => {
    renderCard();

    expect(screen.getByText(/\+20 units/)).toBeInTheDocument();
    expect(screen.getByText(/rule-of-thumb estimate/i)).toBeInTheDocument();
  });

  it("never renders '+null units' when the value is absent", () => {
    renderCard(
      INVENTORY({
        replenishment_items: [
          {
            sku_id: 12,
            sku_code: "COS-SHR-WHT-S",
            product_id: 2,
            product_title: "Poplin Shirt",
            size: "S",
            color: "White",
            stock_level: 2,
            status: "low_stock",
            recommended_reorder: null,
            reorder_basis: "unavailable",
          },
        ],
      }),
    );

    expect(document.body.textContent).not.toMatch(/\+null|null units/);
    expect(screen.getByText(/not available/i)).toBeInTheDocument();
  });

  it("translates the status words instead of hard-coding English", async () => {
    await act(async () => {
      await i18n.changeLanguage("ar");
    });
    renderCard();

    expect(screen.getByText("نفد المخزون")).toBeInTheDocument();
    expect(screen.queryByText("Out of Stock")).toBeNull();
  });

  it("shows the real out-of-stock count, not a literal from the label", () => {
    renderCard(INVENTORY({ out_of_stock_count: 7 }));

    expect(document.body.textContent).not.toMatch(/SKUs \(0\)/);
    expect(screen.getByText("7")).toBeInTheDocument();
  });
});
