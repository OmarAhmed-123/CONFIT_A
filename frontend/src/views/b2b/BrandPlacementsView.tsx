import React, { useState } from 'react';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { SparkleIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const BrandPlacementsView: React.FC = () => {
  const { placements, products, createSponsoredSlot, isLoading } = useBrandViewModel();
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedProductId, setSelectedProductId] = useState<number>(1);
  const [bidCpc, setBidCpc] = useState<number>(0.75);
  const [dailyBudget, setDailyBudget] = useState<number>(100);

  if (isLoading) {
    return <LoadingSpinner text="Loading ad network & sponsored placements..." />;
  }

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    createSponsoredSlot({
      productId: selectedProductId,
      bidAmount: bidCpc,
      dailyBudget,
      placementType: 'stylist_featured',
    });
    setModalOpen(false);
  };

  return (
    <div className="space-y-8 pb-20">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
            Sponsored AI Stylist & Trending Placements
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Bid for high-intent featured slots in conversational Virtual Stylist results and Trending Hero carousels.
          </p>
        </div>

        <button
          onClick={() => setModalOpen(true)}
          className="px-5 py-2.5 rounded-2xl bg-[#B8935A] hover:bg-[#A37E44] text-slate-950 font-bold text-xs shadow-md transition-all flex items-center gap-1.5"
        >
          <SparkleIcon size={16} color="#0F172A" />
          <span>+ Create Sponsored Slot</span>
        </button>
      </div>

      {/* Placements List */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {placements.map((plc) => (
          <div key={plc.id} className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
            <div className="flex justify-between items-start">
              <div>
                <span className="text-[10px] font-bold text-[#B8935A] uppercase tracking-wider">
                  Slot #{plc.id} · {plc.placement_type.replace('_', ' ').toUpperCase()}
                </span>
                <h3 className="font-serif text-base font-bold text-[#1B1F3B] mt-0.5">
                  {plc.product_title}
                </h3>
              </div>
              <span className="px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold">
                Active Bidding
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-center text-xs py-3 border-y border-slate-100">
              <div className="p-2 rounded-xl bg-[#FAF9F6]">
                <span className="text-slate-400 text-[10px] block">CPC Bid</span>
                <span className="font-bold text-slate-900">${plc.bid_amount_per_click}</span>
              </div>
              <div className="p-2 rounded-xl bg-[#FAF9F6]">
                <span className="text-slate-400 text-[10px] block">Clicks</span>
                <span className="font-bold text-slate-900">{plc.clicks}</span>
              </div>
              <div className="p-2 rounded-xl bg-[#FAF9F6]">
                <span className="text-slate-400 text-[10px] block">Conversions</span>
                <span className="font-bold text-emerald-600">{plc.conversions}</span>
              </div>
            </div>

            <div className="flex justify-between items-center text-xs text-slate-500">
              <span>Daily Budget: <strong>${plc.daily_budget}</strong></span>
              <span className="text-emerald-700 font-semibold">ROAS: 8.4x</span>
            </div>
          </div>
        ))}
      </div>

      {/* Create Placement Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="w-full max-w-md bg-white rounded-3xl p-6 shadow-2xl space-y-4">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
              Bid for Featured AI Stylist Slot
            </h3>
            <form onSubmit={handleCreate} className="space-y-4 text-xs">
              <div>
                <label className="font-bold text-slate-700 block mb-1">Select Catalog Product</label>
                <select
                  value={selectedProductId}
                  onChange={(e) => setSelectedProductId(Number(e.target.value))}
                  className="w-full p-2.5 rounded-xl border border-slate-200 bg-white"
                >
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} (${p.base_price})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-bold text-slate-700 block mb-1">CPC Bid ($)</label>
                  <input
                    type="number"
                    step="0.05"
                    value={bidCpc}
                    onChange={(e) => setBidCpc(Number(e.target.value))}
                    className="w-full p-2.5 rounded-xl border border-slate-200"
                  />
                </div>
                <div>
                  <label className="font-bold text-slate-700 block mb-1">Daily Budget ($)</label>
                  <input
                    type="number"
                    value={dailyBudget}
                    onChange={(e) => setDailyBudget(Number(e.target.value))}
                    className="w-full p-2.5 rounded-xl border border-slate-200"
                  />
                </div>
              </div>

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
                  className="flex-1 py-2.5 rounded-xl bg-[#1B1F3B] text-white font-semibold shadow-md"
                >
                  Launch Bid
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
