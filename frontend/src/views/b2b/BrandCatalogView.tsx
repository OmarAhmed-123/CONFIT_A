import React, { useState } from 'react';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const BrandCatalogView: React.FC = () => {
  const { products, updateSKUInventory, isLoading } = useBrandViewModel();
  const [editingSkuId, setEditingSkuId] = useState<number | null>(null);
  const [editStock, setEditStock] = useState<number>(20);
  const [editPrice, setEditPrice] = useState<number | undefined>(undefined);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);

  if (isLoading) {
    return <LoadingSpinner text="Loading brand catalog and SKU inventory..." />;
  }

  const handleSaveSku = (skuId: number) => {
    updateSKUInventory(skuId, editStock, editPrice);
    setEditingSkuId(null);
  };

  return (
    <div className="space-y-8 pb-20">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
            Catalog & SKU Management
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Real-time stock level synchronization across warehouse, BOPIS store locations, and AI try-on engines.
          </p>
        </div>

        <button
          onClick={() => setBulkModalOpen(true)}
          className="px-4 py-2.5 rounded-2xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white text-xs font-semibold shadow-sm transition-all"
        >
          + Bulk CSV Import
        </button>
      </div>

      {/* Product & SKU Table */}
      <div className="space-y-6">
        {products.map((p) => (
          <div key={p.id} className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-14 h-16 rounded-xl bg-slate-100 overflow-hidden shrink-0">
                  <img src={p.thumbnail_url} alt={p.title} className="w-full h-full object-cover" />
                </div>
                <div>
                  <span className="text-[10px] font-bold text-slate-400 uppercase">{p.category_name}</span>
                  <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{p.title}</h3>
                  <span className="text-xs font-bold text-[#B8935A]">${p.base_price}</span>
                </div>
              </div>
            </div>

            {/* SKUs Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-slate-400 uppercase text-[10px] tracking-wider">
                    <th className="py-2">SKU Code</th>
                    <th className="py-2">Size</th>
                    <th className="py-2">Color</th>
                    <th className="py-2">Warehouse Stock</th>
                    <th className="py-2">BOPIS Status</th>
                    <th className="py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {p.skus?.map((sku) => (
                    <tr key={sku.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-3 font-mono font-semibold text-slate-900">{sku.sku_code}</td>
                      <td className="py-3 font-bold">{sku.size}</td>
                      <td className="py-3 flex items-center gap-1.5">
                        <span className="w-3 h-3 rounded-full border border-slate-300" style={{ backgroundColor: sku.color_hex }}></span>
                        <span>{sku.color}</span>
                      </td>
                      <td className="py-3">
                        {editingSkuId === sku.id ? (
                          <input
                            type="number"
                            value={editStock}
                            onChange={(e) => setEditStock(Number(e.target.value))}
                            className="w-20 px-2 py-1 rounded border border-slate-300 text-xs font-bold"
                          />
                        ) : (
                          <span className={`font-bold ${sku.stock_level > 5 ? 'text-slate-900' : 'text-rose-600'}`}>
                            {sku.stock_level} units
                          </span>
                        )}
                      </td>
                      <td className="py-3">
                        <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200">
                          BOPIS Active
                        </span>
                      </td>
                      <td className="py-3 text-right">
                        {editingSkuId === sku.id ? (
                          <div className="flex justify-end gap-1.5">
                            <button
                              onClick={() => handleSaveSku(sku.id)}
                              className="px-3 py-1 rounded bg-[#1B1F3B] text-white text-[10px] font-bold"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingSkuId(null)}
                              className="px-2 py-1 rounded border border-slate-200 text-[10px]"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => {
                              setEditingSkuId(sku.id);
                              setEditStock(sku.stock_level);
                            }}
                            className="text-xs font-bold text-[#B8935A] hover:underline"
                          >
                            Edit Stock
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>

      {/* Bulk CSV Modal */}
      {bulkModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-white rounded-3xl p-6 shadow-2xl space-y-4">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">Bulk SKU Catalog Importer</h3>
            <p className="text-xs text-slate-500">
              Upload a CSV file containing columns: `sku_code`, `title`, `category`, `size`, `color`, `stock_level`, `price`, `images`.
            </p>
            <div className="border-2 border-dashed border-slate-300 rounded-2xl p-8 text-center bg-[#FAF9F6] text-xs text-slate-500">
              Drop CSV catalog file here or click to browse
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setBulkModalOpen(false)} className="px-4 py-2 rounded-xl border text-xs font-semibold">
                Cancel
              </button>
              <button onClick={() => setBulkModalOpen(false)} className="px-4 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold">
                Import SKUs
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
