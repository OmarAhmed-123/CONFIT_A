import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { catalogService } from '../../services/apiServices';
import type {
  CustomerBrand,
  CustomerBrandDetail,
  BranchInventoryCatalog,
  BranchProductItem,
  BranchSKUAvailability,
} from '../../models';
import { BrandCard } from '../../components/brands/BrandCard';
import { StoreBranchCard } from '../../components/brands/StoreBranchCard';
import { BranchInventoryGrid } from '../../components/brands/BranchInventoryGrid';
import { PromotionBanner } from '../../components/brands/PromotionBanner';
import { StoreMapCanvas } from '../../components/brands/StoreMapCanvas';

export const BrandsView: React.FC = () => {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Selected brand & branch states
  const [brands, setBrands] = useState<CustomerBrand[]>([]);
  const [isLoadingBrands, setIsLoadingBrands] = useState<boolean>(true);
  const [brandsError, setBrandsError] = useState<string | null>(null);

  const [activeBrandDetail, setActiveBrandDetail] = useState<CustomerBrandDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [selectedBranchId, setSelectedBranchId] = useState<number | null>(null);
  const [branchInventory, setBranchInventory] = useState<BranchInventoryCatalog | null>(null);
  const [isLoadingInventory, setIsLoadingInventory] = useState<boolean>(false);
  const [inventoryError, setInventoryError] = useState<string | null>(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState<string>(searchParams.get('q') || '');
  const [selectedCategory, setSelectedCategory] = useState<string>(searchParams.get('category') || '');
  const [selectedCity, setSelectedCity] = useState<string>(searchParams.get('city') || '');
  const [hasOffersOnly, setHasOffersOnly] = useState<boolean>(searchParams.get('offers') === 'true');
  const [sortBy, setSortBy] = useState<string>(searchParams.get('sort') || 'alphabetical');

  // Branch inventory filters
  const [inventoryCategory, setInventoryCategory] = useState<string>('');
  const [inStockOnly, setInStockOnly] = useState<boolean>(false);
  const [inventorySearch, setInventorySearch] = useState<string>('');
  const [inventorySort, setInventorySort] = useState<string>('newest');

  // Geolocation
  const [userCoords, setUserCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [geoStatus, setGeoStatus] = useState<'idle' | 'loading' | 'success' | 'denied'>('idle');

  // Reservation Feedback Modal
  const [reservationNotice, setReservationNotice] = useState<{
    item: BranchProductItem;
    sku: BranchSKUAvailability;
    branchName: string;
  } | null>(null);

  // Geolocation request
  const requestLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setGeoStatus('denied');
      return;
    }
    setGeoStatus('loading');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGeoStatus('success');
      },
      () => {
        setGeoStatus('denied');
      },
      { timeout: 7000, enableHighAccuracy: true },
    );
  }, []);

  // 1. Fetch Brands List
  const fetchBrands = useCallback(async () => {
    setIsLoadingBrands(true);
    setBrandsError(null);
    try {
      const data = await catalogService.getBrands({
        q: searchQuery,
        category: selectedCategory,
        city: selectedCity,
        has_offers: hasOffersOnly ? true : undefined,
        sort: sortBy,
      });
      setBrands(data);
    } catch (err: any) {
      setBrandsError(err.message || 'Unable to load brands directory.');
    } finally {
      setIsLoadingBrands(false);
    }
  }, [searchQuery, selectedCategory, selectedCity, hasOffersOnly, sortBy]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchBrands();
    }, 250);
    return () => clearTimeout(timer);
  }, [fetchBrands]);

  // 2. Fetch Brand Detail when slug is set
  useEffect(() => {
    if (!slug) {
      setActiveBrandDetail(null);
      setSelectedBranchId(null);
      setBranchInventory(null);
      return;
    }

    let isMounted = true;
    setIsLoadingDetail(true);
    setDetailError(null);

    catalogService
      .getBrandDetail(slug, userCoords || undefined)
      .then((detail) => {
        if (!isMounted) return;
        setActiveBrandDetail(detail);

        // Pick initial branch from search params or first available store
        const branchParam = searchParams.get('branch');
        const targetBranchId = branchParam ? Number(branchParam) : null;
        const initialStore = detail.stores.find((s) => s.id === targetBranchId) || detail.stores[0];
        if (initialStore) {
          setSelectedBranchId(initialStore.id);
        } else {
          setSelectedBranchId(null);
        }
      })
      .catch((err) => {
        if (!isMounted) return;
        setDetailError(err.message || `Unable to load details for ${slug}`);
      })
      .finally(() => {
        if (isMounted) setIsLoadingDetail(false);
      });

    return () => {
      isMounted = false;
    };
  }, [slug, userCoords]);

  // 3. Fetch Branch Inventory when selectedBranchId changes
  useEffect(() => {
    if (!selectedBranchId) {
      setBranchInventory(null);
      return;
    }

    let isMounted = true;
    setIsLoadingInventory(true);
    setInventoryError(null);

    catalogService
      .getBranchInventory(selectedBranchId, {
        category: inventoryCategory,
        in_stock_only: inStockOnly,
        search: inventorySearch,
        sort_by: inventorySort,
      })
      .then((inv) => {
        if (!isMounted) return;
        setBranchInventory(inv);
      })
      .catch((err) => {
        if (!isMounted) return;
        setInventoryError(err.message || 'Unable to load inventory for this branch.');
      })
      .finally(() => {
        if (isMounted) setIsLoadingInventory(false);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedBranchId, inventoryCategory, inStockOnly, inventorySearch, inventorySort]);

  // Collect all available categories and cities across brands
  const availableCategories = useMemo(() => {
    const set = new Set<string>();
    brands.forEach((b) => b.categories.forEach((c) => set.add(c)));
    return Array.from(set).sort();
  }, [brands]);

  const availableCities = useMemo(() => {
    const set = new Set<string>();
    brands.forEach((b) => b.cities.forEach((c) => set.add(c)));
    return Array.from(set).sort();
  }, [brands]);

  const activeBranch = useMemo(() => {
    if (!activeBrandDetail || !selectedBranchId) return null;
    return activeBrandDetail.stores.find((s) => s.id === selectedBranchId) || activeBrandDetail.stores[0] || null;
  }, [activeBrandDetail, selectedBranchId]);

  // Select brand handler
  const handleSelectBrand = (brandSlug: string) => {
    navigate(`/brands/${brandSlug}`);
  };

  // Back to directory
  const handleBackToBrands = () => {
    navigate('/brands');
  };

  // Branch select handler
  const handleSelectBranch = (branchId: number) => {
    setSelectedBranchId(branchId);
    setSearchParams((prev) => {
      prev.set('branch', String(branchId));
      return prev;
    });
  };

  // Reservation handler
  const handleReserveClick = (item: BranchProductItem, sku: BranchSKUAvailability) => {
    if (!activeBranch) return;
    setReservationNotice({
      item,
      sku,
      branchName: activeBranch.name,
    });
  };

  return (
    <div className="min-h-screen bg-white text-brand-charcoal font-sans pb-24">
      {/* Top Banner / Breadcrumb Bar */}
      <div className="border-b border-neutral-200 bg-neutral-50/60">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-3 text-xs">
          <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 min-w-0 text-neutral-500">
            <Link to="/" className="hover:text-brand-charcoal transition-colors">
              Home
            </Link>
            <span aria-hidden="true">/</span>
            {slug && activeBrandDetail ? (
              <>
                <Link to="/brands" className="hover:text-brand-charcoal transition-colors">
                  {t('brands.title')}
                </Link>
                <span aria-hidden="true">/</span>
                <span className="font-semibold text-brand-charcoal break-words min-w-0">
                  {activeBrandDetail.brand_name}
                </span>
                {activeBranch && (
                  <>
                    <span aria-hidden="true">/</span>
                    <span className="text-neutral-500 truncate max-w-[200px]">
                      {activeBranch.name}
                    </span>
                  </>
                )}
              </>
            ) : (
              <span className="font-semibold text-brand-charcoal">{t('brands.title')}</span>
            )}
          </nav>

          {/* Quick Geolocation Trigger */}
          <button data-motion="progressive" data-motion-tone="icon"
            type="button"
            onClick={requestLocation}
            disabled={geoStatus === 'loading'}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-neutral-200 bg-white text-xs font-semibold text-brand-charcoal hover:bg-neutral-50 transition-colors shadow-2xs"
          >
            <svg
              className={`w-3.5 h-3.5 ${geoStatus === 'loading' ? 'motion-safe:animate-spin text-brand-coral' : 'text-emerald-600'}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span>{geoStatus === 'success' ? t('brands.location_active') : t('brands.locate_nearest')}</span>
          </button>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        {/* ================================================================= */}
        {/* LEVEL 1: BRAND DIRECTORY (When no slug selected)                  */}
        {/* ================================================================= */}
        {!slug && (
          <div className="space-y-8">
            {/* Header Hero */}
            <div className="space-y-3">
              <span className="text-xs font-bold uppercase tracking-widest text-brand-charcoal">
                {t('brands.partner_houses')}
              </span>
              <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-brand-charcoal">
                {t('brands.title')}
              </h1>
              <p className="text-sm sm:text-base text-neutral-600 max-w-3xl leading-relaxed">
                {t('brands.subtitle')}
              </p>
            </div>

            {/* Search & Filter Toolbar */}
            <div className="p-4 sm:p-5 rounded-2xl bg-neutral-50 border border-neutral-200 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                {/* Search Bar */}
                <div className="md:col-span-5 relative">
                  <input
                    type="text"
                    placeholder={t('brands.search_placeholder')}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded-xl bg-white border border-neutral-200 py-2.5 pl-9 pr-3 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    aria-label={t('brands.search_aria')}
                  />
                  <svg
                    className="w-4 h-4 absolute left-3 top-3 text-brand-field"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>

                {/* Category Filter */}
                <div className="md:col-span-3">
                  <select
                    value={selectedCategory}
                    onChange={(e) => setSelectedCategory(e.target.value)}
                    className="w-full rounded-xl bg-white border border-neutral-200 py-2.5 px-3 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    aria-label={t('brands.filter_category_aria')}
                  >
                    <option value="">{t('brands.all_categories')}</option>
                    {availableCategories.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>

                {/* City Filter */}
                <div className="md:col-span-2">
                  <select
                    value={selectedCity}
                    onChange={(e) => setSelectedCity(e.target.value)}
                    className="w-full rounded-xl bg-white border border-neutral-200 py-2.5 px-3 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    aria-label={t('brands.filter_city_aria')}
                  >
                    <option value="">{t('brands.all_cities')}</option>
                    {availableCities.map((city) => (
                      <option key={city} value={city}>
                        {city}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Sort Filter */}
                <div className="md:col-span-2">
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value)}
                    className="w-full rounded-xl bg-white border border-neutral-200 py-2.5 px-3 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    aria-label={t('brands.sort_aria')}
                  >
                    <option value="alphabetical">{t('brands.sort_a_z')}</option>
                    <option value="stores">{t('brands.sort_most_stores')}</option>
                    <option value="products">{t('brands.sort_most_products')}</option>
                    <option value="offers">{t('brands.sort_active_deals')}</option>
                  </select>
                </div>
              </div>

              {/* Secondary Filters Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-neutral-200/60 text-xs">
                <label className="inline-flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={hasOffersOnly}
                    onChange={(e) => setHasOffersOnly(e.target.checked)}
                    className="h-4 w-4 rounded border-neutral-300 text-brand-coral focus:ring-brand-coral"
                  />
                  <span className="font-semibold text-brand-charcoal">
                    {t('brands.only_with_offers')}
                  </span>
                </label>

                {(searchQuery || selectedCategory || selectedCity || hasOffersOnly) && (
                  <button data-motion="destructive"
                    type="button"
                    onClick={() => {
                      setSearchQuery('');
                      setSelectedCategory('');
                      setSelectedCity('');
                      setHasOffersOnly(false);
                      setSortBy('alphabetical');
                    }}
                    className="text-xs font-bold text-brand-charcoal hover:underline"
                  >
                    {t('brands.reset_filters')}
                  </button>
                )}
              </div>
            </div>

            {/* Error state */}
            {brandsError && (
              <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center text-xs text-red-800">
                <p className="font-bold">{t('brands.error_loading_brands')}</p>
                <p className="mt-1">{brandsError}</p>
                <button data-motion="recovery"
                  type="button"
                  onClick={fetchBrands}
                  className="mt-3 px-4 py-2 rounded-xl bg-red-800 text-white font-bold"
                >
                  {t('brands.retry')}
                </button>
              </div>
            )}

            {/* Skeletons Loading */}
            {isLoadingBrands && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div
                    key={i}
                    className="rounded-2xl bg-white border border-neutral-200 p-6 space-y-4 animate-pulse"
                  >
                    <div className="flex items-center gap-3">
                      <div className="h-14 w-14 rounded-xl bg-neutral-200" />
                      <div className="space-y-2 flex-1">
                        <div className="h-4 bg-neutral-200 rounded w-1/2" />
                        <div className="h-3 bg-neutral-200 rounded w-3/4" />
                      </div>
                    </div>
                    <div className="h-10 bg-neutral-100 rounded-xl" />
                    <div className="h-4 bg-neutral-100 rounded w-1/3" />
                  </div>
                ))}
              </div>
            )}

            {/* Brand Grid */}
            {!isLoadingBrands && !brandsError && (
              <>
                {brands.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {brands.map((b) => (
                      <BrandCard
                        key={b.id}
                        brand={b}
                        onSelect={handleSelectBrand}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-neutral-300 p-12 text-center bg-neutral-50/50 space-y-2">
                    <p className="font-serif text-lg font-bold text-brand-charcoal">
                      {t('brands.no_brands_found')}
                    </p>
                    <p className="text-xs text-neutral-500">
                      {t('brands.no_brands_hint')}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ================================================================= */}
        {/* LEVEL 2 & 3: BRAND DETAIL & BRANCH WORKSPACE (When slug selected) */}
        {/* ================================================================= */}
        {slug && (
          <div className="space-y-8">
            {/* Back button & Brand Header */}
            <div>
              <button data-motion="neutral"
                type="button"
                onClick={handleBackToBrands}
                className="inline-flex items-center gap-1.5 text-xs font-bold text-neutral-600 hover:text-brand-charcoal mb-4 transition-colors"
              >
                <span aria-hidden="true">&larr;</span> {t('brands.back_to_brands')}
              </button>

              {isLoadingDetail && (
                <div className="p-8 rounded-2xl bg-neutral-50 border border-neutral-200 animate-pulse h-32" />
              )}

              {detailError && (
                <div role="alert" className="p-6 rounded-2xl bg-red-50 border border-red-200 text-xs text-red-800">
                  {/* Tailwind preflight resets heading size/weight, so this
                      renders exactly as the <p> it replaces — but the page now
                      has a heading instead of none, and the failure is
                      announced instead of being silent. */}
                  <h1 className="font-bold">{t('brands.error_loading_brand')}</h1>
                  <p className="mt-1">{detailError}</p>
                </div>
              )}

              {activeBrandDetail && (
                <div className="relative overflow-hidden rounded-3xl bg-neutral-50 border border-neutral-200 p-6 sm:p-8">
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
                    <div className="flex items-center gap-5">
                      {activeBrandDetail.logo_url ? (
                        <img
                          src={activeBrandDetail.logo_url}
                          alt={activeBrandDetail.brand_name}
                          className="h-20 w-20 rounded-2xl object-cover border border-neutral-200 shadow-sm"
                        />
                      ) : (
                        <div className="h-20 w-20 rounded-2xl bg-white border border-neutral-200 flex items-center justify-center font-serif font-bold text-2xl text-brand-charcoal shadow-sm">
                          {activeBrandDetail.brand_name.slice(0, 2).toUpperCase()}
                        </div>
                      )}

                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <h1 className="font-serif text-2xl sm:text-3xl font-bold tracking-tight text-brand-charcoal">
                            {activeBrandDetail.brand_name}
                          </h1>
                          {activeBrandDetail.is_verified && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              {t('brands.verified_partner')}
                            </span>
                          )}
                        </div>
                        <p className="text-xs sm:text-sm text-neutral-600 max-w-xl">
                          {activeBrandDetail.description || 'Verified contemporary luxury fashion house.'}
                        </p>
                      </div>
                    </div>

                    {/* Meta stats */}
                    <div className="flex items-center gap-4 border-t sm:border-t-0 sm:border-l border-neutral-200 pt-4 sm:pt-0 sm:pl-6 text-left">
                      <div>
                        <span className="text-[10px] uppercase font-bold tracking-wider text-brand-muted block">
                          {t('brands.physical_network')}
                        </span>
                        <span className="text-base font-bold text-brand-charcoal">
                          {activeBrandDetail.stores.length} {activeBrandDetail.stores.length === 1 ? 'Store' : 'Stores'}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase font-bold tracking-wider text-brand-muted block">
                          {t('brands.catalog')}
                        </span>
                        <span className="text-base font-bold text-brand-charcoal">
                          {activeBrandDetail.total_products} {t('brands.garments')}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Brand Level Promotions */}
                  {activeBrandDetail.all_promotions && activeBrandDetail.all_promotions.length > 0 && (
                    <div className="mt-6 pt-6 border-t border-neutral-200">
                      <PromotionBanner
                        promotions={activeBrandDetail.all_promotions}
                        brandName={activeBrandDetail.brand_name}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Split Pane: Stores Directory + Map Canvas */}
            {activeBrandDetail && (
              <div className="space-y-6">
                <div>
                  <h2 className="font-serif text-xl font-bold tracking-tight text-brand-charcoal">
                    {t('brands.stores_title')}
                  </h2>
                  <p className="text-xs text-neutral-500 mt-0.5">
                    {t('brands.stores_subtitle')}
                  </p>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                  {/* Left Column: Branch Cards List */}
                  <div className="lg:col-span-5 space-y-4">
                    {activeBrandDetail.stores.map((branch) => (
                      <StoreBranchCard
                        key={branch.id}
                        branch={branch}
                        isSelected={branch.id === selectedBranchId}
                        onSelect={handleSelectBranch}
                        brandName={activeBrandDetail.brand_name}
                      />
                    ))}
                  </div>

                  {/* Right Column: Interactive Map Canvas */}
                  <div className="lg:col-span-7">
                    <StoreMapCanvas
                      branches={activeBrandDetail.stores}
                      selectedBranchId={selectedBranchId}
                      onSelectBranch={handleSelectBranch}
                      brandName={activeBrandDetail.brand_name}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Branch Level Product Availability Section */}
            {activeBranch && (
              <div className="mt-12 pt-8 border-t border-neutral-200 space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-brand-charcoal">
                      {t('brands.live_availability')}
                    </span>
                    <h3 className="font-serif text-xl sm:text-2xl font-bold tracking-tight text-brand-charcoal">
                      {t('brands.available_at', { name: activeBranch.name })}
                    </h3>
                    <p className="text-xs text-neutral-500 mt-0.5">
                      {activeBranch.address}, {activeBranch.city} • Verified SKU inventory on hand
                    </p>
                  </div>

                  <a
                    href={activeBranch.google_maps_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-brand-coral text-brand-charcoal text-xs font-bold hover:bg-brand-coral/90 shadow-xs transition-colors self-start sm:self-center"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                      <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
                    </svg>
                    {t('brands.navigate_google_maps')}
                  </a>
                </div>

                {/* Branch-Specific Promotions Ribbon */}
                {activeBranch.active_promotions && activeBranch.active_promotions.length > 0 && (
                  <PromotionBanner
                    promotions={activeBranch.active_promotions}
                    branchName={activeBranch.name}
                  />
                )}

                {/* Branch Inventory Filters */}
                <div className="p-4 rounded-2xl bg-neutral-50 border border-neutral-200 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="text"
                      placeholder={t('brands.search_branch_items')}
                      value={inventorySearch}
                      onChange={(e) => setInventorySearch(e.target.value)}
                      className="rounded-xl bg-white border border-neutral-200 py-2 px-3 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal w-48 sm:w-60"
                      aria-label={t('brands.search_branch_aria')}
                    />

                    {branchInventory?.categories && branchInventory.categories.length > 0 && (
                      <select
                        value={inventoryCategory}
                        onChange={(e) => setInventoryCategory(e.target.value)}
                        className="rounded-xl bg-white border border-neutral-200 py-2 px-3 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                        aria-label={t('brands.filter_branch_category_aria')}
                      >
                        <option value="">{t('brands.all_categories')}</option>
                        {branchInventory.categories.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    )}

                    <select
                      value={inventorySort}
                      onChange={(e) => setInventorySort(e.target.value)}
                      className="rounded-xl bg-white border border-neutral-200 py-2 px-3 text-xs font-medium text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                      aria-label={t('brands.sort_branch_aria')}
                    >
                      <option value="newest">{t('brands.newest_arrivals')}</option>
                      <option value="price_asc">{t('brands.price_low_high')}</option>
                      <option value="price_desc">{t('brands.price_high_low')}</option>
                      <option value="stock">{t('brands.highest_stock')}</option>
                    </select>
                  </div>

                  <label className="inline-flex items-center gap-2 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={inStockOnly}
                      onChange={(e) => setInStockOnly(e.target.checked)}
                      className="h-4 w-4 rounded border-neutral-300 text-brand-coral focus:ring-brand-coral"
                    />
                    <span className="font-semibold text-brand-charcoal">
                      {t('brands.in_stock_only')}
                    </span>
                  </label>
                </div>

                {/* Loading Inventory */}
                {isLoadingInventory && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5 animate-pulse">
                    {[1, 2, 3].map((i) => (
                      <div key={i} className="h-64 rounded-2xl bg-neutral-100" />
                    ))}
                  </div>
                )}

                {/* Error Inventory */}
                {inventoryError && (
                  <div className="p-6 rounded-2xl bg-red-50 border border-red-200 text-xs text-red-800">
                    <p className="font-bold">{t('brands.error_loading_inventory')}</p>
                    <p className="mt-1">{inventoryError}</p>
                  </div>
                )}

                {/* Products Grid */}
                {!isLoadingInventory && !inventoryError && branchInventory && (
                  <BranchInventoryGrid
                    products={branchInventory.products}
                    branchName={activeBranch.name}
                    onReserveClick={handleReserveClick}
                  />
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Reservation Confirmation Modal */}
      {reservationNotice && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reservation-title"
        >
          <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-md w-full shadow-2xl border border-neutral-200 space-y-4">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                {t('brands.bopis_hold_requested')}
              </span>
              <button data-motion="neutral" data-motion-tone="icon"
                type="button"
                onClick={() => setReservationNotice(null)}
                className="text-brand-muted hover:text-neutral-600 text-sm font-bold"
                aria-label={t('brands.close_dialog')}
              >
                ✕
              </button>
            </div>

            <div className="space-y-1">
              <h3 id="reservation-title" className="font-serif text-xl font-bold text-brand-charcoal">
                {t('brands.held_at_branch')}
              </h3>
              <p className="text-xs text-neutral-600">
                {t('brands.held_notice', { name: reservationNotice.branchName })}
              </p>
            </div>

            <div className="flex items-center gap-3.5 p-3.5 rounded-2xl bg-neutral-50 border border-neutral-200">
              <img
                src={reservationNotice.item.thumbnail_url}
                alt={reservationNotice.item.title}
                className="h-14 w-14 rounded-xl object-cover"
              />
              <div className="space-y-0.5 text-xs">
                <p className="font-bold text-brand-charcoal line-clamp-1">
                  {reservationNotice.item.title}
                </p>
                <p className="text-neutral-500">
                  Size: <span className="font-semibold text-brand-charcoal">{reservationNotice.sku.size}</span> • {reservationNotice.sku.color}
                </p>
                <p className="font-bold text-brand-charcoal">
                  {reservationNotice.item.currency} {Number(reservationNotice.item.base_price).toLocaleString()}
                </p>
              </div>
            </div>

            <p className="text-[11px] text-neutral-500 leading-relaxed">
              {t('brands.hold_policy_desc')}
            </p>

            <div className="pt-2">
              <button data-motion="progressive"
                type="button"
                onClick={() => setReservationNotice(null)}
                className="w-full py-3 rounded-xl bg-brand-charcoal text-white text-xs font-bold hover:bg-neutral-800 transition-colors"
              >
                {t('brands.done')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
