import React from 'react';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { BopisIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const BrandInventoryView: React.FC = () => {
  const { products, isLoading } = useBrandViewModel();

  if (isLoading) {
    return <LoadingSpinner text="Connecting to store inventory nodes..." />;
  }

  const boutiques = [
    { id: 1, name: 'The Dubai Mall (Fashion Avenue)', city: 'Dubai, UAE', total_skus: 42, active_bopis: 38, avg_prep_time: '45 mins' },
    { id: 2, name: 'Mall of the Emirates (Central Galleria)', city: 'Dubai, UAE', total_skus: 36, active_bopis: 32, avg_prep_time: '50 mins' },
    { id: 3, name: 'Kingdom Centre (Al Olaya)', city: 'Riyadh, Saudi Arabia', total_skus: 48, active_bopis: 44, avg_prep_time: '40 mins' },
  ];

  return (
    <div className="space-y-8 pb-20">
      <div className="border-b border-slate-200 pb-4">
        <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
          BOPIS Store Network & Live Inventory
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Monitor physical store stock levels, customer pickup SLAs, and in-store fulfillment nodes.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {boutiques.map((b) => (
          <div key={b.id} className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#FAF9F6] border border-slate-200 flex items-center justify-center text-[#1B1F3B]">
                <BopisIcon size={20} color="#1B1F3B" />
              </div>
              <div>
                <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{b.name}</h3>
                <span className="text-xs text-slate-500">{b.city}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-100">
              <div className="p-2.5 rounded-xl bg-[#FAF9F6]">
                <span className="text-slate-400 text-[10px] block">Active SKUs</span>
                <span className="font-bold text-slate-900">{b.active_bopis} / {b.total_skus}</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#FAF9F6]">
                <span className="text-slate-400 text-[10px] block">Avg Prep Time</span>
                <span className="font-bold text-emerald-600">{b.avg_prep_time}</span>
              </div>
            </div>

            <div className="flex items-center justify-between text-xs pt-1">
              <span className="text-emerald-700 font-semibold text-[11px] flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                <span>Boutique Node Online</span>
              </span>
              <button className="text-xs font-bold text-[#B8935A] hover:underline">
                Manage Stock →
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
