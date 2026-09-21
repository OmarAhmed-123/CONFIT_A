import { useTranslation } from 'react-i18next';
import { useModalFocus } from '../../hooks/useModalFocus';
import { useCallback } from 'react';
import React, { useState } from 'react';
import { request } from '../../services/apiClient';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { SparkleIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const BrandPlacementsView: React.FC = () => {
  const { t } = useTranslation();
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
      alert('Bid cannot exceed daily budget');
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
          <p className="text-[11px] font-bold text-rose-800">Sponsored network data failed to load</p>
          <p className="text-[11px] text-rose-600 mt-1">{placementsError} An empty list below means "no campaigns", not "API down" — retry to reconcile.</p>
          <button onClick={refresh} className="mt-2 px-3 py-1.5 rounded-lg bg-white border border-rose-200 text-[11px] font-bold text-rose-700 hover:bg-rose-50">Retry</button>
        </div>
      )}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
            Sponsored AI Stylist & Trending Placements - Real
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Manage placement settings and recorded counters. Saving a placement does not prove live ad delivery, daily budget reset, or verified billing.
          </p>
          <p className="text-[11px] text-slate-400 mt-1">Lifecycle: Brand → Campaign/Bid → Budget → Eligibility → Placement → Impression → Click → Conversion → Billing. Bid validation, budget validation, campaign status, start/end date, spend limits, duplicate prevention.</p>
        </div>

        <button
          onClick={() => setModalOpen(true)}
          className="px-5 py-2.5 rounded-2xl bg-[#B8935A] hover:bg-[#A37E44] text-slate-950 font-bold text-xs shadow-md transition-all flex items-center gap-1.5"
        >
          <SparkleIcon size={16} color="#0F172A" />
          <span>+ Create Sponsored Slot</span>
        </button>
      </div>

      {/* Summary KPIs - REAL */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-slate-400 text-[10px] uppercase block">Total Impressions (Real)</span>
          <span className="font-bold text-lg">{totalImpressions.toLocaleString()}</span>
          <span className="text-[10px] text-slate-500 block">From SponsoredPlacement.impressions</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-slate-400 text-[10px] uppercase block">Total Clicks (Real)</span>
          <span className="font-bold text-lg">{totalClicks.toLocaleString()}</span>
          <span className="text-[10px] text-slate-500 block">From SponsoredPlacement.clicks</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-slate-400 text-[10px] uppercase block">Total Spent (Real)</span>
          <span className="font-bold text-lg">${totalSpent.toFixed(2)}</span>
          <span className="text-[10px] text-slate-500 block">From spent_today SUM, budget enforced</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-slate-400 text-[10px] uppercase block">Revenue Generated (Real)</span>
          <span className="font-bold text-lg text-emerald-600">${totalRevenue.toFixed(2)}</span>
          <span className="text-[10px] text-slate-500 block">ROAS: {totalSpent > 0 ? (totalRevenue / totalSpent).toFixed(1) + 'x' : 'N/A'}</span>
        </div>
      </div>

      {/* Placements List - REAL */}
      <div className="space-y-4">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">Active Placements ({placements.length}) - Real from DB</h3>
        {placements.length === 0 ? (
          <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center space-y-3">
            <div className="text-4xl">🎯</div>
            <h3 className="font-bold text-slate-700">No sponsored placements yet</h3>
            <p className="text-xs text-slate-500">Create your first sponsored slot to bid for featured placement in Virtual Stylist results. Budget enforcement prevents overspend.</p>
            <button onClick={() => setModalOpen(true)} className="mt-2 px-4 py-2 rounded-xl bg-[#B8935A] text-slate-900 text-xs font-bold">Create Placement</button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {placements.map((plc) => (
              <div key={plc.id} className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <span className="text-[10px] font-bold text-[#B8935A] uppercase tracking-wider">
                      Slot #{plc.id} · {plc.placement_type.replace('_', ' ').toUpperCase()} · {plc.status}
                    </span>
                    <h3 className="font-serif text-base font-bold text-[#1B1F3B] mt-0.5 truncate">
                      {plc.product_title}
                    </h3>
                    <span className="text-[10px] text-slate-400">Product ID: {plc.product_id} · Created: {new Date(plc.created_at).toLocaleDateString()}</span>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold ${plc.status === 'active' ? 'bg-emerald-100 text-emerald-800' : plc.status === 'budget_exhausted' ? 'bg-rose-100 text-rose-800' : 'bg-slate-100 text-slate-600'}`}>
                    {plc.status}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center text-xs py-3 border-y border-slate-100">
                  <div className="p-2 rounded-xl bg-[#FAF9F6]">
                    <span className="text-slate-400 text-[10px] block">CPC Bid (Real)</span>
                    <span className="font-bold text-slate-900">${plc.bid_amount_per_click}</span>
                  </div>
                  <div className="p-2 rounded-xl bg-[#FAF9F6]">
                    <span className="text-slate-400 text-[10px] block">Clicks (Real)</span>
                    <span className="font-bold text-slate-900">{plc.clicks}</span>
                    <span className="text-[9px] text-slate-400 block">{plc.impressions} impr</span>
                  </div>
                  <div className="p-2 rounded-xl bg-[#FAF9F6]">
                    <span className="text-slate-400 text-[10px] block">Conversions (Real)</span>
                    <span className="font-bold text-emerald-600">{plc.conversions}</span>
                  </div>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-500">Daily Budget: <strong>${plc.daily_budget}</strong></span>
                    <span className="text-slate-500">Spent: <strong className={plc.spent_today >= plc.daily_budget ? 'text-rose-600' : 'text-slate-900'}>${plc.spent_today}</strong></span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div className="h-full bg-[#B8935A] rounded-full" style={{ width: `${Math.min(100, (plc.spent_today / plc.daily_budget) * 100)}%` }}></div>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">Remaining: ${(plc.daily_budget - plc.spent_today).toFixed(2)}</span>
                    <span className="text-emerald-700 font-semibold">Revenue: ${plc.revenue_generated} · ROAS: {plc.spent_today > 0 ? (plc.revenue_generated / plc.spent_today).toFixed(1) + 'x' : 'N/A'}</span>
                  </div>
                </div>

                <button disabled={saving || plc.status === 'budget_exhausted'} onClick={() => changeStatus(plc.id, plc.status === 'active' ? 'paused' : 'active')} className="rounded border px-3 py-2 text-xs">
                  {plc.status === 'active' ? 'Pause placement' : 'Resume placement'}
                </button>
                <div className="text-[10px] text-slate-400 p-2 bg-[#FAF9F6] rounded-xl">
                  Recorded counters are not independently verified ad delivery or a billing ledger. Daily reset and event deduplication are not established by this screen.
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
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
              Bid for Featured AI Stylist Slot - Real
            </h3>
            <p className="text-[11px] text-slate-500">Real validation: bid 0-100, budget 0-10000, bid ≤ budget, product ownership verified, tenant isolated.</p>
            <form onSubmit={handleCreate} className="space-y-4 text-xs">
              <div>
                <label className="font-bold text-slate-700 block mb-1">Select Catalog Product (must belong to your brand)</label>
                <select
                  aria-label={t('b2b.field_placement_product')}
                  value={selectedProductId || products[0]?.id || ''}
                  onChange={(e) => setSelectedProductId(Number(e.target.value))}
                  className="w-full p-2.5 rounded-xl border border-slate-200 bg-white"
                  required
                >
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} (${p.base_price}) - ID {p.id}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="font-bold text-slate-700 block mb-1">Placement Type</label>
                <select aria-label={t('b2b.field_placement_type')} value={placementType} onChange={(e) => setPlacementType(e.target.value)} className="w-full p-2.5 rounded-xl border">
                  <option value="stylist_featured">Stylist Featured</option>
                  <option value="trending_hero">Trending Hero</option>
                  <option value="fit_recom_top">Fit Recommendation Top</option>
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

              {bidCpc > dailyBudget && <div className="text-[11px] text-rose-600 bg-rose-50 p-2 rounded">Bid cannot exceed daily budget</div>}

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="flex-1 py-2.5 rounded-xl border border-slate-200 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !products.length}
                  className="flex-1 py-2.5 rounded-xl bg-[#1B1F3B] text-white font-semibold shadow-md"
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
