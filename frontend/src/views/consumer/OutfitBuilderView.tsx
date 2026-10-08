import { ActionButton, outcomeFromResult } from '../../components/common/ActionButton';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';
import { resolveMessage } from '../../i18n/messages';
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
import { useAuthStore } from '../../stores/authStore';
import { useQuery } from '@tanstack/react-query';
import { profileService } from '../../services/apiServices';
import {
  OutfitBuilderIcon,
  SparkleIcon,
  BagIcon,
  SavedLooksIcon,
  TryOnIcon,
  RulerIcon,
} from '../../components/icons/ConfitIcons';
import { FitScoreBadge } from '../../components/common/CommonComponents';
import { HonestProductImage } from '../../components/common/HonestProductImage';
import { Product } from '../../models';
import { formatMoney } from '../../i18n/format';
import { useTryOnAvailability } from '../../hooks/useTryOnAvailability';

type SlotKey = CanvasItem['slot'];

// BUILDER-02 FIX: the accessory slot is part of the canvas taxonomy
// (CanvasItem.slot already modelled it) but the UI omitted it, so clicking a
// clutch or tie added it to state invisibly — money left the total while no
// slot showed the piece. Accessories are now a first-class slot with the
// same replace/remove/validation rules as the four garment slots.
const SLOT_KEYS: SlotKey[] = ['outerwear', 'top', 'bottom', 'footwear', 'accessory'];

/**
 * The canvas slots. Module scope holds the KEY, never the English: a label here
 * would render in English inside the Arabic UI, which is the exact failure the
 * audit flagged. `t()` is applied at the render boundary.
 */
const SLOTS: Array<{ key: SlotKey; labelKey: string }> = [
  { key: 'outerwear', labelKey: 'outfit_builder.slot_outerwear' },
  { key: 'top', labelKey: 'outfit_builder.slot_top' },
  { key: 'bottom', labelKey: 'outfit_builder.slot_bottom' },
  { key: 'footwear', labelKey: 'outfit_builder.slot_footwear' },
  { key: 'accessory', labelKey: 'outfit_builder.slot_accessory' },
];

const SLOT_LABEL_KEY: Record<SlotKey, string> = Object.fromEntries(
  SLOTS.map((s) => [s.key, s.labelKey]),
) as Record<SlotKey, string>;

/** C04: the three starter formulas were hard-coded English module strings
 * rendered verbatim inside the Arabic UI. Keys only at module scope. */
const FORMULAS: Array<{ id: string; labelKey: string }> = [
  { id: 'tailored', labelKey: 'outfit_builder.formula_tailored' },
  { id: 'smart_casual', labelKey: 'outfit_builder.formula_smart_casual' },
  { id: 'evening', labelKey: 'outfit_builder.formula_evening' },
];

/** Shared focus ring: the old view had NO focus-visible treatment anywhere,
 * so keyboard users tabbed through an invisible interface. */
const FOCUS_RING =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] focus-visible:ring-offset-2';

/** C6 — a draggable catalog product. Also a real <button>: keyboard users
 * press Enter/Space to add via the same ViewModel path (the accessible
 * fallback for pointer drag). */
