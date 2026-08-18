import React, { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useWardrobeViewModel } from '../../viewmodels/useWardrobeViewModel';
import { useUIStore } from '../../stores/uiStore';
import {
  WardrobeIcon,
  SavedLooksIcon,
  GapAnalysisIcon,
  SparkleIcon,
  BagIcon,
  TryOnIcon,
} from '../../components/icons/ConfitIcons';
import { LoadingSpinner, EmptyState, FitScoreBadge } from '../../components/common/CommonComponents';

export const WardrobeView: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const initialTab = searchParams.get('tab') || 'closet';

  const [activeTab, setActiveTab] = useState<'closet' | 'looks' | 'gaps'>(initialTab as any);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newCategory, setNewCategory] = useState('Outerwear');
  const [newColor, setNewColor] = useState('Navy Blue');
  const [newImageUrl, setNewImageUrl] = useState('https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500&auto=format&fit=crop&q=80');

  const {
    items,
    activeCategory,
    setActiveCategory,
    isLoading,
    gapAnalyses,
    isGapLoading,
    fetchGaps,
    isAutoTagging,
    autoTagResult,
    autoTagUpload,
    addNewItem,
    deleteItem,
  } = useWardrobeViewModel();

  const { openTryOn } = useUIStore();

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    addNewItem({
      title: newTitle || 'Custom Wardrobe Item',
      category: newCategory,
      color_name: newColor,
      image_url: newImageUrl,
      wear_frequency: 'regular',
      is_favorite: false,
    });
    setUploadModalOpen(false);
    setNewTitle('');
  };

  return (
    <div className="space-y-8 pb-20">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <WardrobeIcon size={24} color="#1B1F3B" />
            <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
              {t('wardrobe.title')}
            </h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            {t('wardrobe.subtitle')}
          </p>
        </div>

        {/* Tab Selector & Add Piece Button */}
        <div className="flex items-center gap-3">
          <div className="flex bg-slate-100 p-1 rounded-2xl border border-slate-200">
            <button
              onClick={() => setActiveTab('closet')}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                activeTab === 'closet' ? 'bg-white text-[#1B1F3B] shadow-xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {t('nav.my_closet')}
            </button>
            <button
              onClick={() => setActiveTab('looks')}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                activeTab === 'looks' ? 'bg-white text-[#1B1F3B] shadow-xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {t('nav.my_looks')}
            </button>
            <button
              onClick={() => {
                setActiveTab('gaps');
                fetchGaps();
              }}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-1 ${
                activeTab === 'gaps' ? 'bg-white text-[#B8935A] shadow-xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <GapAnalysisIcon size={14} color="#B8935A" />
              <span>{t('nav.gap_analysis')}</span>
            </button>
          </div>

          <button
            onClick={() => setUploadModalOpen(true)}
            className="px-4 py-2.5 rounded-2xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white text-xs font-semibold shadow-sm transition-all"
          >
            + Upload Piece
          </button>
        </div>
      </div>

      {/* TAB 1: My Closet Grid */}
      {activeTab === 'closet' && (
        <div className="space-y-6">
          {/* Category Filter Chips */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {['All', 'Outerwear', 'Tops', 'Bottoms', 'Footwear', 'Accessories'].map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all ${
                  activeCategory === cat
                    ? 'bg-[#1B1F3B] text-white shadow-xs'
                    : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {isLoading ? (
            <LoadingSpinner text="Scanning your wardrobe..." />
          ) : items.length === 0 ? (
            <EmptyState
              title="Your smart closet is waiting"
              description="Upload photos of your existing garments. Our AI will auto-tag fabric, color, and silhouette to suggest new outfit combinations from what you already own."
              actionText="Upload First Piece"
              onAction={() => setUploadModalOpen(true)}
            />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
              {items.map((item) => (
                <div
                  key={item.id}
                  className="bg-white rounded-3xl border border-slate-200 p-3.5 shadow-sm hover:shadow-lg transition-all flex flex-col justify-between group"
                >
                  <div>
                    <div className="h-64 rounded-2xl overflow-hidden bg-slate-100 mb-3 relative">
                      <img src={item.image_url} alt={item.title} className="w-full h-full object-cover" />
                      <button
                        onClick={() => deleteItem(item.id)}
                        className="absolute top-2 right-2 w-7 h-7 rounded-full bg-black/60 hover:bg-rose-600 text-white flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-all"
                        title="Delete from wardrobe"
                      >
                        ✕
                      </button>
                      <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded-full bg-white/90 text-[10px] font-bold text-slate-800">
                        Worn {item.wear_count}x
                      </span>
                    </div>

                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                      {item.brand_name}
                    </span>
                    <h3 className="font-serif text-sm font-bold text-[#1B1F3B] truncate mt-0.5">{item.title}</h3>
                    <p className="text-xs text-slate-500">{item.color_name} · {item.category}</p>

                    {/* AI Tags */}
                    {item.ai_tags && item.ai_tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {item.ai_tags.slice(0, 2).map((t) => (
                          <span key={t} className="text-[9px] px-2 py-0.5 rounded-md bg-[#FDF8EE] text-[#B8935A] font-medium border border-[#B8935A]/20">
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="pt-3 border-t border-slate-100 mt-3 flex items-center gap-2">
                    <button
                      onClick={() => navigate('/builder')}
                      className="w-full py-2 rounded-xl bg-slate-100 hover:bg-[#1B1F3B] hover:text-white text-xs font-semibold text-slate-800 transition-all"
                    >
                      Style in Canvas
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: Saved Outfits */}
      {activeTab === 'looks' && (
        <div className="space-y-6">
          <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                  Saved Curated Ensembles
                </h3>
                <p className="text-xs text-slate-500">Your personalized styling collections</p>
              </div>
              <button
                onClick={() => navigate('/builder')}
                className="px-4 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold shadow-sm"
              >
                + Build New Look
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-[#FAF9F6] rounded-2xl border border-slate-200 p-4 space-y-3">
                <div className="flex justify-between items-start">
                  <div>
                    <span className="text-[10px] font-bold text-[#B8935A] uppercase">Work & Business</span>
                    <h4 className="font-serif text-base font-bold text-[#1B1F3B]">Elevated Metropolitan Boardroom</h4>
                  </div>
                  <FitScoreBadge score={97} verdict="Color Harmony" />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="h-28 rounded-xl overflow-hidden bg-white">
                    <img src="https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=400&auto=format&fit=crop&q=80" alt="Blazer" className="w-full h-full object-cover" />
                  </div>
                  <div className="h-28 rounded-xl overflow-hidden bg-white">
                    <img src="https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=400&auto=format&fit=crop&q=80" alt="Shirt" className="w-full h-full object-cover" />
                  </div>
                  <div className="h-28 rounded-xl overflow-hidden bg-white">
                    <img src="https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=400&auto=format&fit=crop&q=80" alt="Chinos" className="w-full h-full object-cover" />
                  </div>
                </div>
                <div className="flex justify-between items-center pt-2 text-xs font-bold text-[#1B1F3B]">
                  <span>Total: $529.00</span>
                  <button onClick={() => navigate('/builder')} className="text-[#B8935A] hover:underline">
                    Edit in Canvas →
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: Wardrobe Gap Analysis (PDF Feature G4.1) */}
      {activeTab === 'gaps' && (
        <div className="space-y-6">
          <div className="bg-[#FDF8EE] border border-[#B8935A]/30 rounded-3xl p-6">
            <div className="flex items-center gap-2 mb-2">
              <GapAnalysisIcon size={22} color="#B8935A" />
              <h3 className="font-serif text-xl font-bold text-[#1B1F3B]">
                {t('wardrobe.gap_analysis_title')}
              </h3>
            </div>
            <p className="text-xs text-slate-700 max-w-2xl leading-relaxed">
              {t('wardrobe.gap_analysis_desc')}
            </p>
          </div>

          <div className="space-y-4">
            {gapAnalyses.map((gap) => (
              <div
                key={gap.id}
                className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div>
                    <span className="text-[10px] font-bold text-[#B8935A] uppercase tracking-wider">
                      Identified Closet Gap #{gap.id}
                    </span>
                    <h4 className="font-serif text-lg font-bold text-[#1B1F3B]">
                      Missing: {gap.missing_subcategory} ({gap.missing_category})
                    </h4>
                  </div>
                  <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold self-start sm:self-auto">
                    Unlocks +{gap.unlocks_outfit_count} New Outfits
                  </span>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed bg-[#FAF9F6] p-3 rounded-xl border border-slate-100">
                  💡 <strong>AI Analysis:</strong> {gap.rationale}
                </p>

                {/* Recommended Catalog Bridges */}
                <div>
                  <span className="text-xs font-bold text-slate-700 block mb-2">
                    Recommended Catalog Pieces to Bridge this Gap:
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {gap.recommended_products.map((rec) => (
                      <div
                        key={rec.product_id}
                        className="flex items-center gap-3 p-2.5 rounded-2xl bg-white border border-slate-200 hover:border-[#B8935A] transition-all group"
                      >
                        <div className="w-14 h-16 rounded-xl overflow-hidden bg-slate-100 shrink-0">
                          <img src={rec.image_url} alt={rec.title} className="w-full h-full object-cover" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-[9px] font-bold text-slate-400 block truncate">{rec.brand_name}</span>
                          <span className="text-xs font-bold text-[#1B1F3B] block truncate">{rec.title}</span>
                          <span className="text-xs font-bold text-[#B8935A]">${rec.price}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upload Piece Modal with AI Auto-Tagger */}
      {uploadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="w-full max-w-lg bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden">
            <div className="p-5 bg-[#1B1F3B] text-white flex justify-between items-center">
              <h3 className="font-serif text-base font-bold text-white flex items-center gap-2">
                <span>Upload Garment to Smart Wardrobe</span>
              </h3>
              <button onClick={() => setUploadModalOpen(false)} className="text-slate-300 hover:text-white">
                ✕
              </button>
            </div>

            <form onSubmit={handleAddSubmit} className="p-6 space-y-4">
              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1">Garment Title</label>
                <input
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Navy Double-Breasted Blazer"
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#B8935A]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-bold text-slate-800 block mb-1">Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-xs bg-white"
                  >
                    <option value="Outerwear">Outerwear</option>
                    <option value="Tops">Tops & Shirts</option>
                    <option value="Bottoms">Bottoms & Trousers</option>
                    <option value="Footwear">Footwear</option>
                    <option value="Accessories">Accessories</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-bold text-slate-800 block mb-1">Color Family</label>
                  <input
                    type="text"
                    value={newColor}
                    onChange={(e) => setNewColor(e.target.value)}
                    placeholder="e.g. Navy Blue"
                    className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1">Garment Photo URL</label>
                <input
                  type="text"
                  value={newImageUrl}
                  onChange={(e) => setNewImageUrl(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-xs"
                />
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white font-semibold text-xs transition-all shadow-md flex items-center justify-center gap-1.5"
                >
                  <SparkleIcon size={14} color="#B8935A" />
                  <span>Auto-Tag with AI & Save Piece</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
