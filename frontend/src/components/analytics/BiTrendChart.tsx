import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { BiTrendPoint } from '../../models';

interface BiTrendChartProps {
  data: BiTrendPoint[];
  currency?: string;
  comparisonLabel?: string | null;
}

export const BiTrendChart: React.FC<BiTrendChartProps> = ({
  data,
  currency = 'USD',
  comparisonLabel,
}) => {
  const { t, i18n } = useTranslation();
  const isRtl = i18n.dir() === 'rtl';
  const [metric, setMetric] = useState<'revenue' | 'volume'>('revenue');
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);

  if (!data || data.length === 0) {
    return (
      <div className="p-8 text-center bg-slate-50 border border-slate-200 rounded-3xl text-xs text-slate-500">
        {t('bi.no_trend_data', 'No trend data recorded for the selected window.')}
      </div>
    );
  }

  // Chart Dimensions
  const width = 800;
  const height = 260;
  const padding = { top: 25, right: 30, bottom: 40, left: 60 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Max values
  const maxGross = Math.max(10, ...data.map((d) => d.gross_sales));
  const maxNet = Math.max(10, ...data.map((d) => d.net_sales));
  const maxRevenue = Math.max(maxGross, maxNet);
  const maxOrders = Math.max(1, ...data.map((d) => d.orders));
  const maxUnits = Math.max(1, ...data.map((d) => d.units));
  const maxVolume = Math.max(maxOrders, maxUnits);

  const currentMax = metric === 'revenue' ? maxRevenue : maxVolume;

  const getX = (index: number) => {
    if (data.length <= 1) return padding.left + chartWidth / 2;
    return padding.left + (index / (data.length - 1)) * chartWidth;
  };

  const getY = (val: number) => {
    return padding.top + chartHeight - (val / currentMax) * chartHeight;
  };

  // Generate SVG Path
  const generatePath = (valKey: keyof BiTrendPoint) => {
    if (data.length === 0) return '';
    return data
      .map((d, i) => {
        const x = getX(i);
        const y = getY(Number(d[valKey]));
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
      })
      .join(' ');
  };

  const grossPath = generatePath('gross_sales');
  const netPath = generatePath('net_sales');
  const ordersPath = generatePath('orders');
  const unitsPath = generatePath('units');

  // Generate Area Fill Path
  const generateArea = (valKey: keyof BiTrendPoint) => {
    if (data.length === 0) return '';
    const line = data
      .map((d, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(Number(d[valKey]))}`)
      .join(' ');
    const bottomY = padding.top + chartHeight;
    const lastX = getX(data.length - 1);
    const firstX = getX(0);
    return `${line} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;
  };

  const grossArea = generateArea('gross_sales');
  const ordersArea = generateArea('orders');

  return (
    <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-4">
      {/* Header with Mode Toggle & Table view */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
        <div>
          <h2 className="font-serif text-lg font-bold text-brand-charcoal">
            {metric === 'revenue'
              ? t('bi.revenue_trend', 'Revenue & Sales Trend Over Time')
              : t('bi.volume_trend', 'Order & Unit Volume Over Time')}
          </h2>
          <p className="text-[11px] text-slate-500">
            {metric === 'revenue'
              ? t('bi.revenue_trend_desc', 'Daily captured gross line value vs net sales (after discounts and opened returns)')
              : t('bi.volume_trend_desc', 'Daily completed order count and total physical units sold')}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Mode Switcher */}
          <div className="inline-flex rounded-xl bg-slate-100 p-0.5 border border-slate-200" role="group">
            <button data-motion="neutral" data-motion-tone="icon"
              type="button"
              onClick={() => setMetric('revenue')}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${
                metric === 'revenue'
                  ? 'bg-white text-brand-charcoal shadow-xs'
                  : 'text-slate-600 hover:text-brand-charcoal'
              }`}
            >
              {t('bi.revenue', 'Revenue ($)')}
            </button>
            <button data-motion="neutral" data-motion-tone="icon"
              type="button"
              onClick={() => setMetric('volume')}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${
                metric === 'volume'
                  ? 'bg-white text-brand-charcoal shadow-xs'
                  : 'text-slate-600 hover:text-brand-charcoal'
              }`}
            >
              {t('bi.orders_units', 'Orders & Units')}
            </button>
          </div>

          {/* Accessible Table Toggle */}
          <button data-motion="neutral" data-motion-tone="icon"
            type="button"
            onClick={() => setShowTable(!showTable)}
            className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            aria-expanded={showTable}
          >
            {showTable ? t('bi.view_chart', 'View Chart') : t('bi.view_table', 'View Table')}
          </button>
        </div>
      </div>

      {showTable ? (
        /* Accessible Table Alternative */
        <div className="overflow-x-auto max-h-72">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500">
                <th className="py-2">{t('bi.date', 'Date')}</th>
                <th className="py-2">{t('bi.orders', 'Orders')}</th>
                <th className="py-2">{t('bi.units', 'Units')}</th>
                <th className="py-2">{t('bi.gross_sales', 'Gross Sales')}</th>
                <th className="py-2">{t('bi.net_sales', 'Net Sales')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((d) => (
                <tr key={d.date} className="hover:bg-slate-50">
                  <td className="py-2 font-mono font-medium">{d.date}</td>
                  <td className="py-2 font-bold text-slate-700">{d.orders}</td>
                  <td className="py-2 text-slate-600">{d.units}</td>
                  <td className="py-2 font-mono text-brand-charcoal font-semibold">
                    {currency} {d.gross_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-2 font-mono text-emerald-700 font-semibold">
                    {currency} {d.net_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        /* Interactive SVG Chart */
        <div className="relative">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto max-h-[300px] overflow-visible"
            role="img"
            aria-label={t('bi.trend_chart_label', 'Sales and revenue trend chart')}
          >
            <defs>
              <linearGradient id="grossGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#EF826D" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#EF826D" stopOpacity="0.0" />
              </linearGradient>
              <linearGradient id="ordersGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#A99AD6" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#A99AD6" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Gridlines */}
            {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
              const y = padding.top + chartHeight * (1 - pct);
              const val = currentMax * pct;
              return (
                <g key={i}>
                  <line
                    x1={padding.left}
                    y1={y}
                    x2={width - padding.right}
                    y2={y}
                    stroke="#E2E8F0"
                    strokeDasharray={pct === 0 ? undefined : '3 3'}
                    strokeWidth={pct === 0 ? 1.5 : 0.75}
                  />
                  <text
                    x={padding.left - 8}
                    y={y + 3}
                    textAnchor="end"
                    className="text-[9px] fill-slate-400 font-mono"
                  >
                    {metric === 'revenue' ? `${Math.round(val)}` : Math.round(val)}
                  </text>
                </g>
              );
            })}

            {/* Areas */}
            {metric === 'revenue' ? (
              <path d={grossArea} fill="url(#grossGradient)" />
            ) : (
              <path d={ordersArea} fill="url(#ordersGradient)" />
            )}

            {/* Lines */}
            {metric === 'revenue' ? (
              <>
                <path
                  d={grossPath}
                  fill="none"
                  stroke="#EF826D"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d={netPath}
                  fill="none"
                  stroke="#89B799"
                  strokeWidth="2"
                  strokeDasharray="4 2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </>
            ) : (
              <>
                <path
                  d={ordersPath}
                  fill="none"
                  stroke="#A99AD6"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d={unitsPath}
                  fill="none"
                  stroke="#252729"
                  strokeWidth="2"
                  strokeDasharray="4 2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </>
            )}

            {/* X-Axis Ticks (Dates) */}
            {data.map((d, i) => {
              // Show label for first, middle, last, or if small array
              const showLabel =
                data.length <= 7 ||
                i === 0 ||
                i === Math.floor(data.length / 2) ||
                i === data.length - 1;
              if (!showLabel) return null;
              const x = getX(i);
              return (
                <text
                  key={d.date}
                  x={x}
                  y={height - 12}
                  textAnchor="middle"
                  className="text-[9px] fill-slate-500 font-mono"
                >
                  {d.date.slice(5)}
                </text>
              );
            })}

            {/* Interactive Points & Hit Areas */}
            {data.map((d, i) => {
              const x = getX(i);
              const yGross = getY(metric === 'revenue' ? d.gross_sales : d.orders);
              const isHovered = hoveredIndex === i;
              return (
                <g key={d.date} onMouseEnter={() => setHoveredIndex(i)} onMouseLeave={() => setHoveredIndex(null)}>
                  {/* Invisible hit column */}
                  <rect
                    x={x - chartWidth / (data.length * 2)}
                    y={padding.top}
                    width={chartWidth / data.length}
                    height={chartHeight}
                    fill="transparent"
                    className="cursor-pointer"
                  />
                  {isHovered && (
                    <line
                      x1={x}
                      y1={padding.top}
                      x2={x}
                      y2={padding.top + chartHeight}
                      stroke="#94A3B8"
                      strokeWidth="1"
                      strokeDasharray="2 2"
                    />
                  )}
                  <circle
                    cx={x}
                    cy={yGross}
                    r={isHovered ? 5 : 3}
                    fill={metric === 'revenue' ? '#EF826D' : '#A99AD6'}
                    stroke="#FFFFFF"
                    strokeWidth="1.5"
                    className="transition-all"
                  />
                </g>
              );
            })}
          </svg>

          {/* Active Point Floating Tooltip */}
          {hoveredIndex !== null && data[hoveredIndex] && (
            <div
              className="absolute top-2 pointer-events-none bg-brand-charcoal text-white text-[11px] rounded-xl p-3 shadow-lg z-20 space-y-1 transition-all"
              style={{
                left: `${Math.min(
                  80,
                  Math.max(10, ((hoveredIndex + 0.5) / data.length) * 100)
                )}%`,
                transform: 'translateX(-50%)',
              }}
            >
              <div className="font-bold text-slate-200 border-b border-slate-700 pb-1 font-mono">
                {data[hoveredIndex].date}
              </div>
              {metric === 'revenue' ? (
                <>
                  <div className="flex justify-between gap-4">
                    <span className="text-brand-coral font-medium">{t('bi.gross_sales', 'Gross Sales')}:</span>
                    <span className="font-mono font-bold">
                      {currency} {data[hoveredIndex].gross_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-brand-mint font-medium">{t('bi.net_sales', 'Net Sales')}:</span>
                    <span className="font-mono font-bold">
                      {currency} {data[hoveredIndex].net_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className="flex justify-between gap-4 text-brand-muted text-[10px]">
                    <span>{t('bi.orders', 'Orders')}:</span>
                    <span className="font-mono">{data[hoveredIndex].orders}</span>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex justify-between gap-4">
                    <span className="text-brand-lilac font-medium">{t('bi.orders', 'Orders')}:</span>
                    <span className="font-mono font-bold">{data[hoveredIndex].orders}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-slate-300 font-medium">{t('bi.units', 'Units')}:</span>
                    <span className="font-mono font-bold">{data[hoveredIndex].units}</span>
                  </div>
                  <div className="flex justify-between gap-4 text-brand-muted text-[10px]">
                    <span>{t('bi.gross_sales', 'Gross')}:</span>
                    <span className="font-mono">
                      {currency} {data[hoveredIndex].gross_sales.toFixed(2)}
                    </span>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Legend */}
          <div className="flex flex-wrap items-center justify-center gap-6 pt-3 text-xs border-t border-slate-100">
            {metric === 'revenue' ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="w-3.5 h-1 bg-brand-coral rounded-full inline-block" />
                  <span className="text-slate-700 font-semibold">{t('bi.gross_sales', 'Gross Sales')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3.5 h-1 border-t-2 border-brand-mint border-dashed inline-block" />
                  <span className="text-slate-700 font-semibold">{t('bi.net_sales', 'Net Sales (after discounts & returns)')}</span>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className="w-3.5 h-1 bg-brand-lilac rounded-full inline-block" />
                  <span className="text-slate-700 font-semibold">{t('bi.completed_orders', 'Completed Orders')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3.5 h-1 border-t-2 border-brand-charcoal border-dashed inline-block" />
                  <span className="text-slate-700 font-semibold">{t('bi.physical_units', 'Physical Units Sold')}</span>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