const DraggableProduct: React.FC<{
  product: Product;
  onAdd: (p: Product) => void;
}> = ({ product, onAdd }) => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? 'en';
  const { openTryOn, openRuler } = useUIStore();
  // Same availability gate as every other try-on entry point: the label and
  // the destination follow the live engine verdict, never a hard-coded hope.
  const tryOn = useTryOnAvailability();
  const tryOnKind = tryOn.ctaKind(true);

  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `product-${product.id}`,
    data: { product },
  });

  // The try-on control is a SIBLING of the draggable button, not a child.
  // Nesting interactive elements is invalid HTML, and in practice the drag
  // listeners on the outer button swallow the inner click, so a nested
  // control would render but not work. A positioned overlay keeps both
  // controls independently clickable and independently focusable.
  return (
    <div className="relative" style={{ transform: CSS.Translate.toString(transform) }}>
      <button
        ref={setNodeRef}
        type="button"
        {...listeners}
        {...attributes}
        onClick={() => onAdd(product)}
        aria-label={t('outfit_builder.add_to_outfit', { name: product.title })}
        className={`w-full text-start bg-[#FAF9F6] border rounded-2xl p-2 cursor-grab transition-all flex flex-col justify-between ${FOCUS_RING} ${
          isDragging
            ? 'opacity-50 border-[#C5A059] shadow-lg z-50'
            : 'border-slate-200/80 hover:border-[#C5A059] hover:shadow-sm'
        }`}
      >
        <div className="h-28 rounded-xl overflow-hidden bg-white mb-1.5 relative w-full">
          {/* C04: raw <img> → HonestProductImage. A dead catalog URL now shows
              the translated explicit placeholder, never a broken-image glyph. */}
          <HonestProductImage
            src={product.thumbnail_url}
            alt={product.title}
            unavailableLabel={t('common.image_unavailable')}
            className="w-full h-full object-cover"
          />
          <span className="absolute bottom-1 start-1 px-1.5 py-0.5 rounded bg-black/60 text-[9px] text-white font-medium">
            {t('outfit_builder.drag_or_enter')}
          </span>
        </div>
        <div>
          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider block truncate">
            {product.brand_name}
          </span>
          <span className="text-[11px] font-bold text-[#1B1F3B] line-clamp-1">{product.title}</span>
          {/* Was a raw interpolation of the base price with a hard-coded
              dollar sign, printing Latin digits inside the Arabic RTL page. */}
          <span className="text-xs font-bold text-[#1B1F3B] mt-0.5 block">
            {formatMoney(Math.round(product.base_price * 100), product.currency || 'USD', lang)}
          </span>
        </div>
      </button>

      {/* C04: the hit area was ~28px; WCAG 2.5.8 / house rule is 44px minimum.
          The button now owns a 44×44 target while the visual circle stays
          compact inside it. Positions are logical (end-*) so the control does
          not collide with the drag badge when the page flips to RTL. */}
      <button
        type="button"
        onClick={tryOn.gate({
          render: () => openTryOn(product),
          fitCheck: () => openRuler(product),
        })}
        disabled={tryOnKind === 'blocked'}
        title={
          tryOnKind === 'blocked' && tryOn.userMessage
            ? resolveMessage(tryOn.userMessage, t)
            : t(tryOnKind === 'render' ? 'tryon.cta_try_on' : 'tryon.cta_fit_check')
        }
        aria-label={t(tryOnKind === 'render' ? 'tryon.cta_try_on' : 'tryon.cta_fit_check')}
        className={`absolute top-0.5 end-0.5 h-11 w-11 flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed group/tryon ${FOCUS_RING}`}
      >
        <span className="h-7 w-7 rounded-full bg-[#1B1F3B]/90 group-hover/tryon:bg-[#C5A059] text-white group-hover/tryon:text-slate-950 shadow-sm backdrop-blur-sm transition-all flex items-center justify-center">
          {tryOnKind === 'render'
            ? <TryOnIcon size={13} color="currentColor" />
            : <RulerIcon size={13} color="currentColor" />}
        </span>
      </button>
    </div>
  );
};

