import React from 'react';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import {
  BrandDashboardIcon,
  SparkleIcon,
  TryOnIcon,
  BagIcon,
  BopisIcon,
} from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const BrandDashboardView: React.FC = () => {
  const { profile, analytics, products, isLoading } = useBrandViewModel();

  if (isLoading || !analytics) {
    return <LoadingSpinner text="Connecting to B2B Merchant Telemetry..." />;
  }

  return (
    <div className="space-y-8 pb-20">
      {/* Brand Hero Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 text-white flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#B8935A]/20 text-[#B8935A] font-bold uppercase tracking-wider">
              Verified Brand Partner
            </span>
          </div>
          <h1 className="font-serif text-2xl sm:text-3xl font-bold text-white">
            {profile?.brand_name || 'Massimo Dutti'} Command Center
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Catalog ID: #MD-9921 · Commission Tier: 15% · BOPIS Enabled in 3 Boutiques
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="bg-slate-800/80 px-4 py-2 rounded-2xl border border-slate-700 text-center">
            <span className="text-[10px] text-slate-400 block uppercase">Return Reduction</span>
            <span className="text-lg font-mono font-bold text-emerald-400">
              +{analytics.return_reduction_percentage}%
            </span>
          </div>
        </div>
      </div>

      {/* Metric Cards Grid (PDF G6.1) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Total Catalog Views
          </span>
          <div className="text-2xl font-serif font-black text-[#1B1F3B]">
            {analytics.total_views.toLocaleString()}
          </div>
          <div className="text-[11px] text-emerald-600 font-semibold">+18.4% this month</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Virtual Try-Ons Run
          </span>
          <div className="text-2xl font-serif font-black text-[#B8935A]">
            {analytics.total_tryons.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-500 font-medium">32.8% Try-On Adoption Rate</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Try-On Conversion Rate
          </span>
          <div className="text-2xl font-serif font-black text-emerald-600">
            {analytics.funnel_conversion_rate}%
          </div>
          <div className="text-[11px] text-emerald-700 font-medium">vs 1.4% standard e-comm benchmark</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Post-VTON Return Rate
          </span>
          <div className="text-2xl font-serif font-black text-emerald-600">
            {analytics.return_rate_after_vton}%
          </div>
          <div className="text-[11px] text-slate-500 line-through">Pre-VTON: {analytics.return_rate_before_vton}%</div>
        </div>
      </div>

      {/* Return Reduction Impact Chart & Funnel Analysis */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Return Reduction Comparative Analysis (7 cols) */}
        <div className="lg:col-span-7 bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-6">
          <div className="flex justify-between items-center pb-3 border-b border-slate-100">
            <div>
              <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                Return Rate Reduction Impact
              </h3>
              <p className="text-xs text-slate-500">Try-On Users vs Non-Try-On Shoppers</p>
            </div>
            <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold">
              71.4% Lower Returns
            </span>
          </div>

          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-xs font-bold text-slate-700 mb-1">
                <span>Traditional Non-Try-On Shoppers (Industry Average)</span>
                <span className="text-rose-600 font-mono text-sm">{analytics.return_rate_before_vton}%</span>
              </div>
              <div className="w-full h-4 rounded-full bg-slate-100 overflow-hidden">
                <div className="h-full bg-rose-500 rounded-full" style={{ width: `${analytics.return_rate_before_vton}%` }}></div>
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs font-bold text-slate-700 mb-1">
                <span>CONFIT AI Try-On & Fit Certified Shoppers</span>
                <span className="text-emerald-600 font-mono text-sm">{analytics.return_rate_after_vton}%</span>
              </div>
              <div className="w-full h-4 rounded-full bg-slate-100 overflow-hidden">
                <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${analytics.return_rate_after_vton}%` }}></div>
              </div>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-[#FAF9F6] border border-slate-200 text-xs text-slate-600 leading-relaxed">
            💡 <strong>Executive Takeaway:</strong> Providing AI Virtual Try-On and No-Photo measurement scaling dropped sizing-related return requests from 28% down to 8%, saving an estimated <strong>$42,800</strong> in reverse logistics and restocking costs this quarter.
          </div>
        </div>

        {/* Outfit Appearance Rankings ("Most Styled Items") (5 cols) */}
        <div className="lg:col-span-5 bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="pb-3 border-b border-slate-100">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
              Most Styled Items (Stylist ROI)
            </h3>
            <p className="text-xs text-slate-500">Ranking of pieces appearing most in user outfits</p>
          </div>

          <div className="space-y-3">
            {analytics.outfit_appearance_rankings.map((rank, idx) => (
              <div
                key={rank.product_id}
                className="flex items-center gap-3 p-2.5 rounded-2xl bg-[#FAF9F6] border border-slate-200"
              >
                <div className="w-8 h-8 rounded-xl bg-[#1B1F3B] text-white flex items-center justify-center font-bold text-xs shrink-0">
                  #{idx + 1}
                </div>
                <div className="w-12 h-14 rounded-lg bg-white overflow-hidden shrink-0">
                  <img src={rank.thumbnail_url} alt={rank.product_title} className="w-full h-full object-cover" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold text-[#1B1F3B] truncate">{rank.product_title}</div>
                  <div className="text-[11px] text-slate-500">
                    Styled in <strong className="text-[#B8935A]">{rank.outfit_appearances}</strong> ensembles
                  </div>
                </div>
                <div className="text-right text-[11px]">
                  <span className="font-bold text-emerald-600">{rank.purchase_rate}%</span>
                  <span className="text-slate-400 block text-[9px]">Conversion</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
