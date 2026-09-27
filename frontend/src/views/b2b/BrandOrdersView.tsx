import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { brandService } from "../../services/apiServices";
import { BrandOrderLine, BrandOrderLinesResponse } from "../../models";
import { EmptyState } from "../../components/common/CommonComponents";
import { HonestProductImage } from "../../components/common/HonestProductImage";
import { formatMoney } from "../../i18n/format";

/**
 * What actually left this brand's shelf, and what it earned.
 *
 * WHY THIS SCREEN EXISTS
 * ----------------------
 * The brand portal could show aggregate product sales ("14 units of the Navy
 * Blazer") but nothing operational: not which customer is waiting, not which
 * size and colour left stock, not which store the pickup is against, and — the
 * gap that mattered most — not what a line actually EARNED. The order-level
 * discount was never apportioned to lines, so "net sales" was gross minus
 * returns and overstated revenue on every order placed with a promo code.
 *
 * Migration 0025 apportions the discount per line, and this screen states the
 * three figures separately rather than showing one blended number:
 *
 *     gross  -  discount  =  net
 *
 * They are printed side by side deliberately. A brand reconciling a payout
 * needs to see which of the three moved, and a single "revenue" column hides
 * exactly that.
 *
 * MONEY HANDLING
 * --------------
 * Amounts arrive as strings and are formatted from minor units. They are never
 * parsed into JS numbers for arithmetic — the backend computes in Decimal with
 * largest-remainder apportionment precisely so the figures reconcile, and
 * re-deriving them in binary floating point on the client would undo that.
 */

/** Minor units from an exact decimal STRING, without a float round-trip. */
function toMinorUnits(amount: string): number {
  const [whole, frac = ""] = (amount ?? "0").trim().replace("-", "").split(".");
  const cents = `${frac}00`.slice(0, 2);
  const sign = (amount ?? "").trim().startsWith("-") ? -1 : 1;
  return sign * (Number(whole || "0") * 100 + Number(cents));
}