/** C6 — a droppable outfit slot with keyboard removal and live highlighting. */
const DroppableSlot: React.FC<{
  slot: { key: SlotKey; labelKey: string };
  item?: CanvasItem;
  onRemove: (slot: SlotKey) => void;
}> = ({ slot, item, onRemove }) => {
  // The slot card is its own component, so it needs its own translator: the
  // container's `t` is not in scope here.
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? 'en';
  const { setNodeRef, isOver } = useDroppable({ id: `slot-${slot.key}` });

  return (
    <div
      ref={setNodeRef}
      data-testid={`slot-${slot.key}`}
      className={`h-64 rounded-2xl border transition-all p-3 flex flex-col justify-between relative group ${
        isOver
          ? 'border-[#C5A059] bg-[#C5A059]/10 ring-2 ring-[#C5A059]/40'
          : item
            ? 'border-[#C5A059]/60 bg-[#FAF9F6] shadow-sm'
            : 'border-dashed border-slate-300 bg-slate-50/50'
      }`}
    >
      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block text-center">
        {t(slot.labelKey)}
      </span>

      {item ? (
        <>
          {/* C04: was a 24×24 target — below the 44px minimum — anchored with
              a physical `right-2` that landed on the wrong side in RTL. */}
          <button
            onClick={() => onRemove(slot.key)}
            className={`absolute top-0 end-0 h-11 w-11 flex items-center justify-center z-10 group/remove ${FOCUS_RING}`}
            title={t('tryon.remove_item')}
            aria-label={t('outfit_builder.remove_item_aria', { item: item.product.title, slot: t(slot.labelKey) })}
          >
            <span className="w-6 h-6 rounded-full bg-black/60 group-hover/remove:bg-rose-600 text-white flex items-center justify-center text-xs transition-colors">
              ✕
            </span>
          </button>
          <div className="h-36 w-full rounded-xl overflow-hidden bg-white my-auto shadow-sm">
            <HonestProductImage
              src={item.product.thumbnail_url}
              alt={item.product.title}
              unavailableLabel={t('common.image_unavailable')}
              className="w-full h-full object-cover"
            />
          </div>
          <div className="text-center mt-1">
            <span className="text-[10px] text-slate-500 font-semibold block truncate">
              {item.product.brand_name}
            </span>
            <span className="text-xs font-bold text-[#1B1F3B] block truncate">
              {item.product.title}
            </span>
            {item.skuStatus === 'pending' && (
              <span role="status" className="text-[10px] text-slate-500 font-medium block">
                {t('outfit_builder.checking_size')}
              </span>
            )}
            {item.skuStatus === 'unavailable' && (
              <span className="text-[10px] text-rose-600 font-semibold block">{t('outfit_builder.no_size')}</span>
            )}
            {item.skuStatus === 'ready' && item.selectedSku && (
              <span className="text-[10px] text-slate-500 font-medium block">
                {t('outfit_builder.size_label', { size: item.selectedSku.size })}
              </span>
            )}
            <span className="text-xs font-bold text-[#A37E44]">
              {formatMoney(
                Math.round(item.product.base_price * 100),
                item.product.currency || 'USD',
                lang,
              )}
            </span>
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center my-auto text-center p-2 text-slate-500">
          <OutfitBuilderIcon size={22} color="#CBD5E1" />
          <span className="text-[11px] font-light mt-1 text-slate-500">
            {t('outfit_builder.drop_or_enter_hint')}
          </span>
        </div>
      )}
    </div>
  );
};

/** C04: the loading state was a bare English sentence. A skeleton that
 * mirrors the real page geometry (header row, 5 slot cards, summary column)
 * keeps the layout stable while the saved look loads. */
const BuilderSkeleton: React.FC<{ label: string }> = ({ label }) => (
  <div role="status" aria-label={label} data-testid="builder-skeleton" className="space-y-8 pb-24">
    <span className="sr-only">{label}</span>
    <div className="flex items-center justify-between border-b border-slate-200/80 pb-6">
      <div className="space-y-2">
        <div className="h-8 w-56 rounded-xl bg-slate-200/80 motion-safe:animate-pulse" />
        <div className="h-3 w-72 rounded bg-slate-100 motion-safe:animate-pulse" />
      </div>
      <div className="h-9 w-32 rounded-xl bg-slate-200/80 motion-safe:animate-pulse" />
    </div>
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
      <div className="lg:col-span-7">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {SLOT_KEYS.map((k) => (
            <div key={k} className="h-64 rounded-2xl bg-slate-100 motion-safe:animate-pulse" />
          ))}
        </div>
      </div>
      <div className="lg:col-span-5 space-y-6">
        <div className="h-40 rounded-3xl bg-slate-100 motion-safe:animate-pulse" />
        <div className="h-64 rounded-3xl bg-slate-100 motion-safe:animate-pulse" />
      </div>
    </div>
  </div>
);

