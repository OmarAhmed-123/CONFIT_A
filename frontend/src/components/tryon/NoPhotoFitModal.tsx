import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '../../stores/uiStore';
import { useTryOnViewModel } from '../../viewmodels/useTryOnViewModel';
import { RulerIcon, SparkleIcon, BagIcon } from '../icons/ConfitIcons';
import { useCartStore } from '../../stores/cartStore';
import { CameraScanModal } from './CameraScanModal';

export const NoPhotoFitModal: React.FC = () => {
  const { t } = useTranslation();
  const { rulerProduct, closeRuler } = useUIStore();
  const { rulerLoading, noPhotoResult, runNoPhotoFit } = useTryOnViewModel(rulerProduct);
  const { addItem, openCart } = useCartStore();

  const [height, setHeight] = useState(178);
  const [weight, setWeight] = useState(72);
  const [shape, setShape] = useState('Athletic');
  const [chest, setChest] = useState(98);
  const [waist, setWaist] = useState(82);
  const [fitPref, setFitPref] = useState('regular');
  const [isCameraScanOpen, setIsCameraScanOpen] = useState(false);

  if (!rulerProduct) return null;

  const handleCalculate = (customData?: any) => {
    runNoPhotoFit({
      height_cm: customData?.height_cm || height,
      weight_kg: customData?.weight_kg || weight,
      body_shape: customData?.body_shape || shape,
      chest_cm: customData?.chest_cm || chest,
      waist_cm: customData?.waist_cm || waist,
      preferred_fit: fitPref,
    });
  };

  const handleApplyFromScan = (scanData: any) => {
    setHeight(scanData.height_cm);
    setWeight(scanData.weight_kg);
    setShape(scanData.body_shape);
    setChest(scanData.chest_cm);
    setWaist(scanData.waist_cm);
    handleCalculate(scanData);
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md animate-in fade-in duration-150">
        <div className="w-full max-w-3xl bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden max-h-[92vh] flex flex-col">
          {/* Modal Header */}
          <div className="p-4 sm:p-6 border-b border-slate-100 bg-[#FAF9F6] flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-[#1B1F3B]">
                <RulerIcon size={22} color="#1B1F3B" />
              </div>
              <div>
                <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                  {t('tryon.ruler_mode')}
                </h3>
                <p className="text-xs text-slate-500 font-light">
                  100% Privacy-Preserving Anthropometric Analysis for <span className="font-semibold text-slate-800">{rulerProduct.title}</span>
                </p>
              </div>
            </div>
            <button
              onClick={closeRuler}
              className="w-8 h-8 rounded-full bg-slate-100 text-slate-500 hover:text-slate-900 flex items-center justify-center transition-colors"
            >
              ✕
            </button>
          </div>

          {/* Modal Body */}
          <div className="p-6 overflow-y-auto flex-1 grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Left Inputs */}
            <div className="space-y-4">
              <div className="flex justify-between items-center bg-[#FDF8EE] p-3 rounded-2xl border border-[#C5A059]/30">
                <div className="text-xs">
                  <div className="font-bold text-[#1B1F3B]">Fast Body Scan</div>
                  <div className="text-[10px] text-slate-500 font-light">Estimate dimensions in 2s via live camera</div>
                </div>
                <button
                  type="button"
                  onClick={() => setIsCameraScanOpen(true)}
                  className="px-3 py-1.5 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] text-slate-950 text-[11px] font-bold shadow-2xs"
                >
                  📸 Open Camera
                </button>
              </div>

              <div>
                <div className="flex justify-between text-xs font-bold text-slate-800 mb-1">
                  <span>Height: {height} cm</span>
                  <span className="text-slate-400 font-light">({Math.floor(height / 30.48)}' {Math.round((height % 30.48) / 2.54)}")</span>
                </div>
                <input
                  type="range"
                  min="140"
                  max="210"
                  value={height}
                  onChange={(e) => setHeight(Number(e.target.value))}
                  className="w-full accent-[#C5A059]"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs font-bold text-slate-800 mb-1">
                  <span>Weight: {weight} kg</span>
                  <span className="text-slate-400 font-light">({Math.round(weight * 2.204)} lbs)</span>
                </div>
                <input
                  type="range"
                  min="40"
                  max="140"
                  value={weight}
                  onChange={(e) => setWeight(Number(e.target.value))}
                  className="w-full accent-[#C5A059]"
                />
              </div>

              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1.5">Body Silhouette Type:</label>
                <div className="grid grid-cols-3 gap-1.5">
                  {['Athletic', 'Hourglass', 'Rectangle', 'Pear', 'Inverted Triangle'].map((s) => (
                    <button
                      key={s}
                      onClick={() => setShape(s)}
                      className={`py-2 px-1.5 text-center text-xs rounded-xl border transition-all truncate ${
                        shape === s
                          ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44] font-bold'
                          : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1.5">Preferred Fit:</label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: 'slim', label: 'Tailored Slim' },
                    { id: 'regular', label: 'Classic Regular' },
                    { id: 'oversized', label: 'Relaxed Drape' },
                  ].map((f) => (
                    <button
                      key={f.id}
                      onClick={() => setFitPref(f.id)}
                      className={`py-2 px-2 text-center text-xs rounded-xl border transition-all ${
                        fitPref === f.id
                          ? 'border-[#1B1F3B] bg-[#1B1F3B] text-white font-bold'
                          : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              <button
                onClick={() => handleCalculate()}
                disabled={rulerLoading}
                className="w-full py-3.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-semibold text-xs shadow-md transition-all flex items-center justify-center gap-2"
              >
                {rulerLoading ? 'Calculating Brand Proportions...' : 'Compute Precision Fit Verdict'}
              </button>
            </div>

            {/* Right Verdict Result */}
            <div className="bg-[#FAF9F6] border border-slate-200/80 rounded-2xl p-5 flex flex-col justify-between">
              {noPhotoResult ? (
                <div className="space-y-4">
                  <div className="flex justify-between items-center pb-3 border-b border-slate-200">
                    <div>
                      <span className="text-[10px] text-slate-400 font-bold uppercase">Optimal Recommended Size</span>
                      <div className="text-2xl font-serif font-black text-[#1B1F3B]">
                        Size {noPhotoResult.recommended_size}
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="text-xs font-bold text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 block">
                        {noPhotoResult.return_risk_score}
                      </span>
                    </div>
                  </div>

                  {/* Fit Breakdown */}
                  <div className="space-y-2">
                    <span className="text-xs font-bold text-slate-800">Zone Fit Breakdown:</span>
                    <div className="bg-white rounded-xl p-3 border border-slate-200 space-y-1.5 text-xs">
                      {Object.entries(noPhotoResult.fit_breakdown).map(([zone, desc]) => (
                        <div key={zone} className="flex justify-between items-center text-slate-700">
                          <span className="capitalize font-semibold text-slate-900">{zone}:</span>
                          <span className="text-slate-600 font-light">{desc}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <p className="text-[11px] text-slate-500 font-light italic bg-white/80 p-2.5 rounded-lg border border-slate-100">
                    ℹ️ {noPhotoResult.brand_sizing_tendency}
                  </p>

                  <button
                    onClick={async () => {
                      const sku = rulerProduct.skus?.[0];
                      if (sku) {
                        await addItem(sku.id, {
                          id: rulerProduct.id,
                          title: rulerProduct.title,
                          category: rulerProduct.category_name,
                          color: rulerProduct.color_family,
                        });
                        closeRuler();
                        openCart();
                      }
                    }}
                    className="w-full py-3.5 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] text-slate-950 font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
                  >
                    <BagIcon size={14} color="#0C0E1E" />
                    <span>Add Size {noPhotoResult.recommended_size} to Bag</span>
                  </button>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center p-6 text-slate-400">
                  <RulerIcon size={36} color="#C5A059" />
                  <span className="text-xs font-semibold text-slate-700 mt-3">Adjust measurements or scan with camera</span>
                  <span className="text-[11px] text-slate-400 font-light mt-1 max-w-xs">
                    We cross-reference your height, weight, and silhouette against {rulerProduct.brand_name}'s precise pattern specifications.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <CameraScanModal
        isOpen={isCameraScanOpen}
        onClose={() => setIsCameraScanOpen(false)}
        onApplyMeasurements={handleApplyFromScan}
      />
    </>
  );
};
