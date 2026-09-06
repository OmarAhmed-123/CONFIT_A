import { CardStackShowcase } from '../../components/showcase/DesignShowcases';
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  DndContext,
  DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { useOutfitBuilderViewModel, CanvasItem } from '../../viewmodels/useOutfitBuilderViewModel';
import { useCatalogViewModel } from '../../viewmodels/useCatalogViewModel';
import { useUIStore } from '../../stores/uiStore';
import {
  OutfitBuilderIcon,
  SparkleIcon,
  BagIcon,
  SavedLooksIcon,
} from '../../components/icons/ConfitIcons';
import { FitScoreBadge } from '../../components/common/CommonComponents';
import { Product } from '../../models';

type SlotKey = CanvasItem['slot'];

// BUILDER-02 FIX: the accessory slot is part of the canvas taxonomy
// (CanvasItem.slot already modelled it) but the UI omitted it, so clicking a
// clutch or tie added it to state invisibly — money left the total while no
// slot showed the piece. Accessories are now a first-class slot with the
// same replace/remove/validation rules as the four garment slots.
const SLOT_KEYS: SlotKey[] = ['outerwear', 'top', 'bottom', 'footwear', 'accessory'];

const SLOTS: Array<{ key: SlotKey; label: string }> = [
  { key: 'outerwear', label: 'Outerwear Layer' },
  { key: 'top', label: 'Top / Shirt' },
  { key: 'bottom', label: 'Trousers / Bottom' },
  { key: 'footwear', label: 'Footwear / Loafers' },
  { key: 'accessory', label: 'Accessory / Final Touch' },
];

/** C6 — a draggable catalog product. Also a real <button>: keyboard users
 * press Enter/Space to add via the same ViewModel path (the accessible
 * fallback for pointer drag). */
const DraggableProduct: React.FC<{
  product: Product;
  onAdd: (p: Product) => void;
}> = ({ product, onAdd }) => {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `product-${product.id}`,
    data: { product },
  });

  return (
    <button
      ref={setNodeRef}
      type="button"
      {...listeners}
      {...attributes}
      onClick={() => onAdd(product)}
      style={{ transform: CSS.Translate.toString(transform) }}
      aria-label={`Add ${product.title} to outfit`}
      className={`text-left bg-[#FAF9F6] border rounded-2xl p-2 cursor-grab transition-all flex flex-col justify-between ${
        isDragging
          ? 'opacity-50 border-[#C5A059] shadow-lg z-50'
          : 'border-slate-200/80 hover:border-[#C5A059] hover:shadow-sm'
      }`}
    >
      <div className="h-28 rounded-xl overflow-hidden bg-white mb-1.5 relative w-full">
        <img src={product.thumbnail_url} alt={product.title} className="w-full h-full object-cover" />
        <span className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-black/60 text-[9px] text-white font-medium">
          Drag or Enter to add
        </span>
      </div>
      <div>
        <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
          {product.brand_name}
        </span>
        <span className="text-[11px] font-bold text-[#1B1F3B] line-clamp-1">{product.title}</span>
        <span className="text-xs font-bold text-[#1B1F3B] mt-0.5 block">${product.base_price}</span>
      </div>
    </button>
  );
};

/** C6 — a droppable outfit slot with keyboard removal and live highlighting. */
const DroppableSlot: React.FC<{
  slot: { key: SlotKey; label: string };
  item?: CanvasItem;
  onRemove: (slot: SlotKey) => void;
}> = ({ slot, item, onRemove }) => {
  const { setNodeRef, isOver } = useDroppable({ id: `slot-${slot.key}` });

  return (
    <div
      ref={setNodeRef}
      data-testid={`slot-${slot.key}`}
      className={`h-64 rounded-2xl border transition-all p-3 flex flex-col justify-between relative group ${
        isOver
          ? 'border-[#C5A059] bg-[#C5A059]/10 ring-2 ring-[#C5A059]/40'
          : item
            ? 'border-[#C5A059]/60 bg-[#FAF9F6] shadow-2xs'
            : 'border-dashed border-slate-300 bg-slate-50/50'
      }`}
    >
      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block text-center">
        {slot.label}
      </span>

      {item ? (
        <>
          <button
            onClick={() => onRemove(slot.key)}
            className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/60 hover:bg-rose-600 text-white flex items-center justify-center text-xs transition-colors z-10"
            title="Remove item"
            aria-label={`Remove ${item.product.title} from ${slot.label}`}
          >
            ✕
          </button>
          <div className="h-36 w-full rounded-xl overflow-hidden bg-white my-auto shadow-2xs">
            <img
              src={item.product.thumbnail_url}
              alt={item.product.title}
              className="w-full h-full object-cover"
            />
          </div>
          <div className="text-center mt-1">
            <span className="text-[10px] text-slate-400 font-semibold block truncate">
              {item.product.brand_name}
            </span>
            <span className="text-xs font-bold text-[#1B1F3B] block truncate">
              {item.product.title}
            </span>
            <span className="text-xs font-bold text-[#A37E44]">${item.product.base_price}</span>
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center my-auto text-center p-2 text-slate-400">
          <OutfitBuilderIcon size={22} color="#CBD5E1" />
          <span className="text-[11px] font-light mt-1 text-slate-500">
            Drop a piece here, or press Enter on a product below
          </span>
        </div>
      )}
    </div>
  );
};

