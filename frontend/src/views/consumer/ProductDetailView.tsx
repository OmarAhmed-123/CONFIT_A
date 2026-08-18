import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { catalogService } from '../../services/apiServices';
import { Product, StoreInventoryLocation } from '../../models';
import { useUIStore } from '../../stores/uiStore';
import { useCartStore } from '../../stores/cartStore';
import {
  TryOnIcon,
  RulerIcon,
  BagIcon,
  BopisIcon,
  SparkleIcon,
} from '../../components/icons/ConfitIcons';
import { FitScoreBadge, BNPLBadge, LoadingSpinner } from '../../components/common/CommonComponents';

export const ProductDetailView: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [product, setProduct] = useState<Product | null>(null);
  const [selectedSkuId, setSelectedSkuId] = useState<number | null>(null);
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [bopisStores, setBopisStores] = useState<StoreInventoryLocation[]>([]);
  const [bopisOpen, setBopisOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const { openTryOn, openRuler, showToast } = useUIStore();
  const { addItem } = useCartStore();

  useEffect(() => {
    if (!slug) return;
    setIsLoading(true);
    catalogService
      .getProductDetail(slug)
      .then((data) => {
        setProduct(data);
        if (data.skus && data.skus.length > 0) {
          setSelectedSkuId(data.skus[0].id);
          catalogService.getBopisStoresForSKU(data.skus[0].id).then(setBopisStores);
        }
        setIsLoading(false);
      })
      .catch((err) => {
        setIsLoading(false);
        showToast('Product not found: ' + err.message, 'error');
      });
  }, [slug, showToast]);

  if (isLoading || !product) {
    return <LoadingSpinner text="Loading garment specifications and pattern curves..." />;
  }

  const currentSku = product.skus?.find((s) => s.id === selectedSkuId) || product.skus?.[0];
  const images = product.images && product.images.length > 0 ? product.images : [product.thumbnail_url];

  return (
    <div className="space-y-12 pb-24">
      {/* Breadcrumb */}
      <div className="text-xs text-slate-400 flex items-center gap-2 font-light">
        <button onClick={() => navigate('/discover')} className="hover:text-[#1B1F3B] transition-colors">
          Catalog
        </button>
        <span>/</span>
        <span>{product.category_name}</span>
        <span>/</span>
        <span className="font-semibold text-slate-800">{product.title}</span>
      </div>

      {/* Main Product Section */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
        {/* Left: Product Images Gallery (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="h-[520px] rounded-3xl overflow-hidden bg-slate-100 border border-slate-200/80 relative group shadow-sm">
            <img
              src={images[activeImageIndex] || product.thumbnail_url}
              alt={product.title}
              className="w-full h-full object-cover"
            />
            <div className="absolute top-4 left-4">
              <FitScoreBadge score={product.style_compatibility_score} verdict="96% Match with Your USP" />
            </div>

            {/* Quick Virtual Try-On Floating Button */}
            <button
              onClick={() => openTryOn(product)}
              className="absolute bottom-4 right-4 px-5 py-3 rounded-2xl bg-[#1B1F3B]/95 hover:bg-[#C5A059] text-white hover:text-slate-950 text-xs font-bold shadow-xl backdrop-blur-md transition-all flex items-center gap-2"
            >
              <TryOnIcon size={18} color="currentColor" />
              <span>Launch Virtual Try-On</span>
            </button>
          </div>

          {/* Thumbnail Strip */}
          {images.length > 1 && (
            <div className="flex gap-3 overflow-x-auto pb-1">
              {images.map((img, idx) => (
                <button
                  key={idx}
                  onClick={() => setActiveImageIndex(idx)}
                  className={`w-20 h-24 rounded-2xl overflow-hidden border-2 transition-all shrink-0 ${
                    activeImageIndex === idx ? 'border-[#C5A059] ring-2 ring-[#C5A059]/30' : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <img src={img} alt="Thumb" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: Product Purchasing & AI Sizing Actions (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div>
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-1">
              {product.brand_name}
            </span>
            <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[#1B1F3B] leading-tight">
              {product.title}
            </h1>
            <div className="flex items-baseline gap-3 mt-2">
              <span className="text-2xl font-serif font-black text-[#1B1F3B]">
                ${product.base_price.toFixed(2)}
              </span>
              <span className="text-xs text-slate-400 font-light">VAT & duties included</span>
            </div>

            {/* BNPL Split Payment */}
            <div className="mt-3 p-3 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/30">
              <BNPLBadge price={product.base_price} provider="Tabby & Tamara" />
            </div>
          </div>

          {/* AI Size & Fit Recommendation Module (PDF 5.1 Requirement) */}
          <div className="p-4.5 rounded-2xl bg-white border border-slate-200/80 shadow-2xs space-y-3">
            <div className="flex justify-between items-center pb-2 border-b border-slate-100">
              <div className="flex items-center gap-1.5">
                <SparkleIcon size={16} color="#C5A059" />
                <span className="text-xs font-bold text-[#1B1F3B]">AI Fit Recommendation:</span>
              </div>
              <button
                onClick={() => openRuler(product)}
                className="text-xs font-bold text-[#C5A059] hover:underline flex items-center gap-1"
              >
                <RulerIcon size={14} color="#C5A059" />
                <span>No-Photo Size Guide</span>
              </button>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed font-light">
              Based on your athletic body profile (178cm / 72kg), <strong>Size {currentSku?.size || 'M'}</strong> is recommended for an optimal shoulder contour and relaxed drape.
            </p>

            {/* Size Selector */}
            <div>
              <span className="text-xs font-bold text-slate-700 block mb-1.5">Select Size:</span>
              <div className="flex gap-2">
                {product.skus?.map((sku) => (
                  <button
                    key={sku.id}
                    onClick={() => setSelectedSkuId(sku.id)}
                    className={`w-12 h-11 rounded-xl border text-xs font-bold transition-all ${
                      selectedSkuId === sku.id
                        ? 'border-[#1B1F3B] bg-[#1B1F3B] text-white shadow-2xs'
                        : 'border-slate-200 hover:border-slate-300 text-slate-800 bg-white'
                    }`}
                  >
                    {sku.size}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Action Buttons: Add to Bag & Try On */}
          <div className="space-y-2.5">
            <button
              onClick={async () => {
                if (currentSku) {
                  await addItem(currentSku.id, {
                    id: product.id,
                    title: product.title,
                    category: product.category_name,
                    color: product.color_family,
                  });
                }
              }}
              className="w-full py-4 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
            >
              <BagIcon size={16} color="#FFFFFF" />
              <span>Add to Shopping Bag — ${product.base_price.toFixed(2)}</span>
            </button>

            <button
              onClick={() => openTryOn(product)}
              className="w-full py-3.5 rounded-2xl bg-[#FDF8EE] hover:bg-[#C5A059] text-[#C5A059] hover:text-white border border-[#C5A059]/40 font-bold text-xs shadow-2xs transition-all flex items-center justify-center gap-2"
            >
              <TryOnIcon size={16} color="currentColor" />
              <span>Try On Digitally with AI</span>
            </button>
          </div>

          {/* BOPIS In-Store Availability Check */}
          <div className="p-4 rounded-2xl bg-[#FAF9F6] border border-slate-200/80 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BopisIcon size={18} color="#1B1F3B" />
                <span className="text-xs font-bold text-[#1B1F3B]">Boutique Pickup (BOPIS)</span>
              </div>
              <button
                onClick={() => setBopisOpen(!bopisOpen)}
                className="text-xs font-bold text-[#C5A059] hover:underline"
              >
                {bopisOpen ? 'Hide Stores' : 'Check Store Stock'}
              </button>
            </div>

            {bopisOpen && (
              <div className="pt-2 border-t border-slate-200/80 space-y-2 text-xs">
                {bopisStores.map((store) => (
                  <div key={store.store_id} className="p-2.5 rounded-xl bg-white border border-slate-200/80 flex justify-between items-center">
                    <div>
                      <div className="font-bold text-slate-800">{store.store_name}</div>
                      <div className="text-[11px] text-slate-500 font-light">{store.address}, {store.city}</div>
                    </div>
                    <div className="text-right">
                      <span className="text-[11px] font-bold text-emerald-600">
                        {store.quantity_available} in stock
                      </span>
                      <span className="text-[10px] text-slate-400 block font-light">Ready in 2h</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Fabric and Care Specs */}
          <div className="border-t border-slate-200/80 pt-4 space-y-2 text-xs text-slate-600 font-light">
            <div><strong className="font-semibold text-slate-800">Material:</strong> {product.material || 'Premium Italian wool blend'}</div>
            <div><strong className="font-semibold text-slate-800">Care:</strong> {product.care_instructions || 'Specialist dry clean only'}</div>
            <p className="pt-2 text-slate-500 leading-relaxed font-light">{product.description}</p>
          </div>
        </div>
      </div>
    </div>
  );
};
