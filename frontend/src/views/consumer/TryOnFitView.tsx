import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useCatalogViewModel } from '../../viewmodels/useCatalogViewModel';
import { useUIStore } from '../../stores/uiStore';
import { TryOnIcon, RulerIcon, VisualSearchIcon, SparkleIcon } from '../../components/icons/ConfitIcons';
import { FitScoreBadge } from '../../components/common/CommonComponents';
import { CameraScanModal } from '../../components/tryon/CameraScanModal';
import { CircularGalleryShowcase } from '../../components/showcase/DesignShowcases';

export const TryOnFitView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { products, isLoading } = useCatalogViewModel();
  const { openTryOn, openRuler, openVisualSearch } = useUIStore();

  const [activeTab, setActiveTab] = useState<'vton' | 'scan' | 'ruler' | 'visual'>('vton');
  const [isCameraScanOpen, setIsCameraScanOpen] = useState(false);

  return (
    <div className="space-y-10 pb-20">
      <CircularGalleryShowcase
        tone="tryon"
        compact
        eyebrow="Fit Preview Gallery"
        title="Rotate through try-on-ready styling contexts"
        description="The 3D gallery gives the fit studio a visual bridge between inspiration, garment selection, visual search, and no-photo measurements."
      />
      {/* Header */}
      <div className="bg-gradient-to-r from-[#1B1F3B] to-[#2A3C78] rounded-3xl text-white p-8 sm:p-12 shadow-xl border border-slate-800">
        <div className="max-w-2xl space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#C5A059]/20 border border-[#C5A059]/40 text-[#E2BF70] text-xs font-semibold uppercase tracking-wider">
            <SparkleIcon size={14} color="#E2BF70" />
            <span>Group 3: Virtual Visualization & Fit Studio</span>
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold leading-tight">
            Virtual Visualization & Precision Fit Studio
          </h1>
          <p className="text-xs sm:text-sm text-slate-300 font-light leading-relaxed">
            CONFIT bridges the imagination gap. See garments seamlessly draped on your body silhouette with diffusion warping, or evaluate size metrics with zero photo uploads.
          </p>
        </div>
      </div>

      {/* Feature Selector Cards (4 columns) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Virtual Try-On */}
        <div
          onClick={() => setActiveTab('vton')}
          className={`p-5 rounded-3xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
            activeTab === 'vton'
              ? 'border-[#C5A059] bg-[#FDF8EE] shadow-md'
              : 'border-slate-200 bg-white hover:border-slate-300'
          }`}
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-[#1B1F3B] flex items-center justify-center text-white">
              <TryOnIcon size={22} color="#C5A059" isAi={true} />
            </div>
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{t('nav.virtual_tryon')}</h3>
            <p className="text-xs text-slate-500 font-light">
              Photorealistic fabric segmentation and silhouette drape.
            </p>
          </div>
          <span className="text-xs font-bold text-[#A37E44] mt-4 block">Select Garment →</span>
        </div>

        {/* 2. Live Body Scan */}
        <div
          onClick={() => {
            setActiveTab('scan');
            setIsCameraScanOpen(true);
          }}
          className={`p-5 rounded-3xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
            activeTab === 'scan'
              ? 'border-[#C5A059] bg-[#FDF8EE] shadow-md'
              : 'border-slate-200 bg-white hover:border-slate-300'
          }`}
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-[#C5A059] flex items-center justify-center text-slate-950 shadow-xs">
              <SparkleIcon size={22} color="#0C0E1E" />
            </div>
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">Live Camera Body Scan</h3>
            <p className="text-xs text-slate-500 font-light">
              On-device vision posture scan & proportion estimation.
            </p>
          </div>
          <span className="text-xs font-bold text-[#A37E44] mt-4 block">Launch Body Scan →</span>
        </div>

        {/* 3. No-Photo Fit Finder — navigates to the dedicated /fit engine */}
        <div
          onClick={() => navigate('/fit')}
          className={`p-5 rounded-3xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
            activeTab === 'ruler'
              ? 'border-[#1B1F3B] bg-[#FAF9F6] shadow-md'
              : 'border-slate-200 bg-white hover:border-slate-300'
          }`}
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-900">
              <RulerIcon size={22} color="#1B1F3B" />
            </div>
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{t('nav.no_photo_fit')}</h3>
            <p className="text-xs text-slate-500 font-light">
              Zero-photo measurement calculator with brand ease curves.
            </p>
          </div>
          <span className="text-xs font-bold text-slate-800 mt-4 block">Open Fit Finder →</span>
        </div>

        {/* 4. Visual Search */}
        <div
          onClick={() => {
            setActiveTab('visual');
            openVisualSearch();
          }}
          className={`p-5 rounded-3xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
            activeTab === 'visual'
              ? 'border-[#C5A059] bg-[#FDF8EE] shadow-md'
              : 'border-slate-200 bg-white hover:border-slate-300'
          }`}
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-[#FDF8EE] flex items-center justify-center text-[#A37E44]">
              <VisualSearchIcon size={22} color="#C5A059" />
            </div>
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{t('nav.visual_search')}</h3>
            <p className="text-xs text-slate-500 font-light">
              Upload moodboard screenshot to find matching catalog pieces.
            </p>
          </div>
          <span className="text-xs font-bold text-[#A37E44] mt-4 block">Match Outfit →</span>
        </div>
      </div>

      {/* Selectable Garments for Try-On */}
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-serif text-xl font-bold text-[#1B1F3B]">
            Select Garment from Multi-Brand Catalog:
          </h3>
          <span className="text-xs text-slate-400 font-light">
            {isLoading ? 'Loading catalog styles…' : `Showing ${products.length} styles from the live catalog`}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {products.map((p) => (
            <div
              key={p.id}
              className="bg-white rounded-3xl border border-slate-200 p-3.5 shadow-sm hover:shadow-lg transition-all flex flex-col justify-between"
            >
              <div>
                <div className="h-60 rounded-2xl overflow-hidden bg-slate-100 mb-3 relative">
                  <img src={p.thumbnail_url} alt={p.title} className="w-full h-full object-cover" />
                  <div className="absolute top-2 left-2">
                    <FitScoreBadge score={p.style_compatibility_score} label="Style Match" verdict="catalog score" />
                  </div>
                </div>
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{p.brand_name}</span>
                <h4 className="font-serif text-sm font-bold text-[#1B1F3B] truncate">{p.title}</h4>
                <div className="text-sm font-bold text-[#1B1F3B] mt-1">${p.base_price.toFixed(2)}</div>
              </div>

              <div className="pt-3 border-t border-slate-100 mt-3 grid grid-cols-2 gap-2">
                <button
                  onClick={() => openRuler(p)}
                  className="py-2 px-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-[11px] font-semibold text-slate-700 flex items-center justify-center gap-1"
                >
                  <RulerIcon size={13} />
                  <span>Ruler</span>
                </button>
                <button
                  onClick={() => openTryOn(p)}
                  className="py-2 px-2 rounded-xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white text-[11px] font-semibold flex items-center justify-center gap-1 shadow-sm"
                >
                  <TryOnIcon size={13} color="#C5A059" />
                  <span>Try On</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Live Camera Scan Modal */}
      <CameraScanModal
        isOpen={isCameraScanOpen}
        onClose={() => setIsCameraScanOpen(false)}
        onApplyMeasurements={(measurements) => {
          if (products.length > 0) {
            openTryOn(products[0]);
          }
        }}
      />
    </div>
  );
};