export const OutfitBuilderView: React.FC = () => {
  const { t } = useTranslation();
  const {
    selectedItems,
    targetOccasion,
    setTargetOccasion,
    outfitTitle,
    setOutfitTitle,
    runningTotal,
    userBudgetLimit,
    isOverBudget,
    compatibility,
    isSaving,
    addItemToCanvas,
    isValidSlotForProduct,
    removeItemFromCanvas,
    clearCanvas,
    saveOutfit,
    addAllToCart,
  } = useOutfitBuilderViewModel(450.0);

  const { products } = useCatalogViewModel();
  const { showToast } = useUIStore();

  // BUILDER-01 FIX: PointerSensor previously had NO activationConstraint, so
  // a drag activated on raw pointerdown. dnd-kit then swallowed the ensuing
  // click, so plain mouse clicks on the palette never reached the button's
  // onClick — the exact "items were dropped but the canvas stayed empty and
  // the total stayed $0.00" behaviour in the 2026-09-05 audit. A 6px distance
  // constraint is the standard click-vs-drag separator: a click (press+release
  // in place) fires onClick and adds the piece; moving 6px+ starts a real drag.
  // KeyboardSensor is unchanged (Enter on a focused card adds directly).
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor)
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const product = (active.data.current as { product?: Product } | undefined)?.product;
    const slotKey = String(over.id).replace(/^slot-/, '') as SlotKey;
    if (!product || !SLOT_KEYS.includes(slotKey)) return;
    // Invalid drops (e.g. footwear onto the top slot) never touch state.
    if (!isValidSlotForProduct(product, slotKey)) {
      showToast(`"${product.title}" doesn't belong in the ${slotKey} slot.`, 'error');
      return;
    }
    addItemToCanvas(product, slotKey);
  };

  return (
    <div className="space-y-8 pb-24">
      <CardStackShowcase
        tone="consumer"
        compact
        eyebrow="Builder Inspiration Stack"
        title="Start from a styled formula, then customize the canvas"
        description="The stack gives outfit building a premium starting point before users drag catalog or wardrobe pieces into slots."
      />
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <OutfitBuilderIcon size={24} color="#1B1F3B" />
            <h1 className="font-serif text-3xl font-bold text-[#1B1F3B] tracking-tight">
              {t('outfit_builder.title')}
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
            {t('outfit_builder.subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={clearCanvas}
            disabled={selectedItems.length === 0}
            className="px-4 py-2 rounded-xl border border-slate-300 hover:bg-slate-100 disabled:opacity-40 text-xs font-semibold text-slate-700 transition-all"
          >
            {t('outfit_builder.clear_canvas')}
          </button>
          <button
            onClick={saveOutfit}
            disabled={selectedItems.length === 0 || isSaving}
            className="px-5 py-2 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] disabled:opacity-40 text-slate-950 font-bold text-xs shadow-2xs transition-all flex items-center gap-1.5"
          >
            <SavedLooksIcon size={16} color="#0C0E1E" />
            <span>{isSaving ? 'Saving...' : t('outfit_builder.save_outfit')}</span>
          </button>
        </div>
      </div>

      {/* C6: one DndContext wraps palette + canvas so drops are real state transitions */}
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        {/* Main Canvas & Metrics Split */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left: Interactive Outfit Canvas (7 cols) */}
          <div className="lg:col-span-7 space-y-6">
            {/* Canvas Title & Occasion */}
            <div className="bg-white rounded-3xl border border-slate-200/80 p-5 shadow-2xs space-y-3">
              <div className="flex flex-col sm:flex-row gap-3">
                <input
                  type="text"
                  value={outfitTitle}
                  onChange={(e) => setOutfitTitle(e.target.value)}
                  placeholder="Give your look a name..."
                  className="flex-1 font-serif text-base font-bold text-[#1B1F3B] border-b border-slate-200 focus:outline-none focus:border-[#C5A059] py-1"
                />
                <select
                  value={targetOccasion}
                  onChange={(e) => setTargetOccasion(e.target.value)}
                  className="text-xs font-semibold bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 focus:outline-none focus:border-[#C5A059]"
                >
                  <option value="Smart Casual Work">Smart Casual Work</option>
                  <option value="Executive Boardroom">Executive Boardroom</option>
                  <option value="Evening Cocktail & Dinner">Evening Cocktail & Dinner</option>
                  <option value="Weekend Gallery Tour">Weekend Gallery Tour</option>
                  <option value="Formal Gala & Wedding">Formal Gala & Wedding</option>
                </select>
              </div>

              {/* Canvas Silhouette Slots (droppable) */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2">
                {SLOTS.map((slot) => (
                  <DroppableSlot
                    key={slot.key}
                    slot={slot}
                    item={selectedItems.find((i) => i.slot === slot.key)}
                    onRemove={removeItemFromCanvas}
                  />
                ))}
              </div>
            </div>

            {/* Catalog Mix & Match Selector (draggable) */}
            <div className="bg-white rounded-3xl border border-slate-200/80 p-5 shadow-2xs space-y-4">
              <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
                Drag Pieces from the Multi-Brand Catalog onto the Canvas:
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 max-h-96 overflow-y-auto pr-1">
                {products.map((p) => (
                  <DraggableProduct key={p.id} product={p} onAdd={(prod) => addItemToCanvas(prod)} />
                ))}
              </div>
            </div>
          </div>

          {/* Right: Live Running Budget Tracker & Harmony Score (5 cols) */}
          <div className="lg:col-span-5 space-y-6">
            {/* Live Budget Tracker Module */}
            <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
              <div className="flex justify-between items-center pb-3 border-b border-slate-100">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Live Budget Tracker Overlay
                </span>
                <span
                  className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                    isOverBudget
                      ? 'bg-rose-100 text-rose-700 border border-rose-200'
                      : 'bg-emerald-100 text-emerald-700 border border-emerald-200'
                  }`}
                >
                  {isOverBudget ? t('outfit_builder.over_budget') : t('outfit_builder.under_budget')}
                </span>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-baseline">
                  <span className="text-sm text-slate-600 font-light">
                    {t('outfit_builder.running_total')}:
                  </span>
                  <span className="text-2xl font-serif font-black text-[#1B1F3B]">
                    ${runningTotal.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Profile Target Allocation:</span>
                  <span>${userBudgetLimit.toFixed(2)} target</span>
                </div>

                {/* Progress Bar */}
                <div className="w-full h-2.5 rounded-full bg-slate-100 overflow-hidden mt-2">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      isOverBudget ? 'bg-rose-500' : 'bg-[#C5A059]'
                    }`}
                    style={{ width: `${Math.min(100, (runningTotal / userBudgetLimit) * 100)}%` }}
                  ></div>
                </div>
              </div>
            </div>

            {/* AI Color Harmony & Silhouette Synergy */}
            <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
              <div className="flex justify-between items-center pb-3 border-b border-slate-100">
                <div className="flex items-center gap-1.5">
                  <SparkleIcon size={16} color="#C5A059" />
                  <span className="text-xs font-bold text-[#1B1F3B]">
                    {t('outfit_builder.compatibility_rating')}
                  </span>
                </div>
                <FitScoreBadge
                  score={compatibility?.compatibility_score ?? 0}
                  verdict={compatibility?.color_harmony_type || 'Awaiting items'}
                />
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <span className="font-bold text-slate-700 block mb-0.5">
                    {t('outfit_builder.color_harmony')}:
                  </span>
                  <p className="text-slate-500 leading-relaxed bg-[#FAF9F6] p-2.5 rounded-xl border border-slate-100 font-light">
                    {compatibility?.color_harmony_verdict ||
                      'Add pieces to the canvas to evaluate color harmony.'}
                  </p>
                </div>

                <div>
                  <span className="font-bold text-slate-700 block mb-0.5">
                    {t('outfit_builder.aesthetic_synergy')}:
                  </span>
                  <p className="text-slate-500 leading-relaxed bg-[#FAF9F6] p-2.5 rounded-xl border border-slate-100 font-light">
                    {compatibility?.aesthetic_consistency_verdict ||
                      'Silhouette synergy is scored once the look contains items.'}
                  </p>
                </div>
              </div>

              {/* Actions */}
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <button
                  onClick={addAllToCart}
                  disabled={selectedItems.length === 0}
                  className="w-full py-3.5 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-40 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
                >
                  <BagIcon size={16} color="#FFFFFF" />
                  <span>Add Complete Look to Bag (${runningTotal.toFixed(2)})</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </DndContext>
    </div>
  );
};
