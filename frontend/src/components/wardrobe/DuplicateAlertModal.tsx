import React from 'react';
import { useCartStore } from '../../stores/cartStore';
import { DuplicateAlertIcon, SparkleIcon, WardrobeIcon } from '../icons/ConfitIcons';
import { Link } from 'react-router-dom';
import { HonestProductImage } from '../common/HonestProductImage';
import { useTranslation } from 'react-i18next';

export const DuplicateAlertModal: React.FC = () => {
  const { t } = useTranslation();
  const { pendingDuplicateAlert, confirmAddDuplicate, dismissDuplicate } = useCartStore();

  if (!pendingDuplicateAlert) return null;

  const owned = pendingDuplicateAlert.owned_item;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md animate-in fade-in duration-150">
      <div className="w-full max-w-lg bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden">
        {/* Header with Gold Alert Motif */}
        <div className="p-5 bg-brand-wash border-b border-brand-hairline flex items-start gap-3.5">
          <div className="w-11 h-11 rounded-2xl bg-white border border-brand-hairline flex items-center justify-center text-brand-charcoal shadow-xs shrink-0">
            <DuplicateAlertIcon size={24} color="#242526" />
          </div>
          <div>
            <h3 className="font-serif text-base font-bold text-brand-charcoal">
              {t("wardrobe.dup_alert_title")}
            </h3>
            <p className="text-xs text-slate-600 mt-0.5">
              {t("wardrobe.dup_alert_message")}
            </p>
          </div>
        </div>

        {/* Owned Piece Card */}
        <div className="p-6 space-y-4">
          <div className="bg-brand-wash border border-slate-200 rounded-2xl p-3.5 flex items-center gap-3.5">
            <div className="w-18 h-22 rounded-xl overflow-hidden bg-slate-200 shrink-0">
              <HonestProductImage src={owned.image_url} alt={owned.title} className="w-full h-full object-cover" />
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-[10px] font-bold text-brand-charcoal uppercase tracking-wider">
                {t("wardrobe.dup_already_in_closet")}
              </span>
              <h4 className="text-sm font-bold text-brand-charcoal truncate">{owned.title}</h4>
              <p className="text-xs text-slate-500">{owned.color_name} · {owned.category}</p>
              <div className="flex items-center gap-2 mt-1.5 text-[11px] text-slate-600">
                <span>{t("wardrobe.dup_worn_times", { count: owned.wear_count || 0 })}</span>
                <span>•</span>
                <span className="capitalize">{owned.wear_frequency}</span>
              </div>
            </div>
          </div>

          <p className="text-xs text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-xl border border-slate-100">
            💡 <strong>{t("wardrobe.dup_stylist_recommendation")}</strong> {t("wardrobe.dup_stylist_message")}
          </p>

          {/* Decision Actions */}
          <div className="grid grid-cols-2 gap-3 pt-2">
            <button data-motion="creative"
              onClick={() => {
                dismissDuplicate();
              }}
              className="py-2.5 px-4 rounded-xl border border-slate-300 hover:border-brand-charcoal text-slate-700 font-semibold text-xs transition-all text-center flex items-center justify-center gap-1.5"
            >
              <WardrobeIcon size={16} />
              <span>{t('wardrobe.style_what_i_own')}</span>
            </button>

            <button data-motion="progressive"
              onClick={confirmAddDuplicate}
              className="py-2.5 px-4 rounded-xl bg-brand-charcoal hover:bg-black text-white font-semibold text-xs transition-all shadow-sm text-center"
            >
              {t("wardrobe.dup_proceed_anyway")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
