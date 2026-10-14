import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { brandService } from '../../services/apiServices';
import type { PartnerStoreDetail } from '../../models';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const BrandBranchesView: React.FC = () => {
  const { t } = useTranslation();
  const [branches, setBranches] = useState<PartnerStoreDetail[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Search filter
  const [searchQuery, setSearchQuery] = useState('');

  // Modal create/edit state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingBranch, setEditingBranch] = useState<PartnerStoreDetail | null>(null);

  // Form states
  const [formName, setFormName] = useState('');
  const [formNameAr, setFormNameAr] = useState('');
  const [formAddress, setFormAddress] = useState('');
  const [formCity, setFormCity] = useState('');
  const [formCountry, setFormCountry] = useState('UAE');
  const [formLat, setFormLat] = useState<number>(0);
  const [formLng, setFormLng] = useState<number>(0);
  const [formPhone, setFormPhone] = useState('');
  const [formInstructions, setFormInstructions] = useState('');
  const [formBopis, setFormBopis] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Deletion state
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fetchBranches = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await brandService.getStores();
      setBranches(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load branch directory.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBranches();
  }, [fetchBranches]);

  const openCreateModal = () => {
    setEditingBranch(null);
    setFormName('');
    setFormNameAr('');
    setFormAddress('');
    setFormCity('');
    setFormCountry('UAE');
    setFormLat(25.1972);
    setFormLng(55.2796);
    setFormPhone('');
    setFormInstructions('');
    setFormBopis(true);
    setFormError(null);
    setIsModalOpen(true);
  };

  const openEditModal = (b: PartnerStoreDetail) => {
    setEditingBranch(b);
    setFormName(b.name);
    setFormNameAr(b.name_ar || b.name);
    setFormAddress(b.address);
    setFormCity(b.city);
    setFormCountry(b.country);
    setFormLat(b.latitude);
    setFormLng(b.longitude);
    setFormPhone(b.phone || '');
    setFormInstructions(b.pickup_instructions || '');
    setFormBopis(b.is_bopis_enabled);
    setFormError(null);
    setIsModalOpen(true);
  };

  const handleSaveBranch = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Coordinate validation
    if (formLat < -90 || formLat > 90) {
      setFormError('Latitude must be between -90 and 90 degrees.');
      return;
    }
    if (formLng < -180 || formLng > 180) {
      setFormError('Longitude must be between -180 and 180 degrees.');
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        name: formName.trim(),
        name_ar: formNameAr.trim() || formName.trim(),
        address: formAddress.trim(),
        city: formCity.trim(),
        country: formCountry.trim(),
        latitude: Number(formLat),
        longitude: Number(formLng),
        phone: formPhone.trim() || undefined,
        pickup_instructions: formInstructions.trim() || undefined,
        is_bopis_enabled: formBopis,
      };

      if (editingBranch) {
        await brandService.updateStore(editingBranch.id, payload);
      } else {
        await brandService.createStore(payload);
      }
      setIsModalOpen(false);
      await fetchBranches();
    } catch (err: any) {
      setFormError(err?.message || 'Unable to save branch.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm(t('brand_branches.delete_confirm'))) {
      return;
    }
    setDeletingId(id);
    try {
      await brandService.deleteStore(id);
      await fetchBranches();
    } catch (err: any) {
      alert(err?.message || 'Failed to delete branch.');
    } finally {
      setDeletingId(null);
    }
  };

  const filteredBranches = useMemo(() => {
    if (!searchQuery.trim()) return branches;
    const q = searchQuery.toLowerCase();
    return branches.filter(
      (b) =>
        b.name.toLowerCase().includes(q) ||
        b.address.toLowerCase().includes(q) ||
        b.city.toLowerCase().includes(q),
    );
  }, [branches, searchQuery]);

  const verifiedCount = useMemo(
    () => branches.filter((b) => b.is_location_verified).length,
    [branches],
  );
  const bopisCount = useMemo(
    () => branches.filter((b) => b.is_bopis_enabled).length,
    [branches],
  );

  return (
    <div className="space-y-8 pb-20">
      {/* View Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-widest text-brand-coral">
            Omnichannel Boutique Network
          </span>
          <h1 className="font-serif text-2xl sm:text-3xl font-bold tracking-tight text-brand-charcoal">
            {t('brand_branches.title')}
          </h1>
          <p className="text-xs sm:text-sm text-neutral-600 mt-1 max-w-2xl leading-relaxed">
            {t('brand_branches.subtitle')}
          </p>
        </div>

        <button
          type="button"
          aria-label={t('brand_branches.add_branch_btn')}
          onClick={openCreateModal}
          className="inline-flex items-center gap-2 px-5 py-3 rounded-2xl bg-brand-charcoal text-white text-xs font-bold hover:bg-neutral-800 transition-colors shadow-sm self-start sm:self-center"
        >
          <span className="text-base leading-none" aria-hidden="true">+</span>
          {t('brand_branches.add_branch_btn')}
        </button>
      </div>

      {/* KPI Stats Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl bg-neutral-50 border border-neutral-200">
          <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-400 block">
            {t('brand_branches.total_branches')}
          </span>
          <span className="font-serif text-2xl font-bold text-brand-charcoal">
            {branches.length}
          </span>
        </div>

        <div className="p-5 rounded-2xl bg-neutral-50 border border-neutral-200">
          <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-400 block">
            {t('brand_branches.verified_locations')}
          </span>
          <div className="flex items-center gap-2">
            <span className="font-serif text-2xl font-bold text-emerald-700">
              {verifiedCount}
            </span>
            <span className="text-[10px] font-semibold text-neutral-500">
              / {branches.length} verified
            </span>
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-neutral-50 border border-neutral-200">
          <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-400 block">
            {t('brand_branches.bopis_enabled')}
          </span>
          <span className="font-serif text-2xl font-bold text-purple-700">
            {bopisCount}
          </span>
        </div>
      </div>

      {/* Search Toolbar */}
      <div className="p-4 rounded-2xl bg-neutral-50 border border-neutral-200 flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('brand_branches.search_placeholder')}
            className="w-full rounded-xl bg-white border border-neutral-200 py-2.5 pl-9 pr-3 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
            aria-label={t('brand_branches.search_aria')}
          />
          <svg
            className="w-4 h-4 absolute left-3 top-3 text-neutral-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        {searchQuery && (
          <button
            type="button"
            onClick={() => setSearchQuery('')}
            className="text-xs font-bold text-brand-coral hover:underline"
          >
            Clear
          </button>
        )}
      </div>

      {/* Loading & Error States */}
      {isLoading && (
        <div className="p-12 flex justify-center">
          <LoadingSpinner />
        </div>
      )}

      {error && (
        <div className="p-6 rounded-2xl bg-red-50 border border-red-200 text-xs text-red-800">
          <p className="font-bold">{t('brand_branches.error_loading', 'Error loading branches')}</p>
          <p className="mt-1">{error}</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && filteredBranches.length === 0 && (
        <div className="rounded-3xl border border-dashed border-neutral-300 p-12 text-center bg-neutral-50/50 space-y-3">
          <div className="mx-auto h-12 w-12 rounded-full bg-neutral-100 flex items-center justify-center text-neutral-400">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <h3 className="font-serif text-lg font-bold text-brand-charcoal">
            {t('brand_branches.no_branches_title')}
          </h3>
          <p className="text-xs text-neutral-500 max-w-sm mx-auto">
            {t('brand_branches.no_branches_desc')}
          </p>
          <button
            type="button"
            onClick={openCreateModal}
            className="mt-2 px-6 py-2.5 rounded-xl bg-brand-charcoal text-white text-xs font-bold hover:bg-neutral-800 transition-colors"
          >
            {t('brand_branches.add_branch_btn')}
          </button>
        </div>
      )}

      {/* Branches Directory Cards */}
      {!isLoading && !error && filteredBranches.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {filteredBranches.map((b) => (
            <div
              key={b.id}
              className="rounded-3xl border border-neutral-200 bg-white p-6 shadow-sm hover:border-neutral-400 hover:shadow-md transition-all flex flex-col justify-between space-y-4"
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-serif text-lg font-bold text-brand-charcoal">
                      {b.name}
                    </h3>
                    <p className="text-xs text-neutral-500 mt-0.5">
                      {b.address}, {b.city}, {b.country}
                    </p>
                  </div>

                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      b.is_location_verified
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-amber-50 text-amber-700 border border-amber-200'
                    }`}
                  >
                    {b.is_location_verified
                      ? t('brand_branches.status_verified')
                      : t('brand_branches.status_unverified')}
                  </span>
                </div>

                {b.pickup_instructions && (
                  <div className="mt-3 text-xs p-3 rounded-xl bg-neutral-50 border border-neutral-200/80 text-neutral-600">
                    <span className="font-bold text-[10px] uppercase tracking-wider text-neutral-400 block mb-0.5">
                      Instructions
                    </span>
                    {b.pickup_instructions}
                  </div>
                )}

                {/* Stock & BOPIS Info */}
                <div className="mt-4 pt-3 border-t border-neutral-100 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3">
                    <span className="text-neutral-500">
                      Stock: <span className="font-bold text-brand-charcoal">{b.total_stock_units} units</span>
                    </span>
                    <span className="text-neutral-300">•</span>
                    <span className="text-neutral-500">
                      SKUs: <span className="font-bold text-brand-charcoal">{b.inventory_items_count}</span>
                    </span>
                  </div>

                  {b.is_bopis_enabled && (
                    <span className="text-[10px] font-bold uppercase tracking-wider text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                      BOPIS
                    </span>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-3 border-t border-neutral-100 flex items-center justify-between gap-2">
                <a
                  href={b.google_maps_url || (b.latitude != null && b.longitude != null ? `https://www.google.com/maps/search/?api=1&query=${b.latitude},${b.longitude}` : undefined)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-neutral-100 hover:bg-neutral-200 text-xs font-bold text-brand-charcoal transition-colors"
                >
                  <svg className="w-3.5 h-3.5 text-brand-coral" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                    <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
                  </svg>
                  {t('brand_branches.directions')}
                </a>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => openEditModal(b)}
                    className="px-3.5 py-2 rounded-xl border border-neutral-300 text-xs font-bold text-neutral-700 hover:bg-neutral-50 transition-colors"
                  >
                    {t('brand_branches.edit')}
                  </button>
                  <button
                    type="button"
                    disabled={deletingId === b.id}
                    onClick={() => handleDelete(b.id)}
                    className="px-3 py-2 rounded-xl border border-red-200 text-xs font-bold text-red-700 hover:bg-red-50 transition-colors"
                  >
                    {deletingId === b.id ? 'Deleting…' : t('brand_branches.delete_btn')}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create / Edit Modal */}
      {isModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-xl w-full max-h-[90vh] overflow-y-auto shadow-2xl border border-neutral-200 space-y-5">
            <div className="flex items-center justify-between">
              <h3 className="font-serif text-xl font-bold text-brand-charcoal">
                {editingBranch
                  ? t('brand_branches.modal_edit_title')
                  : t('brand_branches.modal_create_title')}
              </h3>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="text-neutral-400 hover:text-neutral-600 text-sm font-bold"
              >
                ✕
              </button>
            </div>

            {formError && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-800">
                {formError}
              </div>
            )}

            <form onSubmit={handleSaveBranch} noValidate className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-neutral-700 mb-1">
                  {t('brand_branches.name_label')} *
                </label>
                <input
                  type="text"
                  name="name"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder={t('brand_branches.name_placeholder')}
                  className="w-full rounded-xl bg-neutral-50 border border-neutral-200 p-2.5 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-neutral-700 mb-1">
                  {t('brand_branches.address_label')} *
                </label>
                <input
                  type="text"
                  name="address"
                  required
                  value={formAddress}
                  onChange={(e) => setFormAddress(e.target.value)}
                  placeholder={t('brand_branches.address_placeholder')}
                  className="w-full rounded-xl bg-neutral-50 border border-neutral-200 p-2.5 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    {t('brand_branches.city_label')} *
                  </label>
                  <input
                    type="text"
                    name="city"
                    required
                    value={formCity}
                    onChange={(e) => setFormCity(e.target.value)}
                    className="w-full rounded-xl bg-neutral-50 border border-neutral-200 p-2.5 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    {t('brand_branches.country_label')} *
                  </label>
                  <input
                    type="text"
                    name="country"
                    required
                    value={formCountry}
                    onChange={(e) => setFormCountry(e.target.value)}
                    className="w-full rounded-xl bg-neutral-50 border border-neutral-200 p-2.5 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                  />
                </div>
              </div>

              {/* Coordinates Section with Live Validation */}
              <div className="p-3.5 rounded-2xl bg-neutral-50 border border-neutral-200 space-y-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-neutral-500 block">
                  Store Coordinates (Google Maps Destination)
                </span>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-neutral-600 mb-0.5">
                      {t('brand_branches.latitude_label')}
                    </label>
                    <input
                      type="number"
                      name="latitude"
                      step="any"
                      required
                      min={-90}
                      max={90}
                      value={formLat}
                      onChange={(e) => setFormLat(parseFloat(e.target.value) || 0)}
                      className="w-full rounded-xl bg-white border border-neutral-200 p-2 text-xs font-mono font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-neutral-600 mb-0.5">
                      {t('brand_branches.longitude_label')}
                    </label>
                    <input
                      type="number"
                      name="longitude"
                      step="any"
                      required
                      min={-180}
                      max={180}
                      value={formLng}
                      onChange={(e) => setFormLng(parseFloat(e.target.value) || 0)}
                      className="w-full rounded-xl bg-white border border-neutral-200 p-2 text-xs font-mono font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    {t('brand_branches.phone_label')}
                  </label>
                  <input
                    type="tel"
                    value={formPhone}
                    onChange={(e) => setFormPhone(e.target.value)}
                    placeholder={t('brand_branches.phone_placeholder')}
                    className="w-full rounded-xl bg-neutral-50 border border-neutral-200 p-2.5 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                  />
                </div>
                <div className="flex items-center pt-5">
                  <label className="inline-flex items-center gap-2 cursor-pointer select-none text-xs font-bold text-brand-charcoal">
                    <input
                      type="checkbox"
                      checked={formBopis}
                      onChange={(e) => setFormBopis(e.target.checked)}
                      className="h-4 w-4 rounded border-neutral-300 text-brand-coral focus:ring-brand-coral"
                    />
                    <span>{t('brand_branches.bopis_label')}</span>
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-neutral-700 mb-1">
                  {t('brand_branches.instructions_label')}
                </label>
                <textarea
                  rows={2}
                  value={formInstructions}
                  onChange={(e) => setFormInstructions(e.target.value)}
                  placeholder={t('brand_branches.instructions_placeholder')}
                  className="w-full rounded-xl bg-neutral-50 border border-neutral-200 p-2.5 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                />
              </div>

              <div className="pt-3 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-5 py-2.5 rounded-xl border border-neutral-200 text-xs font-bold text-neutral-600 hover:bg-neutral-50"
                >
                  {t('brand_branches.cancel')}
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="px-6 py-2.5 rounded-xl bg-brand-charcoal text-white text-xs font-bold hover:bg-neutral-800 disabled:opacity-50"
                >
                  {isSaving ? t('brand_branches.saving') : t('brand_branches.save_btn')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
