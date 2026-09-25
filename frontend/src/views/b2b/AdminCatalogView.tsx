import React from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import {
  adminService,
  type AdminCatalogProductInput,
  type AdminCatalogProductPatch,
} from '../../services/apiServices';
import type {
  AdminCatalogBrandSummary,
  AdminCatalogProduct,
  AdminCatalogSnapshot,
  ProductSKU,
} from '../../models';
import { useUIStore } from '../../stores/uiStore';
import { EmptyState, LoadingSpinner } from '../../components/common/CommonComponents';

const fieldClass = 'min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-[#B8935A] focus:outline-none focus:ring-2 focus:ring-[#B8935A]/30';
const buttonFocus = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A] focus-visible:ring-offset-2';

type Tab = 'products' | 'inventory' | 'placements' | 'imports';
type ProductFormState = {
  category_id: string;
  title: string;
  title_ar: string;
  description: string;
  description_ar: string;
  base_price: string;
  currency: string;
  material: string;
  care_instructions: string;
  color_family: string;
  dominant_hex: string;
  thumbnail_url: string;
  style_tags: string;
  occasion_tags: string;
  is_featured: boolean;
  sku_code: string;
  sku_size: string;
  sku_color: string;
  sku_color_hex: string;
  sku_stock: string;
  sku_price_override: string;
};

const emptyForm = (categoryId?: number): ProductFormState => ({
  category_id: categoryId ? String(categoryId) : '',
  title: '',
  title_ar: '',
  description: '',
  description_ar: '',
  base_price: '',
  currency: 'EGP',
  material: '',
  care_instructions: '',
  color_family: '',
  dominant_hex: '#1B1F3B',
  thumbnail_url: '',
  style_tags: '',
  occasion_tags: '',
  is_featured: false,
  sku_code: '',
  sku_size: '',
  sku_color: '',
  sku_color_hex: '#1B1F3B',
  sku_stock: '0',
  sku_price_override: '',
});

const formFromProduct = (product: AdminCatalogProduct): ProductFormState => ({
  category_id: String(product.category_id),
  title: product.title,
  title_ar: product.title_ar,
  description: product.description,
  description_ar: product.description_ar,
  base_price: String(product.base_price),
  currency: product.currency,
  material: product.material ?? '',
  care_instructions: product.care_instructions ?? '',
  color_family: product.color_family,
  dominant_hex: product.dominant_hex ?? '#1B1F3B',
  thumbnail_url: product.thumbnail_url,
  style_tags: product.style_tags.join(', '),
  occasion_tags: product.occasion_tags.join(', '),
  is_featured: product.is_featured,
  sku_code: '',
  sku_size: '',
  sku_color: '',
  sku_color_hex: '#1B1F3B',
  sku_stock: '0',
  sku_price_override: '',
});

const listFromText = (value: string) => value
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean);

const errorText = (error: unknown, fallback: string) =>
  error instanceof Error && error.message ? error.message : fallback;

