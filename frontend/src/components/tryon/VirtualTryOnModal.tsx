import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '../../stores/uiStore';
import { useTryOnViewModel } from '../../viewmodels/useTryOnViewModel';
import { useCatalogViewModel } from '../../viewmodels/useCatalogViewModel';
import { Product } from '../../models';
import {
  TryOnIcon,
  SparkleIcon,
  BagIcon,
  OutfitBuilderIcon,
  ShieldIcon,
  LockIcon,
} from '../icons/ConfitIcons';
import { FitScoreBadge } from '../common/CommonComponents';
import { CameraScanModal } from './CameraScanModal';

export const VirtualTryOnModal: React.FC = () => {
  const { t } = useTranslation();
  const { tryOnProduct, closeTryOn } = useUIStore();
  const { products } = useCatalogViewModel();

  const {
    tryOnStatus,
    motionStatus,
    isRendering,
    isAnimating,
    multiTryOnResult,
    animationResult,
    activeKeyframeIndex,
    setActiveKeyframeIndex,
    outputAspect,
    setOutputAspect,
    activePreviewTab,
    setActivePreviewTab,
    selectedAvatar,
    setSelectedAvatar,
    uploadedUserImage,
    setUploadedUserImage,
    appliedGarments,
    isBeforeAfterActive,
    setIsBeforeAfterActive,
    splitSliderPosition,
    setSplitSliderPosition,
    totalPrice,
    dynamicFitScore,
    addGarmentToCanvas,
    removeGarmentFromCanvas,
    clearCanvas,
    undoLastAction,
    addAllDressedToCart,
    runTryOn,
    runAnimatedTryOn,
  } = useTryOnViewModel(tryOnProduct);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isCameraScanOpen, setIsCameraScanOpen] = useState(false);
  const [activeCategoryFilter, setActiveCategoryFilter] = useState<string>('All');
  const [isDragOver, setIsDragOver] = useState(false);

  if (!tryOnProduct) return null;

  const avatars = [
    {
      id: 'avatar_athletic_m',
      name: 'Athletic Male',
      img: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600&auto=format&fit=crop&q=80',
      gender: 'male',
    },
    {
      id: 'avatar_hourglass_f',
      name: 'Hourglass Female',
      img: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600&auto=format&fit=crop&q=80',
      gender: 'female',
    },
    {
      id: 'avatar_curvy_f',
      name: 'Curvy Female',
      img: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=600&auto=format&fit=crop&q=80',
      gender: 'female',
    },
    {
      id: 'avatar_tall_m',
      name: 'Tall Structured',
      img: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=600&auto=format&fit=crop&q=80',
      gender: 'male',
    },
  ];

  const currentAvatarObj = avatars.find((a) => a.id === selectedAvatar) || avatars[0];
  const activeBaseImage = uploadedUserImage || currentAvatarObj.img;
  const appliedList = Object.entries(appliedGarments);
  const renderedResultImage = multiTryOnResult?.rendered_result_url || null;
  const activeDisplayImage = appliedList.length > 0 && renderedResultImage ? renderedResultImage : activeBaseImage;

  // Temporary delivery (product requirement): the generated try-on image is
  // returned in the authenticated response (data URL) and is NOT stored by
  // the server. The download is performed client-side (Blob) so no durable
  // copy is ever created — the bytes exist only in the user's browser.
  const handleDownloadRenderedResult = async () => {
    const src = renderedResultImage || activeDisplayImage;
    if (!src) return;
    try {
      let href = src;
      if (src.startsWith('data:')) {
        const res = await fetch(src);
        const blob = await res.blob();
        href = URL.createObjectURL(blob);
      }
      const ext = src.includes('image/jpeg') ? 'jpg' : src.includes('image/webp') ? 'webp' : 'png';
      const a = document.createElement('a');
      a.href = href;
      a.download = `confit-try-on-${Date.now()}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (href.startsWith('blob:')) URL.revokeObjectURL(href);
    } catch (err) {
      console.warn('Try-on result download failed', err);
    }
  };

  // Filter shelf products
  const filteredProducts = products.filter((p) => {
    if (activeCategoryFilter === 'All') return true;
    const cat = (p.category_name || '').toLowerCase();
    const title = (p.title || '').toLowerCase();
    if (activeCategoryFilter === 'Outerwear') return cat.includes('outer') || title.includes('blazer') || title.includes('jacket') || title.includes('coat');
    if (activeCategoryFilter === 'Tops') return cat.includes('top') || cat.includes('shirt') || title.includes('sweater') || title.includes('knit');
    if (activeCategoryFilter === 'Bottoms') return cat.includes('bottom') || title.includes('trouser') || title.includes('chino') || title.includes('denim');
    if (activeCategoryFilter === 'Dresses') return cat.includes('dress') || title.includes('gown');
    if (activeCategoryFilter === 'Footwear') return cat.includes('footwear') || cat.includes('shoe') || title.includes('oxford') || title.includes('loafer') || title.includes('sandal') || title.includes('sneaker');
    if (activeCategoryFilter === 'Accessories') return cat.includes('access') || title.includes('tie') || title.includes('pocket') || title.includes('belt') || title.includes('clutch') || title.includes('watch');
    return true;
  });

  const handleDragStart = (e: React.DragEvent, p: Product) => {
    e.dataTransfer.setData('application/json', JSON.stringify(p));
    e.dataTransfer.effectAllowed = 'copy';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDropOnCanvas = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    try {
      const dataStr = e.dataTransfer.getData('application/json');
      if (dataStr) {
        const prod = JSON.parse(dataStr) as Product;
        addGarmentToCanvas(prod);
      }
    } catch (err) {
      console.warn('Drop error:', err);
    }
  };

  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const dataUrl = event.target?.result as string;
      setUploadedUserImage(dataUrl);
      // Pass the fresh data URL explicitly: state above is not committed
      // yet in this tick, and the render must use the photo the user just
      // uploaded — never the previous reference (avatar or older photo).
      runTryOn({ userImageUrl: dataUrl });
    };
    reader.readAsDataURL(file);
  };

  // Primary active garment for rendering
  const primaryGarment = appliedList.length > 0 ? appliedList[0][1] : null;

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in duration-150">
        <div className="w-full max-w-6xl bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden max-h-[96vh] flex flex-col">
          {/* Header */}
          <div className="p-4 sm:p-5 bg-[#0C0E1E] text-white flex justify-between items-center border-b border-slate-800 shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#C5A059] flex items-center justify-center text-slate-950 shadow-xs">
                <TryOnIcon size={22} color="#0C0E1E" isAi={true} />
              </div>
              <div>
                <h3 className="font-serif text-base sm:text-lg font-bold text-white flex items-center gap-2">
                  <span>Dynamic Virtual Dressing Studio</span>
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#C5A059]/20 text-[#E2BF70] font-sans font-semibold">
                    Multi-Layer Dressing Engine
                  </span>
                </h3>
                <p className="text-xs text-slate-400 font-light hidden sm:block">
                  Applies the selected garments to the person in your photo.
                </p>
              </div>
            </div>
            <button
              onClick={closeTryOn}
              className="w-8 h-8 rounded-full bg-slate-800 text-slate-300 hover:text-white flex items-center justify-center transition-colors"
            >
              ✕
            </button>
          </div>

          {/* Main 2-Column Split */}
          <div className="flex-1 overflow-y-auto grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-slate-200">
            {/* LEFT: Dynamic Dressing Canvas & Controls (7 cols) */}
            <div className="lg:col-span-7 p-4 sm:p-6 bg-[#FAF9F6] flex flex-col justify-between space-y-4">
              {/* Top Bar: Subject Selector & Mode Switchers */}
              <div className="space-y-3">
                <div className="flex flex-wrap justify-between items-center gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-[#1B1F3B]">Person Reference:</span>
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 hover:border-[#C5A059] text-slate-700 text-xs font-semibold flex items-center gap-1 shadow-2xs transition-all"
                    >
                      <span>📸 Upload Photo</span>
                    </button>
                    <button
                      onClick={() => setIsCameraScanOpen(true)}
                      className="px-3 py-1.5 rounded-xl bg-[#FDF8EE] border border-[#C5A059]/40 hover:bg-[#C5A059] hover:text-slate-950 text-[#A37E44] text-xs font-semibold flex items-center gap-1 shadow-2xs transition-all"
                    >
                      <span>🎥 Live Scan</span>
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      onChange={handlePhotoUpload}
                      className="hidden"
                    />
                  </div>

                  {/* Mode Selector Tabs: Static / Layer Assembly / Compare */}
                  <div className="flex items-center bg-white p-1 rounded-xl border border-slate-200 text-xs font-bold shadow-2xs">
                    <button
                      onClick={() => {
                        setActivePreviewTab('static');
                        setIsBeforeAfterActive(false);
                      }}
                      className={`px-3 py-1 rounded-lg transition-all ${
                        activePreviewTab === 'static' && !isBeforeAfterActive
                          ? 'bg-[#1B1F3B] text-white shadow-xs'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      Dressing Canvas
                    </button>
                    <button
                      onClick={() => {
                        setActivePreviewTab('animation');
                        setIsBeforeAfterActive(false);
                        if (!animationResult) runAnimatedTryOn();
                      }}
                      className={`px-3 py-1 rounded-lg transition-all flex items-center gap-1 ${
                        activePreviewTab === 'animation' && !isBeforeAfterActive
                          ? 'bg-[#1B1F3B] text-[#E2BF70] shadow-xs'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <SparkleIcon size={12} color="#C5A059" />
                      <span>Layer Assembly</span>
                    </button>
                    <button
                      onClick={() => {
                        setIsBeforeAfterActive(!isBeforeAfterActive);
                        setActivePreviewTab('static');
                      }}
                      className={`px-3 py-1 rounded-lg transition-all ${
                        isBeforeAfterActive ? 'bg-[#C5A059] text-slate-950 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      Before / After Split
                    </button>
                  </div>
                </div>

                {/* Avatar Strip */}
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {avatars.map((av) => (
                    <button
                      key={av.id}
                      onClick={() => {
                        setSelectedAvatar(av.id);
                        setUploadedUserImage(null);
                        // Fresh values for the same-tick render: the new
                        // avatar and the cleared photo (see overrides
                        // contract on runTryOn in useTryOnViewModel).
                        runTryOn({ userImageUrl: null, avatarId: av.id });
                      }}
                      className={`flex items-center gap-2 p-1.5 pr-3 rounded-xl border text-left transition-all shrink-0 ${
                        selectedAvatar === av.id && !uploadedUserImage
                          ? 'border-[#C5A059] bg-white ring-2 ring-[#C5A059]/30 shadow-2xs'
                          : 'border-slate-200 bg-white/70 hover:bg-white text-slate-600'
                      }`}
                    >
                      <img src={av.img} alt={av.name} className="w-7 h-7 rounded-lg object-cover" />
                      <span className="text-[11px] font-semibold">{av.name}</span>
                    </button>
                  ))}
                  {uploadedUserImage && (
                    <div className="flex items-center gap-2 p-1.5 pr-3 rounded-xl border border-[#C5A059] bg-[#FDF8EE] text-[#1B1F3B] text-[11px] font-bold shrink-0 shadow-2xs">
                      <img src={uploadedUserImage} alt="User" className="w-7 h-7 rounded-lg object-cover" />
                      <span>Custom Photo Active</span>
                      <button
                        onClick={() => setUploadedUserImage(null)}
                        className="text-xs hover:text-rose-600 ml-1"
                        title="Remove photo"
                      >
                        ✕
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Main Interactive Stage / Person Canvas */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDropOnCanvas}
                className={`relative h-[400px] sm:h-[480px] rounded-3xl overflow-hidden bg-slate-950 border-2 transition-all flex items-center justify-center shadow-inner ${
                  isDragOver ? 'border-[#C5A059] ring-4 ring-[#C5A059]/30 bg-slate-900' : 'border-slate-300'
                }`}
              >
                {/* 1. Before / After Split Slider Mode */}
                {isBeforeAfterActive ? (
                  <div className="relative w-full h-full">
                    {/* Underlying Dressed State (AI-Generated Image) */}
                    <div className="relative w-full h-full">
                      <img
                        src={activeDisplayImage}
                        alt="Dressed State"
                        className="w-full h-full object-cover select-none"
                      />
                    </div>

                    {/* Left Clipped Original Image (Undressed Reference) */}
                    <div
                      className="absolute inset-0 overflow-hidden"
                      style={{ clipPath: `polygon(0 0, ${splitSliderPosition}% 0, ${splitSliderPosition}% 100%, 0 100%)` }}
                    >
                      <img
                        src={activeBaseImage}
                        alt="Original Reference"
                        className="w-full h-full object-cover select-none"
                      />
                    </div>

                    {/* Divider Line & Draggable Handle */}
                    <div
                      className="absolute top-0 bottom-0 w-1 bg-[#C5A059] shadow-[0_0_12px_#C5A059] cursor-ew-resize flex items-center justify-center pointer-events-none"
                      style={{ left: `${splitSliderPosition}%` }}
                    >
                      <div className="w-7 h-7 rounded-full bg-[#C5A059] text-slate-950 text-xs font-black flex items-center justify-center shadow-xl border-2 border-white">
                        ↔
                      </div>
                    </div>

                    {/* Interactive Slider Input */}
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={splitSliderPosition}
                      onChange={(e) => setSplitSliderPosition(Number(e.target.value))}
                      className="absolute inset-x-4 bottom-4 opacity-80 hover:opacity-100 accent-[#C5A059] z-20 cursor-ew-resize"
                    />

                    <span className="absolute top-3 left-3 px-3 py-1 rounded-full bg-slate-950/85 backdrop-blur-md text-white text-[10px] font-bold border border-white/20 z-10">
                      Original ({splitSliderPosition}%) ⟷ Dressed ({100 - splitSliderPosition}%)
                    </span>
                  </div>
                ) : activePreviewTab === 'animation' && animationResult ? (
                  /* 2. Layer Assembly Sequence Player */
                  <div className="relative w-full h-full flex flex-col justify-between p-4 bg-slate-950">
                    <img
                      src={animationResult.keyframes_sequence[activeKeyframeIndex]?.image_url || activeDisplayImage}
                      alt="Animation Frame"
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-transparent to-black/40 pointer-events-none" />

                    {/* Top Aspect & Animation Status */}
                    <div className="relative z-10 flex justify-between items-center">
                      <span className="px-2.5 py-1 rounded-full bg-[#C5A059] text-slate-950 text-[10px] font-bold">
                        🎬 Layer Assembly Sequence
                      </span>
                      <div className="flex gap-1 bg-black/60 p-0.5 rounded-lg border border-white/10 text-[9px] text-white">
                        {(['9:16', '4:5', '1:1'] as const).map((asp) => (
                          <button
                            key={asp}
                            onClick={() => setOutputAspect(asp)}
                            className={`px-1.5 py-0.5 rounded ${outputAspect === asp ? 'bg-[#C5A059] text-slate-950 font-bold' : 'hover:bg-white/20'}`}
                          >
                            {asp}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Bottom Step-by-Step Motion Timeline */}
                    <div className="relative z-10 space-y-2 bg-black/75 backdrop-blur-md p-3 rounded-2xl border border-white/10">
                      <div className="flex justify-between items-center text-xs text-white">
                        <span className="font-bold text-[#E2BF70]">
                          Step {activeKeyframeIndex + 1} of {animationResult.keyframes_sequence.length}:
                        </span>
                        <span className="text-[11px] text-slate-300">
                          {animationResult.keyframes_sequence[activeKeyframeIndex]?.status}
                        </span>
                      </div>
                      <div className="flex gap-1.5">
                        {animationResult.keyframes_sequence.map((kf, idx) => (
                          <button
                            key={kf.step}
                            onClick={() => setActiveKeyframeIndex(idx)}
                            className={`flex-1 h-1.5 rounded-full transition-all ${
                              activeKeyframeIndex === idx ? 'bg-[#C5A059]' : 'bg-white/20 hover:bg-white/40'
                            }`}
                            title={kf.product_title}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  /* 3. Static High-Fidelity Generative Try-On Stage */
                  <div className="relative w-full h-full flex items-center justify-center">
                    <img
                      src={activeDisplayImage}
                      alt="Try-On Canvas"
                      className="w-full h-full object-cover select-none"
                    />

                    {/* Top Status & Fit Accuracy (Dynamic calculations) */}
                    <div className="absolute top-3 left-3 flex flex-col gap-1.5 pointer-events-none">
                      <FitScoreBadge
                        score={dynamicFitScore}
                        verdict="Style Compatibility"
                      />
                      <span className="px-2.5 py-0.5 rounded-full bg-slate-950/75 backdrop-blur-md text-[9px] font-medium text-slate-300 border border-white/10 w-fit">
                        {appliedList.length === 0
                          ? 'Base Silhouette (Ready for Styling)'
                          : isRendering
                            ? `Rendering ${appliedList.length} Garment Layer${appliedList.length === 1 ? '' : 's'}…`
                            : `Dressed with ${appliedList.length} Garment Layer${appliedList.length === 1 ? '' : 's'}`}
                      </span>
                    </div>

                    {/* Download — the server retains no copy of the generated
                        image (temporary delivery); this saves it client-side */}
                    {renderedResultImage && !isRendering && (
                      <button
                        onClick={handleDownloadRenderedResult}
                        className="absolute bottom-3 right-3 px-3 py-1.5 rounded-full bg-[#C5A059] text-slate-950 text-[11px] font-bold shadow-lg hover:brightness-110 active:scale-95 transition-all"
                      >
                        ⬇ Download Result
                      </button>
                    )}

                    {/* Active Rendering Overlay */}
                    {isRendering && (
                      <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-xs flex flex-col items-center justify-center p-6 text-center space-y-3 animate-in fade-in duration-150">
                        <div className="w-10 h-10 border-3 border-[#C5A059] border-t-transparent rounded-full animate-spin"></div>
                        <div>
                          <h4 className="font-serif text-sm font-bold text-white">
                            Synthesizing Virtual Try-On Layer...
                          </h4>
                          <p className="text-[11px] text-slate-300 font-light mt-0.5">
                            Draping garment with 100% facial identity preservation.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Dressed Layers Strip & Reorder List */}
              <div className="space-y-2 bg-white p-3.5 rounded-2xl border border-slate-200 shadow-2xs">
                <div className="flex justify-between items-center pb-1 border-b border-slate-100">
                  <span className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                    Dressed Garment Layers ({appliedList.length} items):
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={undoLastAction}
                      className="text-[11px] font-semibold text-slate-500 hover:text-slate-900"
                    >
                      ↩ Undo
                    </button>
                    <button
                      onClick={clearCanvas}
                      className="text-[11px] font-semibold text-rose-600 hover:underline"
                    >
                      Clear All
                    </button>
                  </div>
                </div>

                {appliedList.length === 0 ? (
                  <p className="text-xs text-slate-400 font-light py-1 text-center">
                    Drag any garment from the right catalog shelf or tap "+ Dress" to style this person.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {appliedList.map(([slot, item]) => (
                      <div
                        key={slot}
                        className="inline-flex items-center gap-2 bg-[#FAF9F6] border border-slate-200 rounded-xl px-2.5 py-1 text-xs"
                      >
                        <img src={item.thumbnail_url} alt={item.title} className="w-5 h-5 rounded object-cover" />
                        <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                          {slot.replace('_', ' ')}
                        </span>
                        <span className="font-semibold text-slate-800 line-clamp-1 max-w-[120px]">{item.title}</span>
                        <span className="font-bold text-[#A37E44]">${item.base_price}</span>
                        <button
                          onClick={() => removeGarmentFromCanvas(slot)}
                          className="w-4 h-4 rounded-full bg-slate-200 hover:bg-rose-500 hover:text-white text-slate-600 flex items-center justify-center text-[9px] transition-colors"
                          title="Remove item"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Bottom Action Footer */}
              <div className="flex flex-col sm:flex-row justify-between items-center gap-3 pt-2">
                <div>
                  <span className="text-[10px] text-slate-400 block">Total Dressed Look:</span>
                  <span className="font-serif text-lg font-black text-[#1B1F3B]">
                    ${totalPrice.toFixed(2)}
                  </span>
                </div>
                <div className="flex gap-2 w-full sm:w-auto">
                  <button
                    onClick={runAnimatedTryOn}
                    disabled={isAnimating || appliedList.length === 0}
                    className="flex-1 sm:flex-none px-4 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-40 text-[#E2BF70] font-bold text-xs shadow-md transition-all flex items-center justify-center gap-1.5"
                  >
                    <SparkleIcon size={14} color="#C5A059" />
                    <span>{isAnimating ? 'Synthesizing...' : 'Play Layer Sequence'}</span>
                  </button>
                  <button
                    onClick={addAllDressedToCart}
                    disabled={appliedList.length === 0}
                    className="flex-1 sm:flex-none px-6 py-2.5 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] disabled:opacity-40 text-slate-950 font-bold text-xs shadow-md transition-all flex items-center justify-center gap-1.5"
                  >
                    <BagIcon size={14} color="#0C0E1E" />
                    <span>Add {appliedList.length} Items to Bag</span>
                  </button>
                </div>
              </div>
            </div>

            {/* RIGHT: Multi-Brand Draggable Catalog Shelf (5 cols) */}
            <div className="lg:col-span-5 p-4 sm:p-6 bg-white flex flex-col justify-between space-y-4">
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1.5">
                    <OutfitBuilderIcon size={18} color="#1B1F3B" />
                    <h4 className="font-serif text-sm sm:text-base font-bold text-[#1B1F3B]">
                      Multi-Brand Catalog Shelf
                    </h4>
                  </div>
                  <span className="text-[10px] text-slate-400 font-light">
                    Drag card or tap "+ Dress"
                  </span>
                </div>

                {/* Category Tabs */}
                <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-none">
                  {['All', 'Outerwear', 'Tops', 'Bottoms', 'Dresses', 'Footwear', 'Accessories'].map((cat) => (
                    <button
                      key={cat}
                      onClick={() => setActiveCategoryFilter(cat)}
                      className={`px-3 py-1 rounded-full text-xs font-semibold whitespace-nowrap transition-all ${
                        activeCategoryFilter === cat
                          ? 'bg-[#1B1F3B] text-white shadow-2xs'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>

                {/* Product Card Grid */}
                <div className="grid grid-cols-2 gap-3 max-h-[500px] overflow-y-auto pr-1">
                  {filteredProducts.map((p) => {
                    const isAlreadyDressed = Object.values(appliedGarments).some((g) => g.id === p.id);
                    return (
                      <div
                        key={p.id}
                        draggable={true}
                        onDragStart={(e) => handleDragStart(e, p)}
                        className={`p-3 rounded-2xl border transition-all flex flex-col justify-between cursor-grab active:cursor-grabbing group select-none ${
                          isAlreadyDressed
                            ? 'border-[#C5A059] bg-[#FDF8EE] ring-1 ring-[#C5A059]'
                            : 'border-slate-200 bg-[#FAF9F6] hover:border-[#C5A059] hover:shadow-sm'
                        }`}
                      >
                        <div>
                          <div className="aspect-[3/4] rounded-xl overflow-hidden bg-white mb-2 relative shadow-2xs">
                            <img
                              src={p.thumbnail_url}
                              alt={p.title}
                              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                            />
                            <span className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-black/60 text-[9px] text-white font-medium capitalize">
                              {p.category_name}
                            </span>
                            {isAlreadyDressed && (
                              <span className="absolute bottom-1 right-1 px-2 py-0.5 rounded-full bg-emerald-600 text-[9px] text-white font-bold shadow-xs">
                                ✓ In Outfit
                              </span>
                            )}
                          </div>
                          <span className="text-[9px] text-slate-400 font-bold uppercase tracking-wider block truncate">
                            {p.brand_name}
                          </span>
                          <h5 className="font-serif text-xs font-bold text-[#1B1F3B] line-clamp-1 mt-0.5">
                            {p.title}
                          </h5>
                          <span className="text-xs font-bold text-[#A37E44] mt-0.5 block">
                            ${p.base_price}
                          </span>
                        </div>

                        {/* Engine capability (fashn_vton_segfee): the VTON
                            engine renders tops / outerwear / bottoms /
                            dresses only. Footwear & accessories are catalog
                            items the engine cannot try on — communicate it
                            in the UI instead of a wasted 70 s render + 422
                            (the API also rejects them upfront). */}
                        {['Footwear', 'Accessories'].includes(p.category_name) && !isAlreadyDressed ? (
                          <button
                            type="button"
                            disabled
                            title="The virtual try-on engine (fashn_vton_segfee) renders tops, outerwear, bottoms and dresses. Footwear and accessories are not supported yet."
                            className="mt-2.5 w-full py-1.5 rounded-xl text-[11px] font-bold transition-all flex items-center justify-center gap-1 bg-slate-100 text-slate-400 cursor-not-allowed"
                          >
                            ⚠ Not in Virtual Try-On yet
                          </button>
                        ) : (
                        <button
                          type="button"
                          onClick={() => {
                            if (isAlreadyDressed) {
                              const slot = Object.keys(appliedGarments).find((k) => appliedGarments[k].id === p.id);
                              if (slot) removeGarmentFromCanvas(slot);
                            } else {
                              addGarmentToCanvas(p);
                            }
                          }}
                          className={`mt-2.5 w-full py-1.5 rounded-xl text-[11px] font-bold transition-all flex items-center justify-center gap-1 ${
                            isAlreadyDressed
                              ? 'bg-slate-200 text-slate-700 hover:bg-rose-100 hover:text-rose-700'
                              : 'bg-white border border-slate-300 hover:bg-[#C5A059] hover:text-slate-950 text-slate-800 shadow-2xs'
                          }`}
                        >
                          {isAlreadyDressed ? '✕ Remove' : '+ Dress on Body'}
                        </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Privacy Footer Notice */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 text-[10px] text-slate-500 font-light leading-relaxed">
                🔒 <strong>CONFIT Privacy Shield:</strong> On-device identity preservation with zero facial distortion.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Live Camera Scan Modal */}
      <CameraScanModal
        isOpen={isCameraScanOpen}
        onClose={() => setIsCameraScanOpen(false)}
        onApplyMeasurements={() => {
          runTryOn();
        }}
      />
    </>
  );
};
