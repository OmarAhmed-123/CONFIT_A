import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '../../stores/uiStore';
import { useTryOnViewModel } from '../../viewmodels/useTryOnViewModel';
import { VisualSearchIcon, SparkleIcon, BagIcon } from '../icons/ConfitIcons';
import { useCartStore } from '../../stores/cartStore';

export const VisualSearchModal: React.FC = () => {
  const { t } = useTranslation();
  const { isVisualSearchOpen, closeVisualSearch, openTryOn } = useUIStore();
  const { visualSearchLoading, visualSearchResult, runVisualSearch } = useTryOnViewModel();
  const { addItem, openCart } = useCartStore();

  const [inputUrl, setInputUrl] = useState('');
  const [selectedSample, setSelectedSample] = useState('');

  if (!isVisualSearchOpen) return null;

  const samples = [
    { label: 'Navy Wool Blazer', url: 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500&auto=format&fit=crop&q=80' },
    { label: 'Silk Slip Dress', url: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=500&auto=format&fit=crop&q=80' },
    { label: 'Crisp Oxford Shirt', url: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500&auto=format&fit=crop&q=80' },
  ];

  const handleSearch = (imgUrl?: string) => {
    const target = imgUrl || inputUrl || samples[0].url;
    runVisualSearch(target);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-150">
      <div className="w-full max-w-4xl bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="p-4 sm:p-6 border-b border-slate-100 bg-[#1B1F3B] text-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#B8935A] flex items-center justify-center text-slate-950">
              <VisualSearchIcon size={22} color="#1B1F3B" />
            </div>
            <div>
              <h3 className="font-serif text-lg font-bold text-white">
                {t('tryon.visual_search_title')}
              </h3>
              <p className="text-xs text-slate-300">{t('tryon.visual_search_desc')}</p>
            </div>
          </div>
          <button
            onClick={closeVisualSearch}
            className="w-8 h-8 rounded-full bg-slate-800 text-slate-300 hover:text-white flex items-center justify-center transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* Top Input & Sample Inspiration */}
          <div className="space-y-3">
            <label className="text-xs font-bold text-slate-800 block">
              1. Choose Sample Inspiration or Paste Image URL:
            </label>
            <div className="grid grid-cols-3 gap-3">
              {samples.map((s) => (
                <button
                  key={s.label}
                  onClick={() => {
                    setSelectedSample(s.url);
                    handleSearch(s.url);
                  }}
                  className={`flex items-center gap-2.5 p-2 rounded-xl border text-left transition-all ${
                    selectedSample === s.url
                      ? 'border-[#B8935A] bg-[#FDF8EE] ring-1 ring-[#B8935A]'
                      : 'border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <img src={s.url} alt={s.label} className="w-10 h-10 rounded-lg object-cover" />
                  <span className="text-xs font-semibold text-slate-800 line-clamp-1">{s.label}</span>
                </button>
              ))}
            </div>

            <div className="flex gap-2 pt-1">
              <input
                type="text"
                value={inputUrl}
                onChange={(e) => setInputUrl(e.target.value)}
                placeholder="Or paste image URL (Pinterest, Instagram, photoshoot)..."
                className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#B8935A]"
              />
              <button
                onClick={() => handleSearch()}
                disabled={visualSearchLoading}
                className="px-5 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white text-xs font-semibold shadow-sm transition-all"
              >
                {visualSearchLoading ? 'Analyzing...' : 'Search Style'}
              </button>
            </div>
          </div>

          {/* Vision Detection Result */}
          {visualSearchResult && (
            <div className="space-y-4 pt-2 border-t border-slate-100">
              {visualSearchResult.analysis_available ? (
                <div className="flex items-center gap-2 bg-[#FDF8EE] border border-[#B8935A]/30 p-3 rounded-xl text-xs text-slate-800">
                  <SparkleIcon size={16} color="#B8935A" />
                  <span>
                    Detected: <strong className="text-[#1B1F3B]">{visualSearchResult.detected_category}</strong> in{' '}
                    <strong className="text-[#1B1F3B]">{visualSearchResult.detected_color}</strong> · Style: {visualSearchResult.detected_style}
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 p-3 rounded-xl text-xs text-slate-600">
                  <SparkleIcon size={16} color="#94A3B8" />
                  <span>
                    Vision analysis is unavailable right now — showing catalog matches without image detection.
                  </span>
                </div>
              )}

              {/* Match Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                {visualSearchResult.matches.map((match) => (
                  <div
                    key={match.product_id}
                    className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm hover:shadow-md transition-all flex flex-col justify-between group"
                  >
                    <div>
                      <div className="h-44 rounded-xl overflow-hidden bg-slate-100 mb-2 relative">
                        <img
                          src={match.image_url}
                          alt={match.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        />
                        <span className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-[#1B1F3B]/80 backdrop-blur-sm text-[10px] font-bold text-[#B8935A]">
                          {match.similarity_score}% Match
                        </span>
                        <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-white/90 text-[10px] font-bold text-slate-800">
                          {match.match_type}
                        </span>
                      </div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                        {match.brand_name}
                      </span>
                      <h5 className="text-xs font-bold text-[#1B1F3B] line-clamp-1 mb-1">{match.title}</h5>
                      <span className="text-sm font-bold text-[#1B1F3B]">${match.price}</span>
                    </div>

                    <button
                      onClick={() => {
                        closeVisualSearch();
                        openTryOn({
                          id: match.product_id,
                          brand_id: 1,
                          brand_name: match.brand_name,
                          category_id: 1,
                          category_name: 'Apparel',
                          title: match.title,
                          title_ar: match.title,
                          slug: 'match-' + match.product_id,
                          base_price: match.price,
                          currency: 'USD',
                          thumbnail_url: match.image_url,
                          color_family: match.detected_color,
                          dominant_hex: '#1B1F3B',
                          style_tags: ['Matched'],
                          occasion_tags: ['Versatile'],
                          rating: 4.8,
                          style_compatibility_score: 95,
                          ai_fit_score: 95,
                          is_featured: false,
                        });
                      }}
                      className="mt-3 w-full py-2 rounded-xl bg-slate-100 hover:bg-[#1B1F3B] hover:text-white text-xs font-semibold text-slate-800 transition-all flex items-center justify-center gap-1.5"
                    >
                      <span>Try On This Match</span>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