const StockEditor: React.FC<{
  brandId: number;
  sku: ProductSKU;
  onSaved: () => Promise<void>;
}> = ({ brandId, sku, onSaved }) => {
  const { t } = useTranslation();
  const { showToast } = useUIStore();
  const [stock, setStock] = React.useState(String(sku.stock_level));
  const [price, setPrice] = React.useState(
    sku.price_override === null || sku.price_override === undefined ? '' : String(sku.price_override),
  );
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    setStock(String(sku.stock_level));
    setPrice(sku.price_override === null || sku.price_override === undefined ? '' : String(sku.price_override));
  }, [sku.stock_level, sku.price_override]);

  const save = async () => {
    setSaving(true);
    try {
      await adminService.updateCatalogSKU(brandId, sku.id, {
        stock_level: Number(stock),
        price_override: price.trim() ? Number(price) : null,
      });
      await onSaved();
      showToast(t('admin_catalog.toast_sku_saved'), 'success');
    } catch (error) {
      showToast(errorText(error, t('admin_catalog.error_mutation')), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-[1fr_8rem_9rem_auto] sm:items-end">
      <div className="min-w-0">
        <div className="truncate font-mono text-xs font-bold text-slate-800">{sku.sku_code}</div>
        <div className="mt-1 text-xs text-slate-500">{sku.size} · {sku.color}</div>
      </div>
      <label className="text-xs font-semibold text-slate-700">
        {t('admin_catalog.stock')}
        <input
          aria-label={t('admin_catalog.stock_for', { sku: sku.sku_code })}
          type="number"
          min="0"
          max="100000"
          required
          value={stock}
          onChange={(event) => setStock(event.target.value)}
          className={`${fieldClass} mt-1`}
        />
      </label>
      <label className="text-xs font-semibold text-slate-700">
        {t('admin_catalog.price_override')}
        <input
          aria-label={t('admin_catalog.price_for', { sku: sku.sku_code })}
          type="number"
          min="0.01"
          step="0.01"
          value={price}
          onChange={(event) => setPrice(event.target.value)}
          className={`${fieldClass} mt-1`}
          placeholder={t('admin_catalog.base_price_fallback')}
        />
      </label>
      <button
        type="button"
        onClick={save}
        disabled={saving || stock === ''}
        className={`min-h-11 rounded-xl bg-[#1B1F3B] px-4 py-2 text-xs font-bold text-white disabled:opacity-50 ${buttonFocus}`}
      >
        {saving ? t('admin_catalog.saving') : t('admin_catalog.save')}
      </button>
    </div>
  );
};

export const AdminCatalogView: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { showToast } = useUIStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const [brands, setBrands] = React.useState<AdminCatalogBrandSummary[]>([]);
  const [selectedBrandId, setSelectedBrandId] = React.useState<number | null>(null);
  const [snapshot, setSnapshot] = React.useState<AdminCatalogSnapshot | null>(null);
  const [loadingBrands, setLoadingBrands] = React.useState(true);
  const [loadingSnapshot, setLoadingSnapshot] = React.useState(false);
  const [error, setError] = React.useState('');
  const [tab, setTab] = React.useState<Tab>(() => {
    const requested = searchParams.get('tab');
    return requested === 'inventory' || requested === 'placements' || requested === 'imports'
      ? requested
      : 'products';
  });
  const [editing, setEditing] = React.useState<AdminCatalogProduct | 'new' | null>(null);
  const [form, setForm] = React.useState<ProductFormState>(() => emptyForm());
  const [saving, setSaving] = React.useState(false);
  // Preserve only the direct-entry selection. Writing brand_id back to the URL
  // must not re-run the organization request and flash the entire page away.
  const requestedBrandId = React.useRef(Number(searchParams.get('brand_id')));

  const loadBrands = React.useCallback(async () => {
    setLoadingBrands(true);
    setError('');
    try {
      const rows = await adminService.getCatalogBrands();
      setBrands(rows);
      if (!rows.length) {
        setSelectedBrandId(null);
        return;
      }
      const requestedBrand = rows.find((row) => row.id === requestedBrandId.current);
      // Select the most populated real tenant on first entry so an existing
      // catalog is visible immediately; all other brands remain selectable.
      const initial = requestedBrand ?? [...rows].sort(
        (a, b) => b.product_count - a.product_count || a.brand_name.localeCompare(b.brand_name),
      )[0];
      setSelectedBrandId((current) => current && rows.some((row) => row.id === current) ? current : initial.id);
    } catch (loadError) {
      setError(errorText(loadError, t('admin_catalog.error_load_brands')));
    } finally {
      setLoadingBrands(false);
    }
  }, [t]);

  const loadSnapshot = React.useCallback(async (brandId: number) => {
    setLoadingSnapshot(true);
    setError('');
    try {
      const result = await adminService.getCatalogSnapshot(brandId);
      setSnapshot(result);
    } catch (loadError) {
      setSnapshot(null);
      setError(errorText(loadError, t('admin_catalog.error_load_snapshot')));
    } finally {
      setLoadingSnapshot(false);
    }
  }, [t]);

  React.useEffect(() => { void loadBrands(); }, [loadBrands]);
  React.useEffect(() => {
    if (selectedBrandId !== null) void loadSnapshot(selectedBrandId);
  }, [selectedBrandId, loadSnapshot]);

  React.useEffect(() => {
    if (selectedBrandId === null || searchParams.get('brand_id') === String(selectedBrandId)) return;
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set('brand_id', String(selectedBrandId));
      return next;
    }, { replace: true });
  }, [selectedBrandId, searchParams, setSearchParams]);

  const refresh = React.useCallback(async () => {
    if (selectedBrandId !== null) await loadSnapshot(selectedBrandId);
  }, [selectedBrandId, loadSnapshot]);

  const updateForm = (field: keyof ProductFormState) => (
    event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    const value = event.target instanceof HTMLInputElement && event.target.type === 'checkbox'
      ? event.target.checked
      : event.target.value;
    setForm((previous) => ({ ...previous, [field]: value }));
  };

  const startCreate = () => {
    setEditing('new');
    setForm(emptyForm(snapshot?.categories[0]?.id));
  };
  const startEdit = (product: AdminCatalogProduct) => {
    setEditing(product);
    setForm(formFromProduct(product));
  };

  const submitProduct = async (event: React.FormEvent) => {
    event.preventDefault();
    if (selectedBrandId === null || !editing) return;
    setSaving(true);
    const common: AdminCatalogProductPatch = {
      category_id: Number(form.category_id),
      title: form.title,
      title_ar: form.title_ar,
      description: form.description,
      description_ar: form.description_ar,
      base_price: Number(form.base_price),
      currency: form.currency.toUpperCase(),
      material: form.material || null,
      care_instructions: form.care_instructions || null,
      color_family: form.color_family,
      dominant_hex: form.dominant_hex,
      thumbnail_url: form.thumbnail_url,
      // The form edits the cover URL, not the full gallery. Preserve persisted
      // gallery assets during metadata edits instead of silently deleting them.
      images: editing === 'new' ? [] : editing.images,
      style_tags: listFromText(form.style_tags),
      occasion_tags: listFromText(form.occasion_tags),
      is_featured: form.is_featured,
    };
    try {
      if (editing === 'new') {
        const payload: AdminCatalogProductInput = {
          ...common,
          skus: [{
            sku_code: form.sku_code,
            size: form.sku_size,
            color: form.sku_color,
            color_hex: form.sku_color_hex,
            stock_level: Number(form.sku_stock),
            ...(form.sku_price_override.trim()
              ? { price_override: Number(form.sku_price_override) }
              : {}),
          }],
        };
        await adminService.createCatalogProduct(selectedBrandId, payload);
        showToast(t('admin_catalog.toast_product_created'), 'success');
      } else {
        await adminService.updateCatalogProduct(selectedBrandId, editing.id, common);
        showToast(t('admin_catalog.toast_product_updated'), 'success');
      }
      setEditing(null);
      await Promise.all([refresh(), loadBrands()]);
    } catch (mutationError) {
      showToast(errorText(mutationError, t('admin_catalog.error_mutation')), 'error');
    } finally {
      setSaving(false);
    }
  };

  const setProductActive = async (product: AdminCatalogProduct, active: boolean) => {
    if (selectedBrandId === null) return;
    if (!active && !window.confirm(t('admin_catalog.deactivate_confirm', { title: product.title }))) return;
    setSaving(true);
    try {
      if (active) await adminService.reactivateCatalogProduct(selectedBrandId, product.id);
      else await adminService.deactivateCatalogProduct(selectedBrandId, product.id);
      showToast(t(active ? 'admin_catalog.toast_product_reactivated' : 'admin_catalog.toast_product_deactivated'), 'success');
      await Promise.all([refresh(), loadBrands()]);
    } catch (mutationError) {
      showToast(errorText(mutationError, t('admin_catalog.error_mutation')), 'error');
    } finally {
      setSaving(false);
    }
  };

  if (loadingBrands) return <LoadingSpinner text={t('admin_catalog.loading')} />;
  if (error && !brands.length) {
    return <EmptyState title={t('admin_catalog.unavailable')} description={error} actionText={t('admin_catalog.retry')} onAction={loadBrands} />;
  }

  const tabs: Array<{ id: Tab; label: string; count: number }> = [
    { id: 'products', label: t('admin_catalog.tab_products'), count: snapshot?.products.length ?? 0 },
    { id: 'inventory', label: t('admin_catalog.tab_inventory'), count: snapshot?.brand.sku_count ?? 0 },
    { id: 'placements', label: t('admin_catalog.tab_placements'), count: snapshot?.placements.length ?? 0 },
    { id: 'imports', label: t('admin_catalog.tab_imports'), count: snapshot?.imports.length ?? 0 },
  ];

  return (
    <div className="space-y-7 pb-20">
      <section className="overflow-hidden rounded-3xl bg-[#10152C] p-6 text-white shadow-xl sm:p-8">
        <div className="max-w-3xl">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#E2BF70]">{t('admin_catalog.eyebrow')}</p>
          <h1 className="mt-2 font-serif text-3xl font-black sm:text-4xl">{t('admin_catalog.title')}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-300">{t('admin_catalog.lede')}</p>
        </div>
        <div className="mt-6 max-w-xl">
          <label htmlFor="admin-brand-selector" className="mb-2 block text-xs font-bold text-slate-200">
            {t('admin_catalog.select_brand')}
          </label>
          <select
            id="admin-brand-selector"
            value={selectedBrandId ?? ''}
            onChange={(event) => {
              setEditing(null);
              setSelectedBrandId(Number(event.target.value));
            }}
            className={`${fieldClass} border-slate-600 bg-white text-slate-900`}
          >
            {brands.map((brand) => (
              <option key={brand.id} value={brand.id}>
                {brand.brand_name} · {t('admin_catalog.selector_counts', { products: brand.product_count, skus: brand.sku_count })}
              </option>
            ))}
          </select>
        </div>
      </section>

      {error && (
        <div role="alert" className="flex flex-col gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 sm:flex-row sm:items-center sm:justify-between">
          <span>{error}</span>
          <button type="button" onClick={refresh} className={`min-h-11 rounded-xl border border-rose-300 px-4 font-bold ${buttonFocus}`}>
            {t('admin_catalog.retry')}
          </button>
        </div>
      )}

      {loadingSnapshot ? <LoadingSpinner text={t('admin_catalog.loading_snapshot')} /> : snapshot && (
        <>
          <section aria-label={t('admin_catalog.summary_label')} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {[
              [t('admin_catalog.metric_products'), snapshot.brand.product_count],
              [t('admin_catalog.metric_active'), snapshot.brand.active_product_count],
              [t('admin_catalog.metric_skus'), snapshot.brand.sku_count],
              [t('admin_catalog.metric_stores'), snapshot.brand.store_count],
              [t('admin_catalog.metric_placements'), snapshot.brand.placement_count],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</div>
                <div className="mt-1 font-serif text-2xl font-black text-[#1B1F3B]">{value}</div>
              </div>
            ))}
          </section>

          <div className="flex gap-2 overflow-x-auto border-b border-slate-200 pb-2" role="tablist" aria-label={t('admin_catalog.tabs_label')}>
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id)}
                className={`min-h-11 shrink-0 rounded-xl px-4 text-sm font-bold ${buttonFocus} ${tab === item.id ? 'bg-[#1B1F3B] text-white' : 'bg-white text-slate-700 hover:bg-slate-100'}`}
              >
                {item.label} <span className="ms-1 opacity-70">({item.count})</span>
              </button>
            ))}
          </div>

          {tab === 'products' && (
            <section className="space-y-5" aria-labelledby="catalog-products-heading">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 id="catalog-products-heading" className="font-serif text-2xl font-bold text-[#1B1F3B]">{t('admin_catalog.products_heading')}</h2>
                  <p className="mt-1 text-sm text-slate-500">{t('admin_catalog.products_help')}</p>
                </div>
                <button type="button" onClick={startCreate} className={`min-h-11 rounded-xl bg-[#B8935A] px-5 py-2 text-sm font-bold text-white hover:bg-[#9C7842] ${buttonFocus}`}>
                  {t('admin_catalog.add_product')}
                </button>
              </div>

              {editing && (
                <form onSubmit={submitProduct} className="space-y-5 rounded-3xl border border-[#DCC8A5] bg-[#FFFCF5] p-5 shadow-sm" aria-label={t(editing === 'new' ? 'admin_catalog.create_form_label' : 'admin_catalog.edit_form_label')}>
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="font-serif text-xl font-bold text-[#1B1F3B]">{t(editing === 'new' ? 'admin_catalog.create_heading' : 'admin_catalog.edit_heading')}</h3>
                    <button type="button" onClick={() => setEditing(null)} className={`min-h-11 rounded-xl px-3 text-sm font-bold text-slate-600 hover:bg-white ${buttonFocus}`}>{t('admin_catalog.cancel')}</button>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_title')}<input required maxLength={255} value={form.title} onChange={updateForm('title')} className={`${fieldClass} mt-1`} /></label>
                    <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_title_ar')}<input required dir="rtl" maxLength={255} value={form.title_ar} onChange={updateForm('title_ar')} className={`${fieldClass} mt-1`} /></label>
                    <label className="text-xs font-bold text-slate-700 md:col-span-2">{t('admin_catalog.field_description')}<textarea required rows={3} value={form.description} onChange={updateForm('description')} className={`${fieldClass} mt-1`} /></label>
                    <label className="text-xs font-bold text-slate-700 md:col-span-2">{t('admin_catalog.field_description_ar')}<textarea required dir="rtl" rows={3} value={form.description_ar} onChange={updateForm('description_ar')} className={`${fieldClass} mt-1`} /></label>
                    <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_category')}<select required value={form.category_id} onChange={updateForm('category_id')} className={`${fieldClass} mt-1`}>{snapshot.categories.map((category) => <option key={category.id} value={category.id}>{i18n.dir() === 'rtl' ? category.name_ar : category.name}</option>)}</select></label>
                    <div className="grid grid-cols-[1fr_7rem] gap-3">
                      <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_price')}<input required type="number" min="0.01" step="0.01" value={form.base_price} onChange={updateForm('base_price')} className={`${fieldClass} mt-1`} /></label>
                      <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_currency')}<input required pattern="[A-Za-z]{3}" maxLength={3} value={form.currency} onChange={updateForm('currency')} className={`${fieldClass} mt-1 uppercase`} /></label>
                    </div>
                    <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_material')}<input value={form.material} onChange={updateForm('material')} className={`${fieldClass} mt-1`} /></label>
                    <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_care')}<input value={form.care_instructions} onChange={updateForm('care_instructions')} className={`${fieldClass} mt-1`} /></label>
                    <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_color_family')}<input required value={form.color_family} onChange={updateForm('color_family')} className={`${fieldClass} mt-1`} /></label>
                    <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_color_hex')}<input required type="color" value={form.dominant_hex} onChange={updateForm('dominant_hex')} className={`${fieldClass} mt-1 p-1`} /></label>
                    <label className="text-xs font-bold text-slate-700 md:col-span-2">{t('admin_catalog.field_image')}<input required type="url" value={form.thumbnail_url} onChange={updateForm('thumbnail_url')} className={`${fieldClass} mt-1`} placeholder="https://…" /></label>
                    <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_style_tags')}<input value={form.style_tags} onChange={updateForm('style_tags')} className={`${fieldClass} mt-1`} /></label>
                    <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_occasion_tags')}<input value={form.occasion_tags} onChange={updateForm('occasion_tags')} className={`${fieldClass} mt-1`} /></label>
                    <label className="flex min-h-11 items-center gap-2 text-xs font-bold text-slate-700 md:col-span-2"><input type="checkbox" checked={form.is_featured} onChange={updateForm('is_featured')} className="h-5 w-5" />{t('admin_catalog.field_featured')}</label>
                  </div>

                  {editing === 'new' && (
                    <fieldset className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-3">
                      <legend className="px-2 text-sm font-bold text-[#1B1F3B]">{t('admin_catalog.initial_sku')}</legend>
                      <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_sku')}<input required pattern="[A-Za-z0-9_-]{3,100}" value={form.sku_code} onChange={updateForm('sku_code')} className={`${fieldClass} mt-1`} /></label>
                      <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_size')}<input required value={form.sku_size} onChange={updateForm('sku_size')} className={`${fieldClass} mt-1`} /></label>
                      <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_sku_color')}<input required value={form.sku_color} onChange={updateForm('sku_color')} className={`${fieldClass} mt-1`} /></label>
                      <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_stock')}<input required type="number" min="0" max="100000" value={form.sku_stock} onChange={updateForm('sku_stock')} className={`${fieldClass} mt-1`} /></label>
                      <label className="text-xs font-bold text-slate-700">{t('admin_catalog.price_override')}<input type="number" min="0.01" step="0.01" value={form.sku_price_override} onChange={updateForm('sku_price_override')} className={`${fieldClass} mt-1`} /></label>
                      <label className="text-xs font-bold text-slate-700">{t('admin_catalog.field_color_hex')}<input required type="color" value={form.sku_color_hex} onChange={updateForm('sku_color_hex')} className={`${fieldClass} mt-1 p-1`} /></label>
                    </fieldset>
                  )}
                  <button type="submit" disabled={saving} className={`min-h-11 rounded-xl bg-[#1B1F3B] px-6 py-2 text-sm font-bold text-white disabled:opacity-50 ${buttonFocus}`}>{saving ? t('admin_catalog.saving') : t(editing === 'new' ? 'admin_catalog.create_product' : 'admin_catalog.save_changes')}</button>
                </form>
              )}

              {snapshot.products.length === 0 ? (
                <EmptyState title={t('admin_catalog.no_products')} description={t('admin_catalog.no_products_help')} actionText={t('admin_catalog.add_product')} onAction={startCreate} />
              ) : (
                <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                  {snapshot.products.map((product) => (
                    <article key={product.id} className={`overflow-hidden rounded-3xl border bg-white shadow-sm ${product.is_active ? 'border-slate-200' : 'border-slate-300 opacity-75'}`}>
                      <img src={product.thumbnail_url} alt="" className="h-44 w-full bg-slate-100 object-cover" />
                      <div className="space-y-3 p-5">
                        <div className="flex items-start justify-between gap-3">
                          <div><h3 className="font-serif text-lg font-bold text-[#1B1F3B]">{i18n.dir() === 'rtl' ? product.title_ar : product.title}</h3><p className="text-xs text-slate-500">{product.category_name}</p></div>
                          <span className={`rounded-full px-2 py-1 text-[10px] font-bold uppercase ${product.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-700'}`}>{t(product.is_active ? 'admin_catalog.active' : 'admin_catalog.inactive')}</span>
                        </div>
                        <div className="flex items-center justify-between text-sm"><span className="font-mono font-bold text-[#8A6A2F]">{product.currency} {product.base_price.toLocaleString()}</span><span className="text-xs text-slate-500">{t('admin_catalog.sku_count', { count: product.skus.length })}</span></div>
                        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                          <button type="button" onClick={() => startEdit(product)} className={`min-h-11 rounded-xl border border-slate-300 px-4 text-xs font-bold text-slate-700 hover:border-[#B8935A] ${buttonFocus}`}>{t('admin_catalog.edit')}</button>
                          <button type="button" disabled={saving} onClick={() => void setProductActive(product, !product.is_active)} className={`min-h-11 rounded-xl px-4 text-xs font-bold ${buttonFocus} ${product.is_active ? 'bg-rose-50 text-rose-700 hover:bg-rose-100' : 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100'}`}>{t(product.is_active ? 'admin_catalog.deactivate' : 'admin_catalog.reactivate')}</button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}

          {tab === 'inventory' && (
            <section className="space-y-5">
              <div><h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">{t('admin_catalog.inventory_heading')}</h2><p className="mt-1 text-sm text-slate-500">{t('admin_catalog.inventory_help')}</p></div>
              {snapshot.inventory.flatMap((product) => product.skus.map((sku) => ({ product, sku }))).map(({ product, sku }) => (
                <div key={sku.id} className="space-y-2">
                  <div className="text-xs font-bold text-slate-500">{product.title}</div>
                  <StockEditor brandId={snapshot.brand.id} sku={sku} onSaved={refresh} />
                  {sku.store_inventories.length > 0 && <div className="ps-3 text-xs text-slate-500">{sku.store_inventories.map((row) => `${row.store_name}: ${row.available}`).join(' · ')}</div>}
                </div>
              ))}
              {snapshot.inventory.length === 0 && <p className="rounded-2xl bg-white p-5 text-sm text-slate-500">{t('admin_catalog.no_inventory')}</p>}
            </section>
          )}

          {tab === 'placements' && (
            <section className="space-y-4">
              <div><h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">{t('admin_catalog.placements_heading')}</h2><p className="mt-1 text-sm text-slate-500">{t('admin_catalog.placements_help')}</p></div>
              {snapshot.placements.map((placement) => (
                <div key={String(placement.id)} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-4">
                  <div><span className="block text-[10px] font-bold uppercase text-slate-500">{t('admin_catalog.product')}</span>{String(placement.product_title)}</div>
                  <div><span className="block text-[10px] font-bold uppercase text-slate-500">{t('admin_catalog.status')}</span>{String(placement.status)}</div>
                  <div><span className="block text-[10px] font-bold uppercase text-slate-500">{t('admin_catalog.budget')}</span>{String(placement.daily_budget)}</div>
                  <div><span className="block text-[10px] font-bold uppercase text-slate-500">{t('admin_catalog.performance')}</span>{t('admin_catalog.clicks_conversions', { clicks: placement.clicks, conversions: placement.conversions })}</div>
                </div>
              ))}
              {snapshot.placements.length === 0 && <p className="rounded-2xl bg-white p-5 text-sm text-slate-500">{t('admin_catalog.no_placements')}</p>}
            </section>
          )}

          {tab === 'imports' && (
            <section className="space-y-4">
              <div><h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">{t('admin_catalog.imports_heading')}</h2><p className="mt-1 text-sm text-slate-500">{t('admin_catalog.imports_help')}</p></div>
              {snapshot.imports.map((job) => (
                <div key={String(job.job_id)} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-4">
                  <div><span className="block text-[10px] font-bold uppercase text-slate-500">{t('admin_catalog.file')}</span>{String(job.file_name ?? '—')}</div>
                  <div><span className="block text-[10px] font-bold uppercase text-slate-500">{t('admin_catalog.status')}</span>{String(job.status)}</div>
                  <div><span className="block text-[10px] font-bold uppercase text-slate-500">{t('admin_catalog.accepted')}</span>{String(job.accepted_rows)}</div>
                  <div><span className="block text-[10px] font-bold uppercase text-slate-500">{t('admin_catalog.rejected')}</span>{String(job.rejected_rows)}</div>
                </div>
              ))}
              {snapshot.imports.length === 0 && <p className="rounded-2xl bg-white p-5 text-sm text-slate-500">{t('admin_catalog.no_imports')}</p>}
            </section>
          )}
        </>
      )}
    </div>
  );
};
