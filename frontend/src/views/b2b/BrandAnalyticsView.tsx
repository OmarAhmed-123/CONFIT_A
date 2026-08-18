import React from 'react';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const BrandAnalyticsView: React.FC = () => {
  const { analytics, isLoading } = useBrandViewModel();

  if (isLoading || !analytics) {
    return <LoadingSpinner text="Computing funnel telemetry and conversion rates..." />;
  }

  const funnelSteps = [
    { label: '1. Catalog Product Views', count: analytics.total_views, pct: '100%' },
    { label: '2. Virtual Try-On Rendered', count: analytics.total_tryons, pct: '29.8%' },
    { label: '3. Added to Shopping Bag', count: analytics.total_add_to_carts, pct: '10.8%' },
    { label: '4. Confirmed Purchases', count: analytics.total_purchases, pct: '4.52%' },
  ];

  return (
    <div className="space-y-8 pb-20">
      <div className="border-b border-slate-200 pb-4">
        <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
          Conversion Funnel & Return Telemetry
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Trace how CONFIT's AI styling and Try-On models accelerate add-to-bag intent and drastically slash return costs.
        </p>
      </div>

      {/* Funnel Visualization */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-sm space-y-6">
        <h3 className="font-serif text-xl font-bold text-[#1B1F3B]">
          E-Commerce Conversion Funnel (Try-On Assisted)
        </h3>

        <div className="space-y-4">
          {funnelSteps.map((step, idx) => (
            <div key={step.label} className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold text-slate-700">
                <span>{step.label}</span>
                <span className="font-mono text-sm text-[#1B1F3B]">{step.count.toLocaleString()} ({step.pct})</span>
              </div>
              <div className="w-full h-4 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500 bg-gradient-to-r from-[#1B1F3B] to-[#B8935A]"
                  style={{ width: `${100 - (idx * 28)}%` }}
                ></div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Return Rate Benchmark Card */}
      <div className="bg-[#FAF9F6] rounded-3xl border border-slate-200 p-6 sm:p-8 space-y-4">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
          Return Reduction Financial Impact
        </h3>
        <p className="text-xs text-slate-600 leading-relaxed max-w-3xl">
          By eliminating size ambiguity through 3D scaling and anthropometric fit algorithms, your customer return rate was reduced by <strong>{analytics.return_reduction_percentage}%</strong> compared to traditional online apparel averages.
        </p>
      </div>
    </div>
  );
};
