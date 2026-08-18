import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '../../stores/uiStore';
import { useStylistViewModel } from '../../viewmodels/useStylistViewModel';
import { StylistIcon, SparkleIcon, BagIcon, TryOnIcon } from '../icons/ConfitIcons';
import { FitScoreBadge } from '../common/CommonComponents';

export const VirtualStylistDrawer: React.FC = () => {
  const { t } = useTranslation();
  const { isStylistDrawerOpen, closeStylist, stylistPrefillOccasion, openTryOn } = useUIStore();
  const {
    messages,
    inputPrompt,
    setInputPrompt,
    isTyping,
    isRecording,
    error,
    sendPrompt,
    simulateVoiceInput,
    addCompleteLookToCart,
  } = useStylistViewModel();

  // Prefill occasion if opened with shortcut
  useEffect(() => {
    if (isStylistDrawerOpen && stylistPrefillOccasion && messages.length === 0) {
      sendPrompt(`Style a complete outfit for ${stylistPrefillOccasion}`, stylistPrefillOccasion);
    }
  }, [isStylistDrawerOpen, stylistPrefillOccasion, messages.length, sendPrompt]);

  if (!isStylistDrawerOpen) return null;

  const getPositionBadge = (pos: string) => {
    switch (pos?.toLowerCase()) {
      case 'outerwear':
        return { label: 'Outerwear', bg: 'bg-[#1B1F3B] text-[#E2BF70] border border-[#C5A059]/40' };
      case 'top':
        return { label: 'Top / Shirt', bg: 'bg-indigo-950 text-indigo-200 border border-indigo-700/40' };
      case 'bottom':
        return { label: 'Trousers', bg: 'bg-slate-900 text-slate-200 border border-slate-700/40' };
      case 'footwear':
        return { label: 'Footwear', bg: 'bg-amber-950 text-amber-200 border border-amber-700/40' };
      case 'accessory':
        return { label: 'Accessory', bg: 'bg-emerald-950 text-emerald-200 border border-emerald-700/40' };
      case 'dress':
        return { label: 'Gown / Dress', bg: 'bg-[#C5A059] text-slate-950 font-bold border border-[#C5A059]' };
      default:
        return { label: pos || 'Garment', bg: 'bg-black/70 text-white' };
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-950/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="absolute inset-y-0 right-0 max-w-full flex pl-6 sm:pl-10">
        <div className="w-screen max-w-2xl bg-white shadow-2xl flex flex-col border-l border-slate-200">
          {/* Drawer Header */}
          <div className="p-4 sm:p-6 border-b border-slate-800 bg-[#0C0E1E] text-white flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#C5A059] flex items-center justify-center text-slate-950 shadow-xs">
                <StylistIcon size={22} color="#0C0E1E" />
              </div>
              <div>
                <h2 className="font-serif text-lg font-bold text-white flex items-center gap-2">
                  <span>{t('stylist.title')}</span>
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#C5A059]/20 text-[#E2BF70] font-sans font-semibold">
                    Rules-Grounded Engine
                  </span>
                </h2>
                <p className="text-xs text-slate-400 font-light">{t('stylist.subtitle')}</p>
              </div>
            </div>
            <button
              onClick={closeStylist}
              className="w-8 h-8 rounded-full bg-slate-800 text-slate-300 hover:text-white flex items-center justify-center transition-colors"
            >
              ✕
            </button>
          </div>

          {/* Occasion Quick Chips */}
          <div className="px-4 py-2.5 bg-[#FAF9F6] border-b border-slate-200/80 flex items-center gap-2 overflow-x-auto">
            <span className="text-[10px] font-bold text-[#A37E44] uppercase tracking-wider shrink-0">
              Style Prompts:
            </span>
            {['Formal & Wedding', 'Work & Business', 'Evening & Party', 'Casual Weekend'].map((occ) => (
              <button
                key={occ}
                onClick={() => sendPrompt(`Style an outfit for ${occ}`, occ)}
                className="px-3 py-1 rounded-full bg-white border border-slate-200 text-[11px] font-medium text-slate-700 hover:border-[#C5A059] hover:bg-[#FDF8EE] transition-all shrink-0 shadow-2xs"
              >
                {occ}
              </button>
            ))}
          </div>

          {/* Messages & Recommendations Feed */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5 bg-[#FAF9F6]">
            {messages.length === 0 && (
              <div className="text-center py-12 px-4 bg-white rounded-3xl border border-slate-200/80 shadow-2xs">
                <div className="w-14 h-14 rounded-2xl bg-[#FDF8EE] text-[#C5A059] mx-auto flex items-center justify-center mb-3 shadow-xs">
                  <SparkleIcon size={28} color="#C5A059" />
                </div>
                <h4 className="font-serif text-lg font-bold text-[#1B1F3B] mb-1">
                  How can I style you today?
                </h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mb-5 font-light leading-relaxed">
                  Tell me your event, dress code, preferred tones, or budget. I compose verified multi-brand ensembles with strict slot integrity, color harmony, and zero hallucinated pieces.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-left">
                  <button
                    onClick={() => sendPrompt('I need a formal wedding outfit with navy suit and green tie under 500', 'Formal & Wedding', 500)}
                    className="p-3.5 rounded-2xl border border-slate-200 hover:border-[#C5A059] bg-[#FAF9F6] hover:bg-[#FDF8EE] text-xs font-medium text-slate-800 transition-all"
                  >
                    "Formal wedding navy suit with green tie"
                  </button>
                  <button
                    onClick={() => sendPrompt('Find me a champagne silk dress for an evening gala', 'Evening & Party', 600)}
                    className="p-3.5 rounded-2xl border border-slate-200 hover:border-[#C5A059] bg-[#FAF9F6] hover:bg-[#FDF8EE] text-xs font-medium text-slate-800 transition-all"
                  >
                    "Champagne silk dress for an evening gala"
                  </button>
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`max-w-[92%] rounded-2xl p-4 text-xs sm:text-sm shadow-2xs leading-relaxed ${
                    msg.sender === 'user'
                      ? 'bg-[#1B1F3B] text-white rounded-br-none'
                      : 'bg-white border border-slate-200/80 text-slate-800 rounded-bl-none shadow-sm'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    <span>{msg.sender === 'user' ? 'You' : 'CONFIT Senior AI Stylist'}</span>
                  </div>
                  <p className="text-slate-800 font-light leading-relaxed">{msg.content}</p>
                </div>

                {/* Render Recommended Outfits */}
                {msg.recommendations && msg.recommendations.length > 0 && (
                  <div className="w-full mt-3 space-y-4">
                    {msg.recommendations.map((outfit) => (
                      <div
                        key={outfit.id}
                        className="bg-white border border-slate-200 rounded-3xl p-5 shadow-md overflow-hidden space-y-4"
                      >
                        <div className="flex justify-between items-start">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-[10px] font-bold text-[#A37E44] uppercase tracking-wider">
                                {outfit.occasion}
                              </span>
                              <span
                                className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                                  outfit.is_complete !== false
                                    ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                                    : 'bg-amber-100 text-amber-800 border border-amber-300'
                                }`}
                              >
                                {outfit.completeness_label || (outfit.is_complete !== false ? 'Complete Look' : 'Core Look')}
                              </span>
                            </div>
                            <h4 className="font-serif font-bold text-base text-[#1B1F3B]">
                              {outfit.title}
                            </h4>
                          </div>
                          <FitScoreBadge score={outfit.compatibility_score} verdict="Color Harmony" />
                        </div>

                        {/* Garment Grid (Strict Slots) */}
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                          {outfit.items.map((item) => {
                            const badge = getPositionBadge(item.position);
                            return (
                              <div
                                key={item.id}
                                className="group relative bg-[#FAF9F6] border border-slate-200/80 rounded-2xl p-2.5 flex flex-col justify-between"
                              >
                                <div>
                                  <div className="h-32 w-full rounded-xl overflow-hidden bg-white mb-2 relative shadow-2xs">
                                    <img
                                      src={item.image_url}
                                      alt={item.product_title}
                                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                                    />
                                    <span className={`absolute top-1.5 left-1.5 px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider backdrop-blur-xs ${badge.bg}`}>
                                      {badge.label}
                                    </span>
                                  </div>
                                  <div className="flex items-center justify-between gap-1">
                                    <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block truncate">
                                      {item.brand_name}
                                    </span>
                                    {item.color_family && (
                                      <span className="text-[9px] text-slate-500 font-light truncate">
                                        {item.color_family}
                                      </span>
                                    )}
                                  </div>
                                  <span className="text-xs font-bold text-[#1B1F3B] line-clamp-1 block mt-0.5">
                                    {item.product_title}
                                  </span>
                                  {item.role_in_outfit && (
                                    <span className="text-[9px] text-slate-400 block font-light line-clamp-1 mt-0.5">
                                      {item.role_in_outfit}
                                    </span>
                                  )}
                                </div>

                                <div className="flex items-center justify-between pt-2 border-t border-slate-100 mt-2">
                                  <span className="text-xs font-bold text-[#1B1F3B]">
                                    ${item.price.toFixed(2)}
                                  </span>
                                  <button
                                    onClick={() =>
                                      openTryOn({
                                        id: item.product_id,
                                        title: item.product_title,
                                        brand_name: item.brand_name,
                                        thumbnail_url: item.image_url,
                                        base_price: item.price,
                                        category_name: item.category_name,
                                        color_family: item.color_family || 'Coordinated',
                                        style_compatibility_score: outfit.compatibility_score,
                                        ai_fit_score: 95,
                                      } as any)
                                    }
                                    className="px-2 py-1 rounded-lg bg-white border border-slate-200 hover:border-[#C5A059] text-[10px] font-semibold text-slate-700 flex items-center gap-1 shadow-2xs"
                                    title="Try on this item"
                                  >
                                    <TryOnIcon size={11} color="#C5A059" />
                                    <span>Try</span>
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        {/* Total and Action Buttons */}
                        <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                          <div>
                            <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">
                              Ensemble Total ({outfit.items.length} items):
                            </span>
                            <div className="text-base font-serif font-black text-[#1B1F3B]">
                              ${outfit.total_price.toFixed(2)}
                            </div>
                          </div>
                          <button
                            onClick={() => addCompleteLookToCart(outfit)}
                            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-bold shadow-md transition-all"
                          >
                            <BagIcon size={14} color="#FFFFFF" />
                            <span>{outfit.is_complete !== false ? 'Add Complete Look to Bag' : 'Add Core Look to Bag'}</span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {isTyping && (
              <div className="flex items-center gap-2 p-3.5 bg-white border border-slate-200 rounded-2xl w-32 shadow-2xs">
                <span className="w-2 h-2 rounded-full bg-[#C5A059] animate-bounce"></span>
                <span className="w-2 h-2 rounded-full bg-[#C5A059] animate-bounce [animation-delay:0.2s]"></span>
                <span className="w-2 h-2 rounded-full bg-[#C5A059] animate-bounce [animation-delay:0.4s]"></span>
                <span className="text-[10px] font-bold text-slate-400 ml-1">Styling...</span>
              </div>
            )}

            {error && (
              <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-2xl text-xs text-rose-700 flex justify-between items-center">
                <span>{error}</span>
                <button
                  onClick={() => sendPrompt()}
                  className="text-xs font-bold underline ml-2"
                >
                  Retry
                </button>
              </div>
            )}
          </div>

          {/* Drawer Footer Input */}
          <div className="p-4 border-t border-slate-200 bg-white">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                sendPrompt();
              }}
              className="flex items-center gap-2"
            >
              <button
                type="button"
                onClick={simulateVoiceInput}
                className={`p-3 rounded-2xl border transition-all ${
                  isRecording
                    ? 'bg-rose-500 text-white border-rose-600 animate-pulse'
                    : 'bg-slate-50 border-slate-200 text-slate-600 hover:text-[#C5A059] hover:bg-[#FDF8EE]'
                }`}
                title="Hold for Voice Styling"
              >
                🎙️
              </button>

              <input
                type="text"
                value={inputPrompt}
                onChange={(e) => setInputPrompt(e.target.value)}
                placeholder={t('stylist.input_placeholder')}
                className="flex-1 px-4 py-3 rounded-2xl border border-slate-200 focus:outline-none focus:border-[#C5A059] text-xs sm:text-sm bg-[#FAF9F6]"
              />

              <button
                type="submit"
                disabled={!inputPrompt.trim() || isTyping}
                className="px-6 py-3 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-40 text-white text-xs font-bold transition-all shadow-md flex items-center gap-1.5"
              >
                <SparkleIcon size={14} color="#C5A059" />
                <span>Style</span>
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
