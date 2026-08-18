import React from 'react';
import { useCartStore } from '../../stores/cartStore';
import { DuplicateAlertIcon, SparkleIcon, WardrobeIcon } from '../icons/ConfitIcons';
import { Link } from 'react-router-dom';

export const DuplicateAlertModal: React.FC = () => {
  const { pendingDuplicateAlert, confirmAddDuplicate, dismissDuplicate } = useCartStore();

  if (!pendingDuplicateAlert) return null;

  const owned = pendingDuplicateAlert.owned_item;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md animate-in fade-in duration-150">
      <div className="w-full max-w-lg bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden">
        {/* Header with Gold Alert Motif */}
        <div className="p-5 bg-[#FDF8EE] border-b border-[#B8935A]/30 flex items-start gap-3.5">
          <div className="w-11 h-11 rounded-2xl bg-white border border-[#B8935A]/40 flex items-center justify-center text-[#B8935A] shadow-xs shrink-0">
            <DuplicateAlertIcon size={24} color="#B8935A" />
          </div>
          <div>
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
              Smart Duplicate Purchase Alert
            </h3>
            <p className="text-xs text-slate-600 mt-0.5">
              CONFIT's smart shopping engine detected strong aesthetic similarity to a piece in your virtual wardrobe.
            </p>
          </div>
        </div>

        {/* Owned Piece Card */}
        <div className="p-6 space-y-4">
          <div className="bg-[#FAF9F6] border border-slate-200 rounded-2xl p-3.5 flex items-center gap-3.5">
            <div className="w-18 h-22 rounded-xl overflow-hidden bg-slate-200 shrink-0">
              <img src={owned.image_url} alt={owned.title} className="w-full h-full object-cover" />
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-[10px] font-bold text-[#B8935A] uppercase tracking-wider">
                Already in your closet
              </span>
              <h4 className="text-sm font-bold text-[#1B1F3B] truncate">{owned.title}</h4>
              <p className="text-xs text-slate-500">{owned.color_name} · {owned.category}</p>
              <div className="flex items-center gap-2 mt-1.5 text-[11px] text-slate-600">
                <span>Worn {owned.wear_count || 0} times</span>
                <span>•</span>
                <span className="capitalize">{owned.wear_frequency}</span>
              </div>
            </div>
          </div>

          <p className="text-xs text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-xl border border-slate-100">
            💡 <strong>Stylist Recommendation:</strong> Shopping sustainably means styling what you own first. Would you like to style this owned piece with new pairings, or proceed with purchasing the new item?
          </p>

          {/* Decision Actions */}
          <div className="grid grid-cols-2 gap-3 pt-2">
            <button
              onClick={() => {
                dismissDuplicate();
              }}
              className="py-2.5 px-4 rounded-xl border border-slate-300 hover:border-[#1B1F3B] text-slate-700 font-semibold text-xs transition-all text-center flex items-center justify-center gap-1.5"
            >
              <WardrobeIcon size={16} />
              <span>Style What I Own</span>
            </button>

            <button
              onClick={confirmAddDuplicate}
              className="py-2.5 px-4 rounded-xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white font-semibold text-xs transition-all shadow-sm text-center"
            >
              Proceed to Add Anyway
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
