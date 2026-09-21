import { useTranslation } from 'react-i18next';
import React from 'react';
const percent = (value: number | null) => value == null ? 'Not enough data' : `${value}%`;
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';

export const BrandDashboardView: React.FC = () => {
  const { t } = useTranslation();
  const { profile, analytics, products, fetchErrors, isLoading, refresh } = useBrandViewModel();

  if (isLoading) {
    return <LoadingSpinner text={t('partnerPortal.text046')} />;
  }

  if (!analytics) {
    return (
      <EmptyState
        title={t('partnerPortal.text047')}
        description={fetchErrors.analytics || 'The merchant telemetry service could not be reached. No metrics are fabricated while it is down.'}
        actionText="Retry"
        onAction={refresh}
      />
    );
  }

  const hasData = analytics.total_views > 0 || analytics.total_purchases > 0;

  return (
    <div className="space-y-8 pb-20">
      {/* Brand Hero Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 text-white flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#B8935A]/20 text-[#B8935A] font-bold uppercase tracking-wider">
              {profile?.is_verified ? 'Verified Brand Partner' : 'Brand Partner — verification pending'}
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-bold uppercase">{t('partnerPortal.text048')}</span>
          </div>
          <h1 className="font-serif text-2xl sm:text-3xl font-bold text-white">
            {profile?.brand_name || 'Brand'}{' '}{t('partnerPortal.text049')}{' '}</h1>
          <p className="text-xs text-slate-400 mt-1">{' '}{t('partnerPortal.text050')}{' '}{analytics.total_products_count}{' '}{t('partnerPortal.text051')}{' '}{analytics.total_skus_count}{' '}{t('partnerPortal.text052')}{' '}{profile?.commission_rate != null ? `${profile.commission_rate}%` : 'Unavailable'}{' '}{t('partnerPortal.text053')}{' '}{percent(analytics.bopis_store_fulfillment_rate)}{' '}{t('partnerPortal.text054')}{' '}</p>
          <p className="text-[11px] text-slate-500 mt-1">{analytics.methodology}</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="bg-slate-800/80 px-4 py-2 rounded-2xl border border-slate-700 text-center">
            <span className="text-[10px] text-slate-400 block uppercase">{t('partnerPortal.text055')}</span>
            <span className="text-lg font-mono font-bold text-emerald-400">
              {percent(analytics.return_reduction_percentage)}
            </span>
          </div>
        </div>
      </div>

      {/* Metric Cards Grid - REAL DATA */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{' '}{t('partnerPortal.text056')}{' '}</span>
          <div className="text-2xl font-serif font-black text-[#1B1F3B]">
            {analytics.total_views.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-500 font-medium">{t('partnerPortal.text057')}</div>
          {!hasData && <div className="text-[10px] text-amber-600">{t('partnerPortal.text058')}</div>}
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{' '}{t('partnerPortal.text059')}{' '}</span>
          <div className="text-2xl font-serif font-black text-[#B8935A]">
            {analytics.total_tryons.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-500 font-medium">
            {analytics.total_views > 0 ? `${((analytics.total_tryons / analytics.total_views) * 100).toFixed(1)}% sessions per retained view` : 'From TryOnSession'}
          </div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{' '}{t('partnerPortal.text060')}{' '}</span>
          <div className="text-2xl font-serif font-black text-emerald-600">
            {analytics.funnel_conversion_rate == null ? t('partnerOps.insufficient') : analytics.funnel_conversion_rate == null ? t('partnerOps.insufficient') : `${analytics.funnel_conversion_rate}%`}
          </div>
          <div className="text-[11px] text-slate-500 font-medium">{t('partnerPortal.text061')}</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{' '}{t('partnerPortal.text062')}{' '}</span>
          <div className="text-2xl font-serif font-black text-emerald-600">
            {percent(analytics.return_rate_after_vton)}
          </div>
          <div className="text-[11px] text-slate-500">{' '}{t('partnerPortal.text063')}{' '}{percent(analytics.return_rate_before_vton)}{' '}{t('partnerPortal.text064')}{' '}</div>
        </div>
      </div>

      {/* Return Reduction Impact Chart & Funnel Analysis - REAL */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-7 bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-6">
          <div className="flex justify-between items-center pb-3 border-b border-slate-100">
            <div>
              <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">{' '}{t('partnerPortal.text065')}{' '}</h3>
              <p className="text-xs text-slate-500">{t('partnerPortal.text066')}</p>
            </div>
            <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold">
              {percent(analytics.return_reduction_percentage)}{' '}{t('partnerPortal.text067')}{' '}</span>
          </div>

          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-xs font-bold text-slate-700 mb-1">
                <span>{t('partnerPortal.text068')}</span>
                <span className="text-rose-600 font-mono text-sm">{percent(analytics.return_rate_before_vton)}</span>
              </div>
              <div className="w-full h-4 rounded-full bg-slate-100 overflow-hidden">
                <div className="h-full bg-rose-500 rounded-full" style={{ width: `${Math.min(100, (analytics.return_rate_before_vton ?? 0))}%` }}></div>
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs font-bold text-slate-700 mb-1">
                <span>{t('partnerPortal.text069')}</span>
                <span className="text-emerald-600 font-mono text-sm">{percent(analytics.return_rate_after_vton)}</span>
              </div>
              <div className="w-full h-4 rounded-full bg-slate-100 overflow-hidden">
                <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${Math.min(100, (analytics.return_rate_after_vton ?? 0))}%` }}></div>
              </div>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-[#FAF9F6] border border-slate-200 text-xs text-slate-600 leading-relaxed space-y-2">
            <div>💡 <strong>{t('partnerPortal.text070')}</strong> {analytics.return_cohorts?.methodology}</div>
            <div className="text-[11px] text-slate-500">{t('partnerPortal.text071')}{analytics.ad_spend_total}{' '}{t('partnerPortal.text072')}{analytics.ad_revenue_total}{' '}{t('partnerPortal.text073')}{' '}{percent(analytics.bopis_store_fulfillment_rate)}{' '}{t('partnerPortal.text074')}</div>
            {!hasData && <div className="text-amber-700 bg-amber-50 p-2 rounded">{t('partnerPortal.text075')}</div>}
          </div>
        </div>

        {/* Outfit Appearance Rankings - REAL */}
        <div className="lg:col-span-5 bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="pb-3 border-b border-slate-100">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">{' '}{t('partnerPortal.text076')}{' '}</h3>
            <p className="text-xs text-slate-500">{t('b2b.ranked_by_appearances')}</p>
          </div>

          <div className="space-y-3">
            {analytics.outfit_appearance_rankings.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500 space-y-2">
                <div>{t('partnerPortal.text077')}</div>
                <div className="text-[11px]">{t('partnerPortal.text078')}</div>
              </div>
            ) : (
              analytics.outfit_appearance_rankings.map((rank, idx) => (
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
                    <div className="text-[11px] text-slate-500">{' '}{t('partnerPortal.text079')}{' '}<strong className="text-[#B8935A]">{rank.outfit_appearances}</strong>{' '}{t('partnerPortal.text080')}{' '}</div>
                    <div className="text-[10px] text-slate-400">{t('partnerPortal.text081')}{' '}{rank.add_to_cart_rate}{t('partnerPortal.text082')}{' '}{rank.purchase_rate}%</div>
                  </div>
                  <div className="text-right text-[11px]">
                    <span className="font-bold text-emerald-600">{rank.purchase_rate}%</span>
                    <span className="text-slate-400 block text-[9px]">{t('partnerPortal.text083')}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Products Summary */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B] mb-4">{t('partnerPortal.text084')}</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div className="p-3 rounded-xl bg-[#FAF9F6] border">
            <span className="text-slate-400 text-[10px] uppercase block">{t('partnerPortal.text085')}</span>
            <span className="font-bold text-lg">{analytics.total_products_count}</span>
          </div>
          <div className="p-3 rounded-xl bg-[#FAF9F6] border">
            <span className="text-slate-400 text-[10px] uppercase block">{t('partnerPortal.text086')}</span>
            <span className="font-bold text-lg">{analytics.total_skus_count}</span>
          </div>
          <div className="p-3 rounded-xl bg-[#FAF9F6] border">
            <span className="text-slate-400 text-[10px] uppercase block">{t('partnerPortal.text087')}</span>
            <span className="font-bold text-lg text-emerald-600">{analytics.total_purchases}</span>
          </div>
          <div className="p-3 rounded-xl bg-[#FAF9F6] border">
            <span className="text-slate-400 text-[10px] uppercase block">{t('partnerPortal.text088')}</span>
            <span className="font-bold text-lg">{analytics.total_add_to_carts}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
