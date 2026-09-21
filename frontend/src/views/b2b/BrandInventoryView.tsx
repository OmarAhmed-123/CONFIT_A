import { useTranslation } from 'react-i18next';
import { useModalFocus } from '../../hooks/useModalFocus';
import { useCallback } from 'react';
import React, { useState, useEffect } from 'react';
import { BopisIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';
import { request } from '../../services/apiClient';

interface Store {
  id: number;
  name: string;
  city: string;
  country: string;
  address: string;
  is_bopis_enabled: boolean;
  created_at?: string;
}

interface InventoryItem {
  product_id: number;
  title: string;
  thumbnail_url: string;
  total_stock: number;
  skus: Array<{
    id: number;
    sku_code: string;
    size: string;
    color: string;
    stock_level: number;
    is_in_stock: boolean;
    store_inventories: Array<{ store_id: number; quantity: number; reserved: number; available: number }>;
  }>;
}

export const BrandInventoryView: React.FC = () => {
  const { t } = useTranslation();
  const [stores, setStores] = useState<Store[]>([]);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  // Silent-fallback fix (C6 rule, B2B surface): these fetches used to launder
  // errors into empty arrays, making a backend outage indistinguishable from
  // a brand that genuinely has zero stores / zero inventory rows. Failures
  // are now recorded and rendered as an explicit error + Retry.
  const [fetchErrors, setFetchErrors] = useState<Record<'stores' | 'inventory', string | null>>({ stores: null, inventory: null });
  const [stockForm, setStockForm] = useState({ store_id: '', sku_id: '', quantity: '' });
  const [savingStock, setSavingStock] = useState(false);
  const [stockMessage, setStockMessage] = useState('');
  const [showStoreModal, setShowStoreModal] = useState(false);
  const [newStore, setNewStore] = useState({ name: '', city: '', country: 'UAE', address: '', latitude: 0, longitude: 0, phone: '' });

  const fetchData = async () => {
    setIsLoading(true);
    const [storesRes, invRes] = await Promise.allSettled([
      request<Store[]>('/partner/stores'),
      request<InventoryItem[]>('/partner/inventory'),
    ]);
    if (storesRes.status === 'fulfilled') setStores(storesRes.value);
    else setStores([]);
    if (invRes.status === 'fulfilled') setInventory(invRes.value);
    else setInventory([]);
    setFetchErrors({
      stores: storesRes.status === 'rejected' ? ((storesRes.reason as any)?.message || 'Failed to load store locations.') : null,
      inventory: invRes.status === 'rejected' ? ((invRes.reason as any)?.message || 'Failed to load inventory.') : null,
    });
    setIsLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateStore = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await request('/partner/stores', { method: 'POST', body: JSON.stringify(newStore) });
      setShowStoreModal(false);
      setNewStore({ name: '', city: '', country: 'UAE', address: '', latitude: 0, longitude: 0, phone: '' });
      fetchData();
    } catch (err: any) {
      alert('Failed to create store: ' + err.message);
    }
  };

  const saveStoreStock = async (event: React.FormEvent) => {
    event.preventDefault();
    if (savingStock) return;
    setSavingStock(true); setStockMessage('');
    try {
      await request('/partner/inventory', { method: 'POST', body: JSON.stringify({
        store_id: Number(stockForm.store_id), sku_id: Number(stockForm.sku_id), quantity: Number(stockForm.quantity),
      }) });
      setStockMessage('Store inventory saved. Warehouse stock was not changed.');
      await fetchData();
    } catch (error: any) { setStockMessage(`Not saved: ${error.message}`); }
    finally { setSavingStock(false); }
  };

  const closeDialog = useCallback(() => { if (!savingStock) setShowStoreModal(false); }, [savingStock]);
  const dialogRef = useModalFocus<HTMLDivElement>(closeDialog, showStoreModal);

  if (isLoading) {
    return <LoadingSpinner text={t('partnerPortal.text089')} />;
  }

  return (
    <div className="space-y-8 pb-20">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">{' '}{t('partnerPortal.text090')}{' '}</h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">{' '}{t('partnerPortal.text091')}{' '}</p>
          <p className="text-[11px] text-slate-400 mt-1">{t('partnerPortal.text092')}</p>
        </div>
        <button onClick={() => setShowStoreModal(true)} className="px-4 py-2.5 rounded-2xl bg-[#1B1F3B] text-white text-xs font-semibold">{t('partnerPortal.text093')}</button>
      </div>

      {/* Stores - REAL */}
      <div className="space-y-4">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">{t('partnerPortal.text094')}{stores.length}{t('partnerPortal.text095')}</h3>
        {fetchErrors.stores && (
          <div role="alert" className="p-4 rounded-2xl bg-rose-50 border border-rose-200">
            <p className="text-[11px] font-bold text-rose-800">{t('partnerPortal.text096')}</p>
            <p className="text-[11px] text-rose-600 mt-1">{fetchErrors.stores}{' '}{t('partnerPortal.text097')}</p>
            <button onClick={fetchData} className="mt-2 px-3 py-1.5 rounded-lg bg-white border border-rose-200 text-[11px] font-bold text-rose-700 hover:bg-rose-50">{t('partnerPortal.text005')}</button>
          </div>
        )}
        {!fetchErrors.stores && stores.length === 0 ? (
          <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center space-y-3">
            <div className="text-4xl">🏪</div>
            <h3 className="font-bold text-slate-700">{t('partnerPortal.text098')}</h3>
            <p className="text-xs text-slate-500">{t('partnerPortal.text099')}</p>
            <button onClick={() => setShowStoreModal(true)} className="mt-2 px-4 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold">{t('partnerPortal.text100')}</button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {stores.map((b) => (
              <div key={b.id} className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[#FAF9F6] border border-slate-200 flex items-center justify-center text-[#1B1F3B]">
                    <BopisIcon size={20} color="#1B1F3B" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-serif text-base font-bold text-[#1B1F3B] truncate">{b.name}</h3>
                    <span className="text-xs text-slate-500">{b.city}, {b.country}</span>
                    <div className="text-[10px] text-slate-400 truncate">{b.address}</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-100">
                  <div className="p-2.5 rounded-xl bg-[#FAF9F6]">
                    <span className="text-slate-400 text-[10px] block">{t('partnerPortal.text101')}</span>
                    <span className={`font-bold ${b.is_bopis_enabled ? 'text-emerald-600' : 'text-slate-400'}`}>{b.is_bopis_enabled ? 'Enabled' : 'Disabled'}</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-[#FAF9F6]">
                    <span className="text-slate-400 text-[10px] block">{t('partnerPortal.text102')}</span>
                    <span className="font-mono font-bold">#{b.id}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs pt-1">
                  <span className="text-emerald-700 font-semibold text-[11px] flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                    <span>{t('partnerPortal.text103')}</span>
                  </span>
                  <span className="text-[10px] text-slate-400">{b.created_at ? new Date(b.created_at).toLocaleDateString() : ''}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <form onSubmit={saveStoreStock} aria-label={t('b2b.form_set_stock')} className="rounded-2xl border bg-white p-5 space-y-3">
        <h3 className="font-bold">{t('b2b.form_set_stock_title')}</h3>
        <p className="text-xs text-slate-500">{t('partnerPortal.text104')}</p>
        <div className="flex flex-wrap gap-3">
          <select aria-label={t('b2b.field_store')} required value={stockForm.store_id} onChange={e => setStockForm({...stockForm, store_id: e.target.value})} className="border rounded p-2">
            <option value="">{t('b2b.choose_store')}</option>
            {stores.map(store => <option key={store.id} value={store.id}>{store.name}</option>)}
          </select>
          <select aria-label={t('b2b.field_sku')} required value={stockForm.sku_id} onChange={e => setStockForm({...stockForm, sku_id: e.target.value})} className="border rounded p-2">
            <option value="">{t('b2b.choose_sku')}</option>
            {inventory.flatMap(item => item.skus.map(sku => <option key={sku.id} value={sku.id}>{item.title} — {sku.sku_code}</option>))}
          </select>
          <input aria-label={t('b2b.field_on_hand')} required type="number" min="0" max="100000" step="1" value={stockForm.quantity} onChange={e => setStockForm({...stockForm, quantity: e.target.value})} className="border rounded p-2" />
          <button disabled={savingStock || !!fetchErrors.stores || !!fetchErrors.inventory} className="rounded bg-slate-900 text-white px-4 py-2">{savingStock ? t('common.saving') : t('b2b.save_store_stock')}</button>
        </div>
        {stockMessage && <p role="status" className="text-sm">{stockMessage}</p>}
      </form>

      {/* Inventory - REAL */}
      <div className="space-y-4">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">{t('partnerPortal.text105')}</h3>
        <p className="text-[11px] text-slate-500">{t('partnerPortal.text106')}</p>
        {fetchErrors.inventory && (
          <div role="alert" className="p-4 rounded-2xl bg-rose-50 border border-rose-200">
            <p className="text-[11px] font-bold text-rose-800">{t('partnerPortal.text107')}</p>
            <p className="text-[11px] text-rose-600 mt-1">{fetchErrors.inventory}{' '}{t('partnerPortal.text108')}</p>
            <button onClick={fetchData} className="mt-2 px-3 py-1.5 rounded-lg bg-white border border-rose-200 text-[11px] font-bold text-rose-700 hover:bg-rose-50">{t('partnerPortal.text005')}</button>
          </div>
        )}
        {!fetchErrors.inventory && inventory.length === 0 ? (
          <div className="bg-white rounded-3xl border border-slate-200 p-8 text-center text-xs text-slate-500">{' '}{t('partnerPortal.text109')}{' '}</div>
        ) : (
          <div className="space-y-4">
            {inventory.map((item) => (
              <div key={item.product_id} className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-12 h-14 rounded bg-slate-100 overflow-hidden"><img src={item.thumbnail_url} alt={item.title} className="w-full h-full object-cover" /></div>
                  <div>
                    <h4 className="font-bold text-sm text-[#1B1F3B]">{item.title}</h4>
                    <span className="text-xs text-slate-500">{t('partnerPortal.text110')}{' '}{item.total_stock}{' '}{t('partnerPortal.text111')}{' '}{item.skus.length}{' '}{t('partnerPortal.text086')}</span>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-100 text-slate-400 uppercase text-[10px]">
                        <th className="py-2">{t('partnerPortal.text112')}</th>
                        <th className="py-2">{t('partnerPortal.text113')}</th>
                        <th className="py-2">{t('partnerPortal.text114')}</th>
                        <th className="py-2">{t('partnerPortal.text115')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {item.skus.map((sku) => (
                        <tr key={sku.id} className="hover:bg-slate-50">
                          <td className="py-2 font-mono font-bold">{sku.sku_code}</td>
                          <td className="py-2">{sku.size}/{sku.color}</td>
                          <td className="py-2 font-bold">{sku.stock_level}</td>
                          <td className="py-2">
                            <div className="flex flex-wrap gap-1">
                              {sku.store_inventories.length === 0 ? (
                                <span className="text-slate-400">{t('partnerPortal.text116')}</span>
                              ) : (
                                sku.store_inventories.map((si) => (
                                  <span key={si.store_id} className="px-2 py-0.5 rounded-full bg-slate-100 text-[10px]">{' '}{t('partnerPortal.text117')}{si.store_id}: {si.available}{' '}{t('partnerPortal.text118')}{si.quantity}{' '}{t('partnerPortal.text119')}{' '}{si.reserved}{' '}{t('partnerPortal.text120')}{' '}</span>
                                ))
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Store Modal - REAL */}
      {showStoreModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
          <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={t('b2b.modal_add_store')} tabIndex={-1} className="w-full max-w-md bg-white rounded-3xl p-6 shadow-2xl space-y-4">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">{t('partnerPortal.text121')}</h3>
            <p className="text-[11px] text-slate-500">{t('partnerPortal.text122')}</p>
            <form onSubmit={handleCreateStore} className="space-y-3 text-xs">
              <div>
                <label className="font-bold block mb-1">{t('partnerPortal.text123')}</label>
                <input aria-label={t('b2b.field_store_name')} value={newStore.name} onChange={(e) => setNewStore({ ...newStore, name: e.target.value })} required className="w-full p-2.5 rounded-xl border" placeholder={t('partnerPortal.text124')} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-bold block mb-1">{t('partnerPortal.text125')}</label>
                  <input aria-label={t('b2b.field_store_city')} value={newStore.city} onChange={(e) => setNewStore({ ...newStore, city: e.target.value })} required className="w-full p-2.5 rounded-xl border" placeholder={t('partnerPortal.text126')} />
                </div>
                <div>
                  <label className="font-bold block mb-1">{t('partnerPortal.text127')}</label>
                  <input aria-label={t('b2b.field_store_country')} value={newStore.country} onChange={(e) => setNewStore({ ...newStore, country: e.target.value })} required className="w-full p-2.5 rounded-xl border" placeholder={t('partnerPortal.text128')} />
                </div>
              </div>
              <div>
                <label className="font-bold block mb-1">{t('partnerPortal.text129')}</label>
                <input aria-label={t('b2b.field_store_address')} value={newStore.address} onChange={(e) => setNewStore({ ...newStore, address: e.target.value })} required className="w-full p-2.5 rounded-xl border" placeholder={t('partnerPortal.text130')} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-bold block mb-1">{t('partnerPortal.text131')}</label>
                  <input type="number" step="0.000001" aria-label={t('b2b.field_store_lat')} value={newStore.latitude} onChange={(e) => setNewStore({ ...newStore, latitude: Number(e.target.value) })} className="w-full p-2.5 rounded-xl border" />
                </div>
                <div>
                  <label className="font-bold block mb-1">{t('partnerPortal.text132')}</label>
                  <input type="number" step="0.000001" aria-label={t('b2b.field_store_lng')} value={newStore.longitude} onChange={(e) => setNewStore({ ...newStore, longitude: Number(e.target.value) })} className="w-full p-2.5 rounded-xl border" />
                </div>
              </div>
              <div>
                <label className="font-bold block mb-1">{t('partnerPortal.text133')}</label>
                <input aria-label={t('b2b.field_store_phone')} value={newStore.phone} onChange={(e) => setNewStore({ ...newStore, phone: e.target.value })} className="w-full p-2.5 rounded-xl border" placeholder={t('partnerPortal.text134')} />
              </div>
              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => setShowStoreModal(false)} className="flex-1 py-2.5 rounded-xl border font-semibold">{t('partnerPortal.text033')}</button>
                <button type="submit" className="flex-1 py-2.5 rounded-xl bg-[#1B1F3B] text-white font-semibold">{t('partnerPortal.text135')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
