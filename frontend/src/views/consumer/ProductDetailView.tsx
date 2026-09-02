import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { catalogService } from '../../services/apiServices';
import { Product, StoreInventoryLocation } from '../../models';
import { useUIStore } from '../../stores/uiStore';
import { useCartStore } from '../../stores/cartStore';
import {
  TryOnIcon,
  RulerIcon,
  BagIcon,
  SparkleIcon,
  HeartIcon,
} from '../../components/icons/ConfitIcons';
import { FitScoreBadge, BNPLBadge, LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';

export const ProductDetailView: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();

  const [product, setProduct] = useState<Product | null>(null);
  const [selectedSkuId, setSelectedSkuId] = useState<number | null>(null);
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [bopisStores, setBopisStores] = useState<StoreInventoryLocation[]>([]);
  const [bopisStatus, setBopisStatus] = useState<'idle' | 'loading' | 'success' | 'empty' | 'error'>('idle');
  const [bopisError, setBopisError] = useState<string | null>(null);
  const [isWishlisted, setIsWishlisted] = useState(false);
  const [activeAccordion, setActiveAccordion] = useState<'materials' | 'bopis' | 'delivery' | null>('materials');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const { openTryOn, openRuler, showToast } = useUIStore();
  const { addItem } = useCartStore();

  // C6 FIX: BOPIS failure handling - differentiate no stores vs API failure vs network
  const fetchBopisStores = (skuId: number) => {
    setBopisStatus('loading');
    setBopisError(null);
    catalogService
      .getBopisStoresForSKU(skuId)
      .then((stores) => {
        setBopisStores(stores);
        setBopisStatus(stores.length === 0 ? 'empty' : 'success');
      })
      .catch((err: any) => {
        setBopisStores([]);
        setBopisStatus('error');
        const msg = err?.message || 'Unable to load boutique availability';
        setBopisError(msg);
        // Don't show toast for BOPIS - it's secondary info, show inline error instead
      });
  };

  useEffect(() => {
    if (!slug) return;
    setIsLoading(true);
    setLoadError(null);
    catalogService
      .getProductDetail(slug)
      .then((data) => {
        setProduct(data);
        const firstInStock = data.skus?.find((s) => s.is_in_stock) || data.skus?.[0];
        if (firstInStock) {
          setSelectedSkuId(firstInStock.id);
          fetchBopisStores(firstInStock.id);
        }
        setIsLoading(false);
      })
      .catch((err) => {
        setIsLoading(false);
        setLoadError(err.message || 'Product not found');
      });
  }, [slug]);

  useEffect(() => {
    if (!selectedSkuId) return;
    fetchBopisStores(selectedSkuId);
  }, [selectedSkuId]);

  if (isLoading) {
    return <LoadingSpinner text="Loading garment details..." />;
  }

  if (loadError || !product) {
    return (
      <EmptyState
        title="This piece is unavailable"
        description={loadError || 'The product could not be loaded from the catalogue.'}
      />
    );
  }

  const currentSku = product.skus?.find((s) => s.id === selectedSkuId) || product.skus?.[0];
  const images = product.images && product.images.length > 0 ? product.images : [product.thumbnail_url];
  const bnpl = product.bnpl;
  const styleScore = product.style_compatibility_available ? product.style_compatibility_score : null;
  const fitScore = product.fit_available ? product.ai_fit_score : null;

  return (
    <div className="space-y-12 pb-24 max-w-6xl mx-auto">
      <nav className="text-xs text-slate-400 flex items-center gap-2 font-light">
        <Link to="/discover" className="hover:text-[#1B1F3B] transition-colors">
          Catalog
        </Link>
        <span>/</span>
        <Link to={`/discover?category=${product.category_id}`} className="hover:text-[#1B1F3B] transition-colors">
          {product.category_name}
        </Link>
        <span>/</span>
        <span className="font-semibold text-slate-800 truncate max-w-xs">{product.title}</span>
      </nav>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
        <div className="lg:col-span-7 space-y-4">
          <div className="aspect-[3/4] sm:h-[540px] rounded-3xl overflow-hidden bg-slate-100 border border-slate-200/80 relative group shadow-sm">
            <img
              src={images[activeImageIndex] || product.thumbnail_url}
              alt={product.title}
              loading="lazy"
              decoding="async"
              className="w-full h-full object-cover"
              onError={(e) => { const t=e.currentTarget as HTMLImageElement; if(!t.dataset.fallback){ t.dataset.fallback="true"; t.src=`https://placehold.co/600x800/1B1F3B/FFFFFF?text=${encodeURIComponent(product.title.slice(0,20))}`; } }}
            />
            <div className="absolute top-4 left-4 flex flex-col gap-2">
              {styleScore != null && (
                <FitScoreBadge
                  score={styleScore}
                  verdict={product.style_compatibility_reason || 'Style match'}
                />
              )}
              {fitScore != null && (
                <FitScoreBadge
                  score={fitScore}
                  verdict={
                    product.recommended_size
                      ? product.recommended_size_available
                        ? `Recommended ${product.recommended_size}`
                        : `${product.recommended_size} unavailable`
                      : 'Fit score'
                  }
                />
              )}
            </div>

            <button
              onClick={() => setIsWishlisted(!isWishlisted)}
              className="absolute top-4 right-4 p-2.5 rounded-full bg-white/90 hover:bg-white text-slate-800 shadow-md backdrop-blur-xs transition-all"
              aria-label="Add to wishlist"
            >
              <HeartIcon size={18} isLiked={isWishlisted} />
            </button>

            <button
              onClick={() => openTryOn(product)}
              className="absolute bottom-4 right-4 px-5 py-3 rounded-2xl bg-[#1B1F3B]/95 hover:bg-[#C5A059] text-white hover:text-slate-950 text-xs font-bold shadow-xl backdrop-blur-md transition-all flex items-center gap-2"
            >
              <TryOnIcon size={18} color="currentColor" />
              <span>Launch Virtual Try-On</span>
            </button>
          </div>

          {images.length > 1 && (
            <div className="flex gap-3 overflow-x-auto pb-1">
              {images.map((img, idx) => (
                <button
                  key={idx}
                  onClick={() => setActiveImageIndex(idx)}
                  aria-label={`View image ${idx + 1}`}
                  className={`w-20 h-24 rounded-2xl overflow-hidden border-2 transition-all shrink-0 ${
                    activeImageIndex === idx ? 'border-[#C5A059] ring-2 ring-[#C5A059]/30' : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <img src={img} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="lg:col-span-5 space-y-6">
          <div>
            <span className="text-xs font-bold text-[#C5A059] uppercase tracking-widest block mb-1">
              {product.brand_name}
            </span>
            <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[#1B1F3B] leading-tight">
              {product.title}
            </h1>
            <div className="flex items-baseline gap-3 mt-2">
              <span className="text-2xl font-serif font-black text-[#1B1F3B]">
                ${product.base_price.toFixed(2)}
              </span>
              <span className="text-xs text-slate-400 font-light">{product.currency}</span>
            </div>

            {bnpl?.eligible && bnpl.installment_amount != null && (
              <div className="mt-3 p-3 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/30">
                <BNPLBadge
                  price={product.base_price}
                  provider={bnpl.provider || undefined}
                  installmentAmount={bnpl.installment_amount}
                  eligible
                />
              </div>
            )}
          </div>

          <div className="p-4.5 rounded-2xl bg-white border border-slate-200/80 shadow-2xs space-y-3.5">
            <div className="flex justify-between items-center pb-2 border-b border-slate-100">
              <div className="flex items-center gap-1.5">
                <SparkleIcon size={16} color="#C5A059" />
                <span className="text-xs font-bold text-[#1B1F3B]">Size & fit</span>
              </div>
              <button
                onClick={() => openRuler(product)}
                className="text-xs font-bold text-[#C5A059] hover:underline flex items-center gap-1"
              >
                <RulerIcon size={14} color="#C5A059" />
                <span>Find my size</span>
              </button>
            </div>

            {product.fit_available ? (
              <p className="text-xs text-slate-600 leading-relaxed font-light">
                {product.fit_reasoning || `Recommended size ${product.recommended_size}.`}
                {product.recommended_size_available === false && (
                  <span className="block mt-1 text-amber-700 font-medium">The recommended size is not currently in stock.</span>
                )}
              </p>
            ) : (
              <p className="text-xs text-slate-500 leading-relaxed font-light">
                Complete your body profile to see a personal size recommendation. Until then, choose a size from available stock.
              </p>
            )}

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <span className="text-xs font-bold text-slate-700">Available sizes</span>
                <span className="text-[10px] font-semibold text-slate-500">
                  {currentSku?.is_in_stock
                    ? `${currentSku.stock_level} in stock`
                    : 'Out of stock'}
                </span>
              </div>
              <div className="flex gap-2 flex-wrap" role="listbox" aria-label="Select size">
                {product.skus?.map((sku) => (
                  <button
                    key={sku.id}
                    onClick={() => setSelectedSkuId(sku.id)}
                    disabled={!sku.is_in_stock}
                    aria-selected={selectedSkuId === sku.id}
                    className={`min-w-[48px] h-11 px-3 rounded-xl border text-xs font-bold transition-all ${
                      selectedSkuId === sku.id
                        ? 'border-[#1B1F3B] bg-[#1B1F3B] text-white shadow-2xs'
                        : sku.is_in_stock
                        ? 'border-slate-200 hover:border-slate-300 text-slate-800 bg-white'
                        : 'border-slate-100 text-slate-300 bg-slate-50 cursor-not-allowed line-through'
                    }`}
                  >
                    {sku.size}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-2.5">
            <button
              disabled={!currentSku?.is_in_stock || adding}
              onClick={async () => {
                if (!currentSku) return;
                setAdding(true);
                try {
                  await addItem(currentSku.id, {
                    id: product.id,
                    title: product.title,
                    category: product.category_name,
                    color: product.color_family,
                  });
                  showToast('Added to bag', 'success');
                } catch (err: any) {
                  showToast(err?.message || 'Could not add to bag', 'error');
                } finally {
                  setAdding(false);
                }
              }}
              className="w-full py-4 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-50 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
            >
              <BagIcon size={16} color="#FFFFFF" />
              <span>
                {!currentSku?.is_in_stock
                  ? 'Out of stock'
                  : adding
                  ? 'Adding...'
                  : `Add to bag — $${(currentSku?.price_override ?? product.base_price).toFixed(2)}`}
              </span>
            </button>

            <button
              onClick={() => openTryOn(product)}
              className="w-full py-3.5 rounded-2xl bg-[#FDF8EE] hover:bg-[#C5A059] text-[#C5A059] hover:text-white border border-[#C5A059]/40 font-bold text-xs shadow-2xs transition-all flex items-center justify-center gap-2"
            >
              <TryOnIcon size={16} color="currentColor" />
              <span>Try on digitally</span>
            </button>
          </div>

          <div className="border-t border-slate-200/80 pt-2 divide-y divide-slate-100 text-xs">
            <div className="py-3">
              <button
                onClick={() => setActiveAccordion(activeAccordion === 'materials' ? null : 'materials')}
                className="w-full flex justify-between items-center font-bold text-slate-800 text-left"
                aria-expanded={activeAccordion === 'materials'}
              >
                <span>Fabric, care & details</span>
                <span>{activeAccordion === 'materials' ? '−' : '+'}</span>
              </button>
              {activeAccordion === 'materials' && (
                <div className="pt-2 text-slate-500 space-y-1.5 font-light leading-relaxed">
                  <div><strong>Composition:</strong> {product.material || 'Not specified'}</div>
                  <div><strong>Care:</strong> {product.care_instructions || 'See garment label'}</div>
                  {product.description && <p className="pt-1">{product.description}</p>}
                </div>
              )}
            </div>

            <div className="py-3">
              <button
                onClick={() => setActiveAccordion(activeAccordion === 'bopis' ? null : 'bopis')}
                className="w-full flex justify-between items-center font-bold text-slate-800 text-left"
                aria-expanded={activeAccordion === 'bopis'}
              >
                <span>Boutique pickup (BOPIS)</span>
                <span>{activeAccordion === 'bopis' ? '−' : '+'}</span>
              </button>
              {activeAccordion === 'bopis' && (
                <div className="pt-2 space-y-2">
                  {bopisStatus === 'loading' && (
                    <p className="text-slate-500 font-light text-xs">Checking boutique availability...</p>
                  )}
                  {bopisStatus === 'error' && (
                    <div className="p-3 rounded-xl bg-rose-50 border border-rose-200">
                      <p className="text-[11px] font-bold text-rose-800">Boutique availability check failed</p>
                      <p className="text-[11px] text-rose-600 mt-1">{bopisError || 'Unable to reach inventory service. Please try again or use home delivery.'}</p>
                      <button
                        onClick={() => selectedSkuId && fetchBopisStores(selectedSkuId)}
                        className="mt-2 px-3 py-1.5 rounded-lg bg-white border border-rose-200 text-[11px] font-bold text-rose-700 hover:bg-rose-50"
                      >
                        Retry
                      </button>
                    </div>
                  )}
                  {bopisStatus === 'empty' && (
                    <p className="text-slate-500 font-light text-xs">No nearby stores currently hold this size. Home delivery remains available at checkout.</p>
                  )}
                  {bopisStatus === 'success' && bopisStores.filter((s) => s.is_available_for_pickup).length === 0 && (
                    <p className="text-slate-500 font-light text-xs">No nearby stores currently hold this size with available stock. Home delivery remains available at checkout.</p>
                  )}
                  {bopisStatus === 'success' && bopisStores.filter((s) => s.is_available_for_pickup).length > 0 && (
                    <>
                      {bopisStores
                        .filter((s) => s.is_available_for_pickup)
                        .map((store) => (
                          <div key={store.store_id} className="p-2.5 rounded-xl bg-[#FAF9F6] border border-slate-200/80 flex justify-between items-center gap-2">
                            <div>
                              <div className="font-bold text-slate-800 text-xs">{store.store_name}</div>
                              <div className="text-[11px] text-slate-500 font-light">{store.address}</div>
                              {store.latitude != null && store.longitude != null && (
                                <a
                                  className="text-[11px] text-[#C5A059] font-semibold"
                                  href={`https://www.openstreetmap.org/?mlat=${store.latitude}&mlon=${store.longitude}#map=16/${store.latitude}/${store.longitude}`}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Open map
                                </a>
                              )}
                            </div>
                            <div className="text-right">
                              <span className="text-[11px] font-bold text-emerald-600">
                                {store.quantity_available} in stock
                              </span>
                            </div>
                          </div>
                        ))}
                    </>
                  )}
                </div>
              )}
            </div>

            <div className="py-3">
              <button
                onClick={() => setActiveAccordion(activeAccordion === 'delivery' ? null : 'delivery')}
                className="w-full flex justify-between items-center font-bold text-slate-800 text-left"
                aria-expanded={activeAccordion === 'delivery'}
              >
                <span>Delivery & returns</span>
                <span>{activeAccordion === 'delivery' ? '−' : '+'}</span>
              </button>
              {activeAccordion === 'delivery' && (
                <div className="pt-2 text-slate-500 space-y-1.5 font-light leading-relaxed">
                  <div>Standard or express home delivery is quoted at checkout from live cart totals.</div>
                  <div>Eligible orders can be returned within 30 days from the order date. Return authorisation is issued from order history.</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {product.related_outfits && product.related_outfits.length > 0 && (
        <section className="space-y-4">
          <h2 className="font-serif text-xl font-bold text-[#1B1F3B]">Complete the look</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {product.related_outfits.map((outfit, idx) => (
              <div key={`${outfit.title}-${idx}`} className="rounded-3xl border border-slate-200 p-4 bg-white space-y-3">
                <h3 className="text-sm font-bold text-[#1B1F3B]">{outfit.title}</h3>
                <div className="grid grid-cols-2 gap-3">
                  {outfit.items.map((item) => (
                    <Link
                      key={item.product_id}
                      to={item.slug ? `/product/${item.slug}` : `/discover`}
                      className="rounded-2xl border border-slate-100 p-2 hover:border-[#C5A059] transition-colors"
                    >
                      {item.image_url && (
                        <img src={item.image_url} alt={item.product_title} className="w-full h-28 object-cover rounded-xl mb-2" />
                      )}
                      <div className="text-[11px] font-bold text-slate-800 truncate">{item.product_title}</div>
                      <div className="text-[10px] text-slate-500">{item.brand_name}</div>
                      {item.price != null && <div className="text-[11px] font-semibold">${item.price}</div>}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};