const StatusPill: React.FC<{ value: string | null; tone?: "neutral" | "warn" }> = ({
  value,
  tone = "neutral",
}) => {
  if (!value) return <span className="text-slate-400">—</span>;
  const cls =
    tone === "warn"
      ? "bg-amber-50 text-amber-800 border-amber-200"
      : "bg-slate-100 text-slate-700 border-slate-200";
  return (
    <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${cls}`}>
      {value}
    </span>
  );
};

export const BrandOrdersView: React.FC = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? "en";

  const [data, setData] = useState<BrandOrderLinesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 25;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    brandService
      .getOrderLines({ limit, offset })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err: any) => {
        // State the failure. A silently empty table reads as "no sales",
        // which is a very different and much worse claim than "not loaded".
        if (!cancelled) setError(err?.message || t("brand_orders.load_failed"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [offset, t]);

  const money = (amount: string, currency: string) =>
    formatMoney(toMinorUnits(amount), currency || "USD", lang);

  const currency = useMemo(
    () => data?.lines[0]?.currency ?? "USD",
    [data],
  );

  return (
    <div className="space-y-6">
      <header className="border-b border-slate-200/80 pb-4">
        <h1 className="font-serif text-2xl font-bold text-[#1B1F3B]">
          {t("brand_orders.title")}
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
          {t("brand_orders.subtitle")}
        </p>
      </header>

      {data && (
        <section
          className="grid grid-cols-2 lg:grid-cols-5 gap-3"
          aria-label={t("brand_orders.totals_label")}
        >
          {[
            { k: "orders", v: String(data.totals.orders) },
            { k: "units", v: String(data.totals.units) },
            { k: "gross", v: money(data.totals.gross_amount, currency) },
            { k: "discount", v: money(data.totals.discount_amount, currency) },
            { k: "net", v: money(data.totals.net_amount, currency) },
          ].map(({ k, v }) => (
            <div
              key={k}
              className={`rounded-2xl border p-4 ${
                k === "net"
                  ? "bg-[#1B1F3B] border-[#1B1F3B] text-white"
                  : k === "discount"
                    ? "bg-[#FDF1F2] border-[#7A1F2B]/20"
                    : "bg-white border-slate-200/80"
              }`}
            >
              <span
                className={`block text-[10px] font-bold uppercase tracking-wider ${
                  k === "net" ? "text-[#C5A059]" : "text-slate-500"
                }`}
              >
                {t(`brand_orders.total_${k}`)}
              </span>
              <span className="block font-serif text-lg font-bold mt-1">{v}</span>
            </div>
          ))}
          {/* The totals describe every matching line, not the visible page. */}
          <p className="col-span-2 lg:col-span-5 text-[11px] text-slate-500">
            {t("brand_orders.totals_scope", { count: data.pagination.total_lines })}
          </p>
        </section>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {error}
        </div>
      )}

      {loading && !data && (
        <div className="space-y-2" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-2xl bg-slate-100 animate-pulse" />
          ))}
        </div>
      )}

      {data && data.lines.length === 0 && !error && (
        <EmptyState
          title={t("brand_orders.empty_title")}
          description={t("brand_orders.empty_body")}
        />
      )}

      {data && data.lines.length > 0 && (
        <div className="overflow-x-auto rounded-3xl border border-slate-200/80 bg-white shadow-2xs">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">{t("brand_orders.table_caption")}</caption>
            <thead className="bg-[#FAF9F6] text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-3">{t("brand_orders.col_item")}</th>
                <th scope="col" className="px-4 py-3">{t("brand_orders.col_order")}</th>
                <th scope="col" className="px-4 py-3">{t("brand_orders.col_customer")}</th>
                <th scope="col" className="px-4 py-3">{t("brand_orders.col_stock")}</th>
                <th scope="col" className="px-4 py-3 text-right">{t("brand_orders.col_gross")}</th>
                <th scope="col" className="px-4 py-3 text-right">{t("brand_orders.col_discount")}</th>
                <th scope="col" className="px-4 py-3 text-right">{t("brand_orders.col_net")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.lines.map((line: BrandOrderLine) => (
                <tr key={line.line_id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <div className="w-10 h-12 rounded-lg overflow-hidden bg-slate-100 shrink-0">
                        <HonestProductImage
                          src={line.thumbnail_url ?? ""}
                          alt={line.product_title}
                          loading="lazy"
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div className="min-w-0">
                        <span className="block font-semibold text-[#1B1F3B] truncate max-w-[180px]">
                          {line.product_title}
                        </span>
                        <span className="block text-[11px] text-slate-500">
                          {line.size} · {line.color}
                          {line.sku_code ? ` · ${line.sku_code}` : ""}
                        </span>
                        {line.is_returned && (
                          <StatusPill value={t("brand_orders.returned")} tone="warn" />
                        )}
                      </div>
                    </div>
                  </td>

                  <td className="px-4 py-3 align-top">
                    <span className="block font-mono text-[11px] text-[#1B1F3B]">
                      {line.order_number}
                    </span>
                    <span className="block text-[11px] text-slate-500">
                      {line.placed_at
                        ? new Date(line.placed_at).toLocaleDateString(lang)
                        : "—"}
                    </span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      <StatusPill value={line.order_status} />
                      <StatusPill
                        value={line.payment_status}
                        tone={line.payment_status === "paid" ? "neutral" : "warn"}
                      />
                    </div>
                  </td>

                  <td className="px-4 py-3 align-top">
                    <span className="block font-semibold text-[#1B1F3B]">
                      {line.customer_name}
                    </span>
                    <span className="block text-[11px] text-slate-500">
                      {line.customer_city ?? "—"} · {line.fulfillment_type}
                    </span>
                  </td>

                  <td className="px-4 py-3 align-top">
                    <span className="block font-semibold text-[#1B1F3B]">
                      {t("brand_orders.units_pulled", { count: line.quantity })}
                    </span>
                    <span className="block text-[11px] text-slate-500">
                      {line.store_name ?? t("brand_orders.no_store")}
                    </span>
                    <span className="block text-[11px] text-slate-500">
                      {/* null means the SKU row is gone, so remaining stock is
                          genuinely unknown. Printing 0 would claim sold out. */}
                      {line.sku_stock_remaining == null
                        ? t("brand_orders.stock_unknown")
                        : t("brand_orders.stock_remaining", {
                            count: line.sku_stock_remaining,
                          })}
                    </span>
                  </td>

                  <td className="px-4 py-3 text-right align-top tabular-nums">
                    {money(line.gross_amount, line.currency)}
                  </td>
                  <td className="px-4 py-3 text-right align-top tabular-nums text-[#7A1F2B]">
                    {toMinorUnits(line.discount_amount) > 0
                      ? `− ${money(line.discount_amount, line.currency)}`
                      : "—"}
                    {line.promo_code && (
                      <span className="block text-[10px] text-slate-400 font-mono">
                        {line.promo_code}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right align-top tabular-nums font-bold text-[#1B1F3B]">
                    {money(line.net_amount, line.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-slate-100 bg-[#FAF9F6]">
            <span className="text-[11px] text-slate-500">
              {t("brand_orders.showing", {
                from: data.pagination.offset + 1,
                to: data.pagination.offset + data.pagination.returned,
                total: data.pagination.total_lines,
              })}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0 || loading}
                className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-[11px] font-semibold disabled:opacity-40"
              >
                {t("common.previous")}
              </button>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={!data.pagination.has_more || loading}
                className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-[11px] font-semibold disabled:opacity-40"
              >
                {t("common.next")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BrandOrdersView;
