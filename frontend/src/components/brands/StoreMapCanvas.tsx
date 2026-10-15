import React from 'react';
import type { StoreBranchSummary } from '../../models';

interface StoreMapCanvasProps {
  branches: StoreBranchSummary[];
  selectedBranchId: number | null;
  onSelectBranch: (branchId: number) => void;
  brandName?: string;
}

export const StoreMapCanvas: React.FC<StoreMapCanvasProps> = ({
  branches,
  selectedBranchId,
  onSelectBranch,
  brandName,
}) => {
  const selectedBranch = branches.find((b) => b.id === selectedBranchId) || branches[0];

  return (
    <div className="relative h-full w-full min-h-[320px] bg-neutral-100 rounded-2xl overflow-hidden border border-neutral-200 flex flex-col justify-between shadow-xs">
      {/* Map Background Pattern */}
      <div
        className="absolute inset-0 bg-[radial-gradient(#d1d5db_1.2px,transparent_1.2px)] [background-size:20px_20px] bg-neutral-50/90"
        aria-hidden="true"
      />

      {/* Top Map Context Info Bar */}
      <div className="relative z-10 m-4 flex items-center justify-between pointer-events-none">
        <div className="pointer-events-auto inline-flex items-center gap-2 rounded-xl bg-white/95 backdrop-blur-md px-3.5 py-2 shadow-sm border border-neutral-200">
          <span className="h-2 w-2 rounded-full bg-brand-coral animate-ping" />
          <span className="text-xs font-bold text-brand-charcoal">
            {brandName ? `${brandName} Locations (${branches.length})` : `Partner Stores (${branches.length})`}
          </span>
        </div>

        {selectedBranch && (
          <div className="pointer-events-auto hidden sm:inline-flex items-center gap-2 rounded-xl bg-white/90 backdrop-blur-md px-3 py-1.5 shadow-sm border border-neutral-200 text-[11px] font-semibold text-neutral-600">
            <span>Coordinates: {selectedBranch.latitude.toFixed(4)}, {selectedBranch.longitude.toFixed(4)}</span>
          </div>
        )}
      </div>

      {/* Markers Container */}
      <div className="relative z-10 flex-1 flex items-center justify-center p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl w-full">
          {branches.map((b) => {
            const isTarget = b.id === selectedBranch?.id;
            return (
              <button data-motion="neutral"
                key={b.id}
                type="button"
                onClick={() => onSelectBranch(b.id)}
                className={`flex items-center gap-3 p-3 rounded-xl border text-left transition-all ${
                  isTarget
                    ? 'bg-brand-charcoal text-white border-brand-charcoal shadow-md ring-2 ring-brand-mint scale-102'
                    : 'bg-white/95 text-brand-charcoal border-neutral-300 hover:bg-white hover:border-neutral-400'
                }`}
                aria-label={`Select branch ${b.name}`}
              >
                <div
                  className={`p-2 rounded-lg shrink-0 ${
                    isTarget ? 'bg-neutral-800 text-brand-coral' : 'bg-neutral-100 text-brand-coral'
                  }`}
                >
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                    <path
                      fillRule="evenodd"
                      d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
                <div className="truncate flex-1">
                  <div className="text-xs font-bold truncate">{b.name}</div>
                  <div className={`text-[11px] truncate ${isTarget ? 'text-neutral-300' : 'text-neutral-500'}`}>
                    {b.city} {b.distance_km ? `• ${b.distance_km} km` : ''}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Bottom Floating Navigation Action Bar */}
      {selectedBranch && (
        <div className="relative z-10 m-4 p-4 rounded-xl bg-white/95 backdrop-blur-md border border-neutral-200 shadow-md flex items-center justify-between gap-4">
          <div className="text-left truncate">
            <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-wider block">
              Active Store Destination
            </span>
            <p className="font-serif text-sm font-bold text-brand-charcoal truncate">
              {selectedBranch.name}
            </p>
            <p className="text-xs text-neutral-500 truncate">
              {selectedBranch.address}, {selectedBranch.city}
            </p>
          </div>

          <a
            href={selectedBranch.google_maps_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex shrink-0 items-center gap-1.5 px-4 py-2.5 rounded-xl bg-brand-coral text-white text-xs font-bold hover:bg-brand-coral/90 shadow-xs transition-colors"
          >
            Launch Route
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        </div>
      )}
    </div>
  );
};
