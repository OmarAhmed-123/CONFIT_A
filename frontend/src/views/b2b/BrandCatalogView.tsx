import React, { useState, useRef } from 'react';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const BrandCatalogView: React.FC = () => {
  const { products, updateSKUInventory, isLoading, uploadCatalogCSV, importJobs, isUploading } = useBrandViewModel();
  const [editingSkuId, setEditingSkuId] = useState<number | null>(null);
  const [editStock, setEditStock] = useState<number>(20);
  const [editPrice, setEditPrice] = useState<number | undefined>(undefined);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [lastImportResult, setLastImportResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (isLoading) {
    return <LoadingSpinner text="Loading brand catalog and SKU inventory..." />;
  }

  const handleSaveSku = (skuId: number) => {
    updateSKUInventory(skuId, editStock, editPrice);
    setEditingSkuId(null);
  };

  const handleFileUpload = async (file: File) => {
    if (!file.name.endsWith('.csv')) {
      alert('File must be CSV');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert('File exceeds 10MB limit');
      return;
    }
    try {
      const result = await uploadCatalogCSV(file);
      setLastImportResult(result);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
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
            Real-time stock level synchronization across warehouse, BOPIS store locations, and AI try-on engines. CSV import with validation, idempotency, and error reporting.
          </p>
        </div>

        <button
          onClick={() => setBulkModalOpen(true)}
          className="px-4 py-2.5 rounded-2xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white text-xs font-semibold shadow-sm transition-all"
        >
          + Bulk CSV Import
        </button>
      </div>

      {/* Import Jobs History */}
      {importJobs.length > 0 && (
        <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">Recent Import Jobs</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400 uppercase text-[10px]">
                  <th className="py-2">Job ID</th>
                  <th className="py-2">File</th>
                  <th className="py-2">Status</th>
                  <th className="py-2">Total</th>
                  <th className="py-2">Accepted</th>
                  <th className="py-2">Rejected</th>
                  <th className="py-2">Duplicate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {importJobs.slice(0, 5).map((job) => (
                  <tr key={job.job_id} className="hover:bg-slate-50">
                    <td className="py-2 font-mono">#{job.job_id}</td>
                    <td className="py-2 truncate max-w-[150px]">{job.file_name || 'API import'}</td>
                    <td className="py-2">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        job.status === 'completed' ? 'bg-emerald-100 text-emerald-800' :
                        job.status === 'partially_completed' ? 'bg-amber-100 text-amber-800' :
                        job.status === 'failed' ? 'bg-rose-100 text-rose-800' :
                        'bg-slate-100 text-slate-600'
                      }`}>{job.status}</span>
                    </td>
                    <td className="py-2">{job.total_rows}</td>
                    <td className="py-2 text-emerald-600 font-bold">{job.accepted_rows}</td>
                    <td className="py-2 text-rose-600">{job.rejected_rows}</td>
                    <td className="py-2 text-amber-600">{job.duplicate_rows}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Last Import Result */}
      {lastImportResult && (
        <div className={`rounded-3xl border p-6 space-y-3 ${lastImportResult.status === 'completed' ? 'bg-emerald-50 border-emerald-200' : lastImportResult.status === 'partially_completed' ? 'bg-amber-50 border-amber-200' : 'bg-rose-50 border-rose-200'}`}>
          <h4 className="font-bold text-sm">Last Import: {lastImportResult.status}</h4>
          <div className="grid grid-cols-4 gap-3 text-xs">
            <div><span className="text-slate-500">Total:</span> <strong>{lastImportResult.total_rows}</strong></div>
            <div><span className="text-slate-500">Accepted:</span> <strong className="text-emerald-600">{lastImportResult.accepted_rows}</strong></div>
            <div><span className="text-slate-500">Rejected:</span> <strong className="text-rose-600">{lastImportResult.rejected_rows}</strong></div>
            <div><span className="text-slate-500">Duplicate:</span> <strong className="text-amber-600">{lastImportResult.duplicate_rows}</strong></div>
          </div>
          {lastImportResult.errors && lastImportResult.errors.length > 0 && (
            <div className="pt-3 border-t border-slate-200">
              <span className="text-xs font-bold text-slate-700 block mb-2">Errors (first 10):</span>
              <div className="space-y-1 max-h-40 overflow-y-auto text-[11px]">
                {lastImportResult.errors.slice(0, 10).map((err: any, idx: number) => (
                  <div key={idx} className="p-2 rounded bg-white border border-slate-200">
                    <span className="font-bold">Row {err.row} - {err.field}:</span> {err.message} {err.value ? `(${err.value})` : ''}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Product & SKU Table */}
      <div className="space-y-6">
        {products.length === 0 ? (
          <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center space-y-3">
            <div className="text-4xl">📦</div>
            <h3 className="font-serif text-lg font-bold text-slate-700">No products yet</h3>
            <p className="text-xs text-slate-500">Upload your catalog via CSV to get started. Required columns: title, category_slug, base_price, color_family, thumbnail_url</p>
            <button onClick={() => setBulkModalOpen(true)} className="mt-3 px-4 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold">Upload CSV</button>
          </div>
        ) : (
          products.map((p) => (
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
                    <span className="text-[10px] text-slate-400 ml-2">ID: {p.id}</span>
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
                      <th className="py-2">Price Override</th>
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
                              min={0}
                              max={100000}
                            />
                          ) : (
                            <span className={`font-bold ${sku.stock_level > 5 ? 'text-slate-900' : 'text-rose-600'}`}>
                              {sku.stock_level} units
                            </span>
                          )}
                        </td>
                        <td className="py-3">
                          {editingSkuId === sku.id ? (
                            <input
                              type="number"
                              step="0.01"
                              value={editPrice ?? sku.price_override ?? ''}
                              onChange={(e) => setEditPrice(e.target.value ? Number(e.target.value) : undefined)}
                              placeholder={String(p.base_price)}
                              className="w-20 px-2 py-1 rounded border border-slate-300 text-xs"
                            />
                          ) : (
                            <span className="font-mono">${sku.price_override ?? p.base_price}</span>
                          )}
                        </td>
                        <td className="py-3">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${sku.is_in_stock ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-rose-50 text-rose-700 border-rose-200'}`}>
                            {sku.is_in_stock ? 'BOPIS Active' : 'Out of Stock'}
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
                                setEditPrice(sku.price_override);
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
          ))
        )}
      </div>

      {/* Bulk CSV Modal - REAL IMPLEMENTATION */}
      {bulkModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-white rounded-3xl p-6 shadow-2xl space-y-4">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">Bulk SKU Catalog Importer</h3>
            <div className="text-xs text-slate-600 space-y-2">
              <p>Upload CSV with required columns: <code className="px-1.5 py-0.5 bg-slate-100 rounded text-[10px]">title, category_slug, base_price, color_family, thumbnail_url</code></p>
              <p>Optional: title_ar, description, material, currency, style_tags, sku_code, size, color, stock_level, price_override, images</p>
              <p className="text-[11px] text-amber-700 bg-amber-50 p-2 rounded">Security: Formula injection protection, MIME validation, 10MB limit, SKU uniqueness enforced, upsert semantics, transactional.</p>
            </div>

            <div
              onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${dragActive ? 'border-[#1B1F3B] bg-[#1B1F3B]/5' : 'border-slate-300 bg-[#FAF9F6]'} ${isUploading ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleFileInputChange}
                className="hidden"
              />
              {isUploading ? (
                <div className="space-y-2">
                  <div className="animate-spin w-6 h-6 border-2 border-[#1B1F3B] border-t-transparent rounded-full mx-auto"></div>
                  <div className="text-xs font-semibold text-[#1B1F3B]">Processing CSV...</div>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-2xl">📤</div>
                  <div className="text-xs text-slate-600 font-semibold">Drop CSV catalog file here or click to browse</div>
                  <div className="text-[10px] text-slate-400">Max 10MB, UTF-8, headers required</div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setBulkModalOpen(false)} className="px-4 py-2 rounded-xl border text-xs font-semibold" disabled={isUploading}>
                Cancel
              </button>
              <button onClick={() => fileInputRef.current?.click()} className="px-4 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold" disabled={isUploading}>
                Browse Files
              </button>
            </div>

            <div className="pt-3 border-t border-slate-100 text-[11px] text-slate-500">
              <span className="font-bold">Sample CSV:</span>
              <pre className="mt-1 p-2 bg-slate-50 rounded text-[10px] overflow-x-auto">
title,category_slug,base_price,color_family,thumbnail_url,size,color,stock_level
"Tailored Blazer",outerwear,299.99,Navy,https://example.com/blazer.jpg,M,Navy,20
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
