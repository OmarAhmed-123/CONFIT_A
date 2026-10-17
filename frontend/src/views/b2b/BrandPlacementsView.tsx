import { useTranslation } from 'react-i18next';
import { useModalFocus } from '../../hooks/useModalFocus';
import { useCallback } from 'react';
import React, { useState } from 'react';
import { request } from '../../services/apiClient';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { SparkleIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';
import { formatMoney } from '../../i18n/format';

export const BrandPlacementsView: React.FC = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? 'en';
  const { placements, products, createSponsoredSlot, fetchErrors, isLoading, refresh } = useBrandViewModel();
  const [actionMessage, setActionMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedProductId, setSelectedProductId] = useState<number>(0);
  const [bidCpc, setBidCpc] = useState<number>(0.75);
  const [dailyBudget, setDailyBudget] = useState<number>(100);
  const [placementType, setPlacementType] = useState<string>('stylist_featured');

  const closeDialog = useCallback(() => { if (!saving) setModalOpen(false); }, [saving]);
  const dialogRef = useModalFocus<HTMLDivElement>(closeDialog, modalOpen);

  if (isLoading) {
    return <LoadingSpinner text="Loading ad network & sponsored placements..." />;
  }

  // Failed placement/products fetch is an explicit error state (with retry),
  // never an empty list pretending the campaign network has nothing on it.
  const placementsError = fetchErrors.placements || fetchErrors.products;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    const productId = selectedProductId || products[0]?.id;
    if (!productId || !products.some(p => p.id === productId)) return;
    if (bidCpc <= 0 || bidCpc > 100) {
      alert('Bid must be 0-100');
      return;
    }
    if (dailyBudget <= 0 || dailyBudget > 10000) {
      alert('Daily budget must be 0-10000');
      return;
    }
    if (bidCpc > dailyBudget) {
      alert(t("brand_placements.bid_exceeds_budget"));
      return;
    }
    setSaving(true);
    const saved = await createSponsoredSlot({
      productId,
      bidAmount: bidCpc,
      dailyBudget,
      placementType,
    });
    setSaving(false);
    if (saved) setModalOpen(false);
  };

  const changeStatus = async (id: number, status: string) => {
    if (saving) return;
    setSaving(true); setActionMessage('');
    try {
      await request(`/partner/placements/${id}`, {method: 'PATCH', body: JSON.stringify({status})});
      await refresh();
      setActionMessage('Placement status saved.');
    } catch (error: any) { setActionMessage(`Not saved: ${error.message}`); }
    finally { setSaving(false); }
  };

  const totalImpressions = placements.reduce((sum, p) => sum + p.impressions, 0);
  const totalClicks = placements.reduce((sum, p) => sum + p.clicks, 0);
  const totalSpent = placements.reduce((sum, p) => sum + p.spent_today, 0);
  const totalRevenue = placements.reduce((sum, p) => sum + p.revenue_generated, 0);

  return (
    <div className="space-y-8 pb-20">
      {actionMessage && <p role="status">{actionMessage}</p>}
      {placementsError && (
        <div role="alert" className="p-4 rounded-2xl bg-rose-50 border border-rose-200">
          <p className="text-[11px] font-bold text-rose-800">{t("brand_placements.sponsored_failed")}</p>
          <p className="text-[11px] text-rose-600 mt-1">{placementsError} An empty list below means "no campaigns", not "API down" — retry to reconcile.</p>
          <button data-motion="recovery" onClick={refresh} className="mt-2 px-3 py-1.5 rounded-lg bg-white border border-rose-200 text-[11px] font-bold text-rose-700 hover:bg-rose-50">{t("common.retry")}</button>
        </div>
      )}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <h1 className="font-serif text-3xl font-bold text-brand-charcoal">
            {t("b2b.placements_heading")}
          </h1>
          <p className="text-xs sm:text-sm text-brand-muted mt-1">
            {t("b2b.placements_heading_note")}
          </p>
          <p className="text-[11px] text-brand-muted mt-1">Lifecycle: Brand → Campaign/Bid → Budget → Eligibility → Placement → Impression → Click → Conversion → Billing. Bid validation, budget validation, campaign status, start/end date, spend limits, duplicate prevention.</p>
        </div>

        <button data-motion="admin"
          onClick={() => setModalOpen(true)}
          className="px-5 py-2.5 rounded-2xl bg-brand-charcoal text-white hover:bg-black font-bold text-xs shadow-md transition-all flex items-center gap-1.5"
        >
          <SparkleIcon size={16} color="currentColor" />
          <span>+ Create Sponsored Slot</span>
        </button>
      </div>

      {/* Summary KPIs - REAL */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-brand-muted text-[10px] uppercase block">{t("b2b.placements_impressions")}</span>
          <span className="font-bold text-lg">{totalImpressions.toLocaleString()}</span>
          <span className="text-[10px] text-brand-muted block">{t("b2b.placements_impressions_src")}</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-brand-muted text-[10px] uppercase block">{t("b2b.placements_clicks_total")}</span>
          <span className="font-bold text-lg">{totalClicks.toLocaleString()}</span>
          <span className="text-[10px] text-brand-muted block">{t("b2b.placements_clicks_src")}</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-brand-muted text-[10px] uppercase block">{t("b2b.placements_spent_total")}</span>
          <span className="font-bold text-lg">${totalSpent.toFixed(2)}</span>
          <span className="text-[10px] text-brand-muted block">From spent_today SUM, budget enforced</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-brand-muted text-[10px] uppercase block">{t("b2b.placements_revenue")}</span>
          <span className="font-bold text-lg text-emerald-700">${totalRevenue.toFixed(2)}</span>
          <span className="text-[10px] text-brand-muted block">{t("b2b.placements_roas")} {totalSpent > 0 ? (totalRevenue / totalSpent).toFixed(1) + 'x' : 'N/A'}</span>
        </div>
      </div>

      {/* Placements List - REAL */}
      <div className="space-y-4">
        <h3 className="font-serif text-lg font-bold text-brand-charcoal">{t("b2b.placements_active", { count: placements.length })} {t("b2b.placements_real_from_db")}</h3>
        {placements.length === 0 ? (
          <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center space-y-3">
            <div className="text-4xl">🎯</div>
            <h3 className="font-bold text-slate-700">{t("brand_placements.no_placements")}</h3>
            <p className="text-xs text-brand-muted">{t("b2b.placements_empty")}</p>
            <button data-motion="admin" onClick={() => setModalOpen(true)} className="mt-2 px-4 py-2 rounded-xl bg-brand-charcoal text-white text-xs font-bold">{t("brand_placements.create_placement")}</button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {placements.map((plc) => (
              <div key={plc.id} className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <span className="text-[10px] font-bold text-brand-charcoal uppercase tracking-wider">
                      Slot #{plc.id} · {plc.placement_type.replace('_', ' ').toUpperCase()} · {plc.status}
                    </span>
                    <h3 className="font-serif text-base font-bold text-brand-charcoal mt-0.5 truncate">
                      {plc.product_title}
                    </h3>
                    <span className="text-[10px] text-brand-muted">{t("b2b.placements_product_id")} {plc.product_id} · {t("b2b.placements_created_at")} {new Date(plc.created_at).toLocaleDateString()}</span>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold ${plc.status === 'active' ? 'bg-emerald-100 text-emerald-800' : plc.status === 'budget_exhausted' ? 'bg-rose-100 text-rose-800' : 'bg-slate-100 text-slate-600'}`}>
                    {plc.status}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center text-xs py-3 border-y border-slate-100">
                  <div className="p-2 rounded-xl bg-brand-wash">
                    <span className="text-brand-muted text-[10px] block">{t("b2b.placements_cpc_bid")}</span>
                    <span className="font-bold text-slate-900">${plc.bid_amount_per_click}</span>
                  </div>
                  <div className="p-2 rounded-xl bg-brand-wash">
                    <span className="text-brand-muted text-[10px] block">{t("b2b.placements_clicks")}</span>
                    <span className="font-bold text-slate-900">{plc.clicks}</span>
                    <span className="text-[9px] text-brand-muted block">{plc.impressions} impr</span>
                  </div>
                  <div className="p-2 rounded-xl bg-brand-wash">
                    <span className="text-brand-muted text-[10px] block">{t("b2b.placements_conversions")}</span>
                    <span className="font-bold text-emerald-700">{plc.conversions}</span>
                  </div>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-brand-muted">{t("b2b.placements_daily_budget")} <strong>${plc.daily_budget}</strong></span>
                    <span className="text-brand-muted">{t("b2b.placements_spent")} <strong className={plc.spent_today >= plc.daily_budget ? 'text-rose-600' : 'text-slate-900'}>${plc.spent_today}</strong></span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div className="h-full bg-brand-charcoal text-white rounded-full" style={{ width: `${Math.min(100, (plc.spent_today / plc.daily_budget) * 100)}%` }}></div>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-brand-muted">Remaining: ${(plc.daily_budget - plc.spent_today).toFixed(2)}</span>
                    <span className="text-emerald-700 font-semibold">Revenue: ${plc.revenue_generated} · ROAS: {plc.spent_today > 0 ? (plc.revenue_generated / plc.spent_today).toFixed(1) + 'x' : 'N/A'}</span>
                  </div>
                </div>

                <button data-motion="admin" data-motion-tone="icon" disabled={saving || plc.status === 'budget_exhausted'} onClick={() => changeStatus(plc.id, plc.status === 'active' ? 'paused' : 'active')} className="rounded border px-3 py-2 text-xs">
                  {plc.status === 'active' ? 'Pause placement' : 'Resume placement'}
                </button>
                <div className="text-[10px] text-brand-muted p-2 bg-brand-wash rounded-xl">
                  {t("b2b.placements_counters_note")}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Placement Modal - REAL WITH VALIDATION */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-150">
          <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={t('b2b.form_create_placement')} tabIndex={-1} className="w-full max-w-md bg-white rounded-3xl p-6 shadow-2xl space-y-4">
            <h3 className="font-serif text-lg font-bold text-brand-charcoal">
              {t("b2b.placements_form_heading")}
            </h3>
            <p className="text-[11px] text-brand-muted">Real validation: bid 0-100, budget 0-10000, bid ≤ budget, product ownership verified, tenant isolated.</p>
            <form onSubmit={handleCreate} className="space-y-4 text-xs">
              <div>
                <label className="font-bold text-slate-700 block mb-1">{t("b2b.placements_select_product")}</label>
                <select
                  aria-label={t('b2b.field_placement_product')}
                  value={selectedProductId || products[0]?.id || ''}
                  onChange={(e) => setSelectedProductId(Number(e.target.value))}
                  className="w-full p-2.5 rounded-xl border border-slate-200 bg-white"
                  required
                >
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {/* Was a raw interpolation of the base price with a
                          hard-coded dollar sign: Latin digits and the wrong
                          symbol for any non-USD brand, and wrong again in the
                          Arabic UI. */}
                      {p.title} (
                      {formatMoney(
                        Math.round(p.base_price * 100),
                        p.currency || 'USD',
                        lang,
                      )}
                      ) - ID {p.id}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="font-bold text-slate-700 block mb-1">{t("brand_placements.placement_type")}</label>
                <select aria-label={t('b2b.field_placement_type')} value={placementType} onChange={(e) => setPlacementType(e.target.value)} className="w-full p-2.5 rounded-xl border">
                  <option value="stylist_featured">{t("brand_placements.stylist_featured")}</option>
                  <option value="trending_hero">{t("brand_placements.trending_hero")}</option>
                  <option value="fit_recom_top">{t("brand_placements.fit_recommendation_top")}</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-bold text-slate-700 block mb-1">CPC Bid ($) 0-100</label>
                  <input
                    type="number"
                    step="0.01"
                    min={0.01}
                    max={100}
                    aria-label={t('b2b.field_bid_cpc')}
                    value={bidCpc}
                    onChange={(e) => setBidCpc(Number(e.target.value))}
                    className="w-full p-2.5 rounded-xl border border-slate-200"
                    required
                  />
                </div>
                <div>
                  <label className="font-bold text-slate-700 block mb-1">Daily Budget ($) 0-10000</label>
                  <input
                    type="number"
                    min={0.01}
                    step="0.01"
                    max={10000}
                    aria-label={t('b2b.field_daily_budget')}
                    value={dailyBudget}
                    onChange={(e) => setDailyBudget(Number(e.target.value))}
                    className="w-full p-2.5 rounded-xl border border-slate-200"
                    required
                  />
                </div>
              </div>

              {bidCpc > dailyBudget && <div className="text-[11px] text-rose-600 bg-rose-50 p-2 rounded">{t("brand_placements.bid_exceeds_budget")}</div>}

              <div className="flex gap-2 pt-2">
                <button data-motion="neutral"
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="flex-1 py-2.5 rounded-xl border border-slate-200 font-semibold"
                >
                  {t("common.cancel")}
                </button>
                <button data-motion="admin" data-motion-tone="icon"
                  type="submit"
                  disabled={saving || !products.length}
                  className="flex-1 py-2.5 rounded-xl bg-brand-charcoal text-white font-semibold shadow-md"
                >
                  {saving ? 'Saving…' : 'Save placement'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
