import React from 'react';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const AdminAnalyticsView: React.FC = () => {
  const { adminAnalytics, isLoading } = useBrandViewModel();

  if (isLoading || !adminAnalytics) {
    return <LoadingSpinner text="Aggregating platform-wide telemetry & style heatmaps..." />;
  }

  return (
    <div className="space-y-8 pb-20">
      <div className="border-b border-slate-200 pb-4">
        <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
          Platform Administration & Revenue Attribution
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Macro metrics across connected brand catalogs, try-on conversion lift, and regional style heatmaps.
        </p>
      </div>

      {/* Platform Macro KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase">Platform GMV</span>
          <div className="text-2xl font-serif font-black text-[#1B1F3B]">
            ${adminAnalytics.total_gmv.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-emerald-600 font-semibold">+24.2% MoM Growth</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase">Total Orders</span>
          <div className="text-2xl font-serif font-black text-[#1B1F3B]">
            {adminAnalytics.total_orders.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-500 font-medium">Try-On Assisted: 68.4%</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase">Stylist Conversion Ratio</span>
          <div className="text-2xl font-serif font-black text-[#B8935A]">
            {adminAnalytics.stylist_conversion_ratio}%
          </div>
          <div className="text-[11px] text-slate-500 font-medium">Saved Outfit to Purchase</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase">Platform Return Rate</span>
          <div className="text-2xl font-serif font-black text-emerald-600">
            {adminAnalytics.platform_avg_return_rate}%
          </div>
          <div className="text-[11px] text-slate-500">Non-Try-On: {adminAnalytics.return_rate_non_tryon_users}%</div>
        </div>
      </div>

      {/* Revenue Attribution & Style Preference Heatmap (PDF G6.2) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Revenue Attribution by AI Feature */}
        <div className="lg:col-span-6 bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="pb-3 border-b border-slate-100">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
              Revenue Attribution by AI Feature
            </h3>
            <p className="text-xs text-slate-500">Direct sales generated per experience module</p>
          </div>

          <div className="space-y-3 text-xs">
            {Object.entries(adminAnalytics.revenue_attribution).map(([feat, rev]) => (
              <div key={feat} className="flex justify-between items-center p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="font-bold text-slate-800 capitalize">{feat.replace('_', ' ')}</span>
                <span className="font-mono text-sm font-bold text-[#1B1F3B]">
                  ${Number(rev).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Style Preference Heatmaps */}
        <div className="lg:col-span-6 bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="pb-3 border-b border-slate-100">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
              Regional Style Signal Heatmap ({adminAnalytics.style_preference_heatmap.region})
            </h3>
            <p className="text-xs text-slate-500">Anonymized customer aesthetic signals</p>
          </div>

          <div className="space-y-3">
            {adminAnalytics.style_preference_heatmap.top_aesthetics.map((aes) => (
              <div key={aes.name} className="space-y-1 text-xs">
                <div className="flex justify-between font-bold text-slate-700">
                  <span>{aes.name}</span>
                  <span className="text-[#B8935A]">{aes.share}% of shoppers</span>
                </div>
                <div className="w-full h-3 rounded-full bg-slate-100 overflow-hidden">
                  <div className="h-full bg-[#1B1F3B] rounded-full" style={{ width: `${aes.share}%` }}></div>
                </div>
              </div>
            ))}

            <div className="pt-3 border-t border-slate-100">
              <span className="text-xs font-bold text-slate-700 block mb-1.5">Trending Color Families:</span>
              <div className="flex flex-wrap gap-2">
                {adminAnalytics.style_preference_heatmap.trending_colors.map((c) => (
                  <span key={c} className="px-3 py-1 rounded-xl bg-slate-100 text-xs font-semibold text-slate-800">
                    {c}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