export const OutfitBuilderView: React.FC = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? 'en';
  // OUTFIT-03: /outfits/:id now really edits that look instead of mounting an
  // empty canvas that silently saved a duplicate.
  const { id } = useParams<{ id?: string }>();
  const editingOutfitId = id && /^\d+$/.test(id) ? Number(id) : undefined;

  // C04: the outfit budget was a hard-coded 450 — on the EGP catalog (where a
  // single clutch costs 9,429 EGP) every look read "over budget", making the
  // whole module meaningless. The style profile already stores a REAL
  // budget_per_outfit_max; when the signed-in user has one, it drives the
  // tracker. Guests and users without a budget keep the previous default.
  const { isAuthenticated } = useAuthStore();
  const { data: usp } = useQuery({
    queryKey: ['profile', 'me', 'builder-budget'],
    queryFn: () => profileService.getProfile(),
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const profileBudget =
    usp &&
    'budget_per_outfit_max' in usp &&
    typeof usp.budget_per_outfit_max === 'number' &&
    usp.budget_per_outfit_max > 0
      ? usp.budget_per_outfit_max
      : undefined;

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
    isEvaluating,
    isSaving,
    isAddingAll,
    addItemToCanvas,
    isValidSlotForProduct,
    removeItemFromCanvas,
    clearCanvas,
    saveOutfit,
    addAllToCart,
    isLoadingExisting,
    loadError,
    verdict,
    isEditing,
  } = useOutfitBuilderViewModel(profileBudget ?? 450.0, editingOutfitId);

  const { products } = useCatalogViewModel();
  const { showToast } = useUIStore();

  // C04: every money figure on this page used a hard-coded "$" even though
  // the catalog prices carry their own currency (EGP in production). Totals
  // are formatted in the currency of the pieces themselves.
  const displayCurrency =
    selectedItems[0]?.product.currency || products[0]?.currency || 'USD';
  const formattedTotal = formatMoney(Math.round(runningTotal * 100), displayCurrency, lang);
  const formattedBudget = formatMoney(Math.round(userBudgetLimit * 100), displayCurrency, lang);

  // BUILDER-01 FIX: PointerSensor previously had NO activationConstraint, so
  // a drag activated on raw pointerdown. dnd-kit then swallowed the ensuing
  // click, so plain mouse clicks on the palette never reached the button's
  // onClick — the exact "items were dropped but the canvas stayed empty and
  // the total stayed $0.00" behaviour in the 2026-09-05 audit. A 6px distance
  // constraint is the standard click-vs-drag separator: a click (press+release
  // in place) fires onClick and adds the piece; moving 6px+ starts a real drag.
  // Keyboard: dnd-kit's KeyboardSensor DEFAULTS to Enter/Space BOTH starting a
  // drag — which hijacked Enter on the focused card (verified live: Enter left
  // Running Total at $0.00). Restricting the sensor's START key to Space frees
  // Enter for the button's native click → onAdd(): the focused card now adds
  // DIRECTLY on Enter, while Space still enables full keyboard dragging
  // (arrows to move, Space/Enter to drop) for those who want it.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, {
      keyboardCodes: { start: ['Space'], cancel: ['Escape'], end: ['Space', 'Enter'] },
    })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const product = (active.data.current as { product?: Product } | undefined)?.product;
    const slotKey = String(over.id).replace(/^slot-/, '') as SlotKey;
    if (!product || !SLOT_KEYS.includes(slotKey)) return;
    // Invalid drops (e.g. footwear onto the top slot) never touch state.
    // C04: this toast was a raw English template literal.
    if (!isValidSlotForProduct(product, slotKey)) {
      showToast(
        t('outfit_builder.wrong_slot', {
          title: product.title,
          slot: t(SLOT_LABEL_KEY[slotKey]),
        }),
        'error',
      );
      return;
    }
    addItemToCanvas(product, slotKey);
  };

  // C04: previously ALWAYS announced success ("formula added") even when the
  // catalog had no matching pieces and the canvas stayed empty — a fake
  // success. The toast now reports what actually happened.
  const applyStarterFormula = (formulaLabel: string) => {
    clearCanvas();
    setTargetOccasion(formulaLabel);
    setOutfitTitle(t('outfit_builder.formula_title', { name: formulaLabel }));
    let added = 0;
    SLOT_KEYS.forEach((slot) => {
      const product = products.find((item) => isValidSlotForProduct(item, slot));
      if (product) {
        addItemToCanvas(product, slot);
        added += 1;
      }
    });
    if (added > 0) {
      showToast(t('outfit_builder.formula_added'), 'success');
    } else {
      showToast(t('outfit_builder.formula_nothing_added'), 'error');
    }
  };

  if (isLoadingExisting) {
    return <BuilderSkeleton label={t('outfit_builder.loading_look')} />;
  }

  if (loadError) {
    return (
      <div className="py-24 text-center space-y-3">
        <h1 className="font-serif text-2xl text-[#1B1F3B]">
          {resolveMessage(loadError, t)}
        </h1>
        <Link
          to="/my-looks"
          className={`inline-block px-4 py-2 rounded-xl border border-slate-300 text-xs font-semibold hover:bg-slate-100 ${FOCUS_RING}`}
        >
          {t('outfit_builder.back_to_my_looks')}
        </Link>
      </div>
    );
  }

  // C04: the edit flow can hydrate an occasion saved in another language (or
  // from an older release). Without this, the <select> silently displayed the
  // first option while the state held the real value — the user saw a lie.
  const occasionOptionKeys = [
    'outfit_builder.occasion_smart_casual',
    'outfit_builder.occasion_boardroom',
    'outfit_builder.occasion_cocktail',
    'outfit_builder.occasion_weekend',
    'outfit_builder.occasion_gala',
  ];
  const occasionValues = occasionOptionKeys.map((k) => t(k));
  // Any hydrated/derived value outside the canonical five (legacy language,
  // formula name, older release) gets its own option so the select never
  // displays a value different from the state it holds.
  const occasionIsLegacy = targetOccasion !== '' && !occasionValues.includes(targetOccasion);

  return (
    <div className="space-y-8 pb-24">
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
            className={`px-4 py-2 min-h-[44px] rounded-xl border border-slate-300 hover:bg-slate-100 disabled:opacity-40 text-xs font-semibold text-slate-700 transition-all ${FOCUS_RING}`}
          >
            {t('outfit_builder.clear_canvas')}
          </button>
          {/* Spec 08: unified kinetic CTA. The machine owns pending (one
              in-flight save, focus retained), and the viewmodel's
              true/false/undefined verdict maps to an HONEST outcome:
              success only when the server saved, error stays actionable,
              and early validation exits ("handled") change nothing here —
              their toast is the surface that explains. Also removes the
              previously hardcoded English "Saving..."/"Update look". */}
          <ActionButton
            metricsId={isEditing ? 'builder.update_look' : 'builder.save_look'}
            onAction={async () => outcomeFromResult(await saveOutfit())}
            disabled={selectedItems.length === 0 || verdict?.is_valid === false}
            labels={{
              idle: isEditing
                ? t('outfit_builder.update_look')
                : t('outfit_builder.save_outfit'),
              pending: t('outfit_builder.saving'),
              success: t('outfit_builder.saved_confirm'),
              error: t('outfit_builder.save_failed_retry'),
            }}
            icon={<SavedLooksIcon size={16} color="#0C0E1E" />}
            data-testid="save-look-cta"
            className="px-5 py-2 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] disabled:opacity-40 text-slate-950 font-bold text-xs shadow-sm transition-all"
          />
        </div>
      </div>

      <section className="rounded-3xl border border-[#C5A059]/25 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-[#7A5C28]">{t('outfit_builder.guided_mode')}</span>
            <h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">{t('outfit_builder.replace_hint')}</h2>
            <p className="mt-1 text-sm font-light text-slate-500">
              {t('outfit_builder.guided_intro')}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {FORMULAS.map((formula) => (
              <button
                key={formula.id}
                onClick={() => applyStarterFormula(t(formula.labelKey))}
                className={`rounded-2xl bg-[#1B1F3B] px-4 py-2.5 min-h-[44px] text-xs font-bold text-white transition hover:bg-[#C5A059] hover:text-[#0C0E1E] ${FOCUS_RING}`}
              >
                {t('outfit_builder.use_formula', { name: t(formula.labelKey) })}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* OUTFIT-04: the server's composition verdict, shown verbatim. A
          rejected combination always states WHY and which slot is at fault,
          instead of a disabled button with no explanation. */}
      {verdict && (!verdict.is_valid || verdict.warnings.length > 0) ? (
        <div
          role={verdict.is_valid ? 'status' : 'alert'}
          className={`rounded-2xl border p-4 text-xs space-y-1 ${
            verdict.is_valid
              ? 'border-amber-200 bg-amber-50 text-amber-800'
              : 'border-rose-200 bg-rose-50 text-rose-800'
          }`}
        >
          <span className="font-bold uppercase tracking-wider text-[10px]">
            {verdict.is_valid
              ? t('outfit_builder.verdict_warning_title')
              : t('outfit_builder.verdict_blocked_title')}
          </span>
          {verdict.violations.map((v) => (
            <p key={v.code + v.positions.join()}>{v.message}</p>
          ))}
          {verdict.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      ) : null}

      {/* C6: one DndContext wraps palette + canvas so drops are real state transitions */}
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        {/* Main Canvas & Metrics Split */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left: Interactive Outfit Canvas (7 cols) */}
          <div className="lg:col-span-7 space-y-6">
            {/* Canvas Title & Occasion */}
            <div className="bg-white rounded-3xl border border-slate-200/80 p-5 shadow-sm space-y-3">
              <div className="flex flex-col sm:flex-row gap-3">
                {/* The name field previously had only a placeholder to identify
                    it. Chrome does expose the placeholder as the accessible name
                    (measured 2026-09-23 with the CDP accessibility tree:
                    role=textbox, name="Give your look a name..."), but it is
                    announced as a hint and disappears the moment the user types,
                    leaving the field unnamed — WCAG 3.3.2 Labels or Instructions.
                    `aria-label` gives it a name that survives typing. */}
                <input
                  type="text"
                  value={outfitTitle}
                  onChange={(e) => setOutfitTitle(e.target.value)}
                  placeholder={t('outfit_builder.name_placeholder')}
                  aria-label={t('outfit_builder.name_label')}
                  className="flex-1 font-serif text-base font-bold text-[#1B1F3B] border-b border-slate-200 focus:outline-none focus:border-[#C5A059] py-1"
                />
                <select
                  aria-label={t('outfit_builder.target_occasion')}
                  value={targetOccasion}
                  onChange={(e) => setTargetOccasion(e.target.value)}
                  className="text-xs font-semibold bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 min-h-[44px] focus:outline-none focus:border-[#C5A059]"
                >
                  {/* Preserve a hydrated value that is not one of the current
                      locale's options (saved in another language, or a formula
                      occasion) instead of silently displaying the wrong one. */}
                  {occasionIsLegacy && <option value={targetOccasion}>{targetOccasion}</option>}
                  {occasionOptionKeys.map((k) => (
                    <option key={k} value={t(k)}>{t(k)}</option>
                  ))}
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
            <div className="bg-white rounded-3xl border border-slate-200/80 p-5 shadow-sm space-y-4">
              <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
                {t('outfit_builder.drop_garment_here')}
              </h3>
              {products.length === 0 ? (
                <p className="py-10 text-center text-sm font-light text-slate-500">
                  {t('outfit_builder.palette_empty')}
                </p>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 max-h-96 overflow-y-auto pe-1">
                  {products.map((p) => (
                    <DraggableProduct key={p.id} product={p} onAdd={(prod) => addItemToCanvas(prod)} />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right: Live Running Budget Tracker & Harmony Score (5 cols).
              C04: the header literally said "Sticky Look Summary" while the
              column scrolled away — the label lied. It is now actually sticky
              on desktop. */}
          <div className="lg:col-span-5 space-y-6 lg:sticky lg:top-24 self-start">
            {/* Live Budget Tracker Module */}
            <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-sm space-y-4">
              <div className="flex justify-between items-center pb-3 border-b border-slate-100">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  {t('outfit_builder.look_summary')}
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
                  <span data-testid="builder-running-total" className="text-2xl font-serif font-black text-[#1B1F3B]">
                    {formattedTotal}
                  </span>
                </div>
                <div className="flex justify-between text-xs text-slate-500">
                  <span>{t('outfit_builder.allocated_budget')}:</span>
                  <span data-testid="builder-budget-limit">{formattedBudget}</span>
                </div>

                {/* Progress Bar — now a real progressbar for AT users, not a
                    purely visual div. */}
                <div
                  role="progressbar"
                  aria-label={t('outfit_builder.budget_status')}
                  aria-valuemin={0}
                  aria-valuemax={userBudgetLimit}
                  aria-valuenow={Math.min(userBudgetLimit, Math.round(runningTotal))}
                  aria-valuetext={formattedTotal}
                  className="w-full h-2.5 rounded-full bg-slate-100 overflow-hidden mt-2"
                >
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
            <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-sm space-y-4">
              <div className="flex justify-between items-center pb-3 border-b border-slate-100">
                <div className="flex items-center gap-1.5">
                  <SparkleIcon size={16} color="#C5A059" />
                  <span className="text-xs font-bold text-[#1B1F3B]">
                    {t('outfit_builder.compatibility_rating')}
                  </span>
                </div>
                <FitScoreBadge
                  score={compatibility?.compatibility_score ?? 0}
                  label={t('outfit_builder.match_label')}
                  verdict={compatibility?.color_harmony_type || t('outfit_builder.awaiting_items')}
                />
              </div>

              {/* C04: the viewmodel exposed isEvaluating but the view ignored
                  it — stale verdicts displayed as current while the server was
                  still scoring. An honest in-flight indicator. */}
              {isEvaluating && (
                <p role="status" className="text-[11px] font-medium text-slate-500">
                  {t('outfit_builder.evaluating')}
                </p>
              )}

              {/* C04: scoring requires an account — guests get an HONEST
                  sentence instead of background 401s that popped the login
                  modal mid-composition (observed on production). */}
              <div className="space-y-3 text-xs">
                <div>
                  <span className="font-bold text-slate-700 block mb-0.5">
                    {t('outfit_builder.color_harmony')}:
                  </span>
                  <p className="text-slate-500 leading-relaxed bg-[#FAF9F6] p-2.5 rounded-xl border border-slate-100 font-light">
                    {compatibility?.color_harmony_verdict ||
                      t(isAuthenticated ? 'outfit_builder.harmony_empty' : 'outfit_builder.sign_in_to_evaluate')}
                  </p>
                </div>

                <div>
                  <span className="font-bold text-slate-700 block mb-0.5">
                    {t('outfit_builder.aesthetic_synergy')}:
                  </span>
                  <p className="text-slate-500 leading-relaxed bg-[#FAF9F6] p-2.5 rounded-xl border border-slate-100 font-light">
                    {compatibility?.aesthetic_consistency_verdict ||
                      t(isAuthenticated ? 'outfit_builder.synergy_empty' : 'outfit_builder.sign_in_to_evaluate')}
                  </p>
                </div>
              </div>

              {/* Actions */}
              <div className="pt-3 border-t border-slate-100 space-y-2">
                {/* C04: disabled + aria-busy while the batch is in flight —
                    a double-click must never duplicate the bag. */}
                <button
                  onClick={addAllToCart}
                  disabled={selectedItems.length === 0 || isAddingAll}
                  aria-busy={isAddingAll}
                  data-testid="builder-add-all"
                  className={`w-full py-3.5 min-h-[48px] rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-40 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2 ${FOCUS_RING}`}
                >
                  <BagIcon size={16} color="#FFFFFF" />
                  <span>{t('outfit_builder.add_look_to_bag', { total: formattedTotal })}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </DndContext>
    </div>
  );
};
