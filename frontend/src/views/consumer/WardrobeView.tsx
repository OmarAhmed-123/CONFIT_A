import React, { useCallback, useRef, useState } from "react";
import { useModalFocus } from "../../hooks/useModalFocus";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { compressImageToDataUrl } from "../../lib/imageUpload";
import { useCapabilities } from "../../hooks/useCapabilities";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { msg } from "../../i18n/messages";
import { useWardrobeViewModel } from "../../viewmodels/useWardrobeViewModel";
import { useAuthStore } from "../../stores/authStore";
import { stylistService } from "../../services/apiServices";
import { Outfit } from "../../models";
import { useUIStore } from "../../stores/uiStore";
import {
  WardrobeIcon,
  SavedLooksIcon,
  GapAnalysisIcon,
  SparkleIcon,
  BagIcon,
  TryOnIcon,
} from "../../components/icons/ConfitIcons";
import {
  LoadingSpinner,
  EmptyState,
  FitScoreBadge,
} from "../../components/common/CommonComponents";
import {
  CardStackShowcase,
  CircularGalleryShowcase,
} from "../../components/showcase/DesignShowcases";

const MANUAL_WARDROBE_IMAGE =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 750"><rect width="600" height="750" fill="%23F8FAFC"/><rect x="90" y="120" width="420" height="510" rx="42" fill="%23FFFFFF" stroke="%23CBD5E1" stroke-width="4"/><text x="300" y="345" text-anchor="middle" font-family="Arial,sans-serif" font-size="32" font-weight="700" fill="%231B1F3B">Manual wardrobe item</text><text x="300" y="395" text-anchor="middle" font-family="Arial,sans-serif" font-size="22" fill="%2364748B">No photo uploaded</text></svg>',
  );

export const WardrobeView: React.FC = () => {
  const { t } = useTranslation();
  // WARD-01 closure: the 'looks' tab previously rendered a STATIC mock
  // ensemble (hardcoded images, $529.00, score 97) regardless of the user's
  // data. Saved looks now come from the real backend (GET /outfits); guests
  // get an honest sign-in prompt instead of fabricated content.
  const { isAuthenticated } = useAuthStore();
  const queryClient = useQueryClient();
  const savedLooksQuery = useQuery({
    queryKey: ["wardrobe", "saved-looks"],
    queryFn: () => stylistService.getSavedOutfits(),
    enabled: isAuthenticated,
    staleTime: 30_000,
  });
  const savedLooks: Outfit[] = savedLooksQuery.data ?? [];
  const [deletingLookId, setDeletingLookId] = useState<number | null>(null);
  const handleDeleteLook = async (id: number) => {
    setDeletingLookId(id);
    try {
      await stylistService.deleteOutfit(id);
      await queryClient.invalidateQueries({
        queryKey: ["wardrobe", "saved-looks"],
      });
    } finally {
      setDeletingLookId(null);
    }
  };

  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const initialTab = searchParams.get("tab") || "closet";
  const { capabilities } = useCapabilities();
  const photoUploadUnavailable = capabilities.storage_mode === "local";

  const [activeTab, setActiveTab] = useState<"closet" | "looks" | "gaps" | "boards">(
    initialTab as any,
  );
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const closeUploadModal = useCallback(() => setUploadModalOpen(false), []);
  const uploadPanelRef = useModalFocus<HTMLDivElement>(
    closeUploadModal,
    uploadModalOpen,
  );
  const [newTitle, setNewTitle] = useState("");
  const [newCategory, setNewCategory] = useState("Outerwear");
  const [newColor, setNewColor] = useState("Navy Blue");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isCompressing, setIsCompressing] = useState(false);
  const [uploadSkipNotes, setUploadSkipNotes] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const {
    items,
    activeCategory,
    setActiveCategory,
    isLoading,
    isClosetError,
    fetchWardrobe,
    gapAnalyses,
    isGapLoading,
    isGapError,
    hasLoadedGaps,
    fetchGaps,
    moodBoards,
    isBoardsLoading,
    isBoardsError,
    hasLoadedBoards,
    fetchMoodBoards,
    createMoodBoard,
    renameMoodBoard,
    deleteMoodBoard,
    addMoodBoardTile,
    removeMoodBoardTile,
    uploadMoodBoardTile,
    isAutoTagging,
    autoTagResult,
    autoTagUpload,
    addNewItem,
    deleteItem,
    uploadFiles,
    isUploading,
    uploadReport,
    retryAnalysis,
    retryingItemId,
    toggleFavorite,
    setWearFrequency,
    outfitSuggestion,
    isOutfitLoading,
    fetchOutfitSuggestion,
  } = useWardrobeViewModel();

  // Mood-board local UI state (form + per-board busy flags)
  const [newBoardTitle, setNewBoardTitle] = useState("");
  const [newTileUrl, setNewTileUrl] = useState("");
  const [busyBoardId, setBusyBoardId] = useState<number | null>(null);
  const [renamingBoardId, setRenamingBoardId] = useState<number | null>(null);
  const [renameTitle, setRenameTitle] = useState("");

  const { openTryOn, showToast } = useUIStore();

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    addNewItem({
      title: newTitle || "Custom Wardrobe Item",
      category: newCategory,
      color_name: newColor,
      image_url: MANUAL_WARDROBE_IMAGE,
      wear_frequency: "regular",
      is_favorite: false,
    });
    setUploadModalOpen(false);
    setNewTitle("");
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    // Client-side validation mirrors the backend contract (BRD §12.2).
    const valid = files.filter((f) => {
      if (!["image/jpeg", "image/png", "image/webp"].includes(f.type)) {
        return false;
      }
      return f.size <= 15 * 1024 * 1024;
    });
    if (valid.length !== files.length) {
      alert(
        "Some files were skipped: only JPEG/PNG/WebP up to 15MB are supported.",
      );
    }
    setSelectedFiles(valid.slice(0, 20));
    setUploadSkipNotes([]);
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFiles.length) return;
    // P0-03 fix: multipart bodies hit the same ~4.5 MB serverless gateway
    // ceiling as JSON bodies. Compress every garment photo client-side
    // (≤1024px, JPEG q0.85, ≤3 MB) before it enters the FormData.
    setIsCompressing(true);
    try {
      const compressed: File[] = [];
      for (const f of selectedFiles) {
        try {
          const { dataUrl } = await compressImageToDataUrl(f, { maxDim: 1280 });
          const blob = await (await fetch(dataUrl)).blob();
          compressed.push(
            new File([blob], f.name.replace(/\.[^.]+$/, "") + ".jpg", {
              type: "image/jpeg",
            }),
          );
        } catch {
          // A photo that cannot be compressed is skipped and REPORTED, never
          // silently uploaded raw (that would resurrect the 413 failure).
          setUploadSkipNotes((prev) => [
            ...prev,
            t('errors.file_skipped', { name: f.name }),
          ]);
        }
      }
      if (!compressed.length) return;
      const report = await uploadFiles(compressed);
      if (report && report.summary.succeeded > 0) {
        setSelectedFiles([]);
        if (fileInputRef.current) fileInputRef.current.value = "";
        if (report.summary.failed === 0) setUploadModalOpen(false);
      }
    } finally {
      setIsCompressing(false);
    }
  };

  return (
    <div className="space-y-8 pb-20">
      <CardStackShowcase
        tone="wardrobe"
        compact
        eyebrow="Wardrobe Styling Stack"
        title="Reuse owned pieces through premium outfit formulas"
        description="Saved garments become styled rotations instead of a static closet grid, encouraging realistic reuse and smarter recommendations."
      />

      <CircularGalleryShowcase
        tone="wardrobe"
        compact
        eyebrow="Circular Closet Capsules"
        title="A rotating capsule view for your wardrobe stories"
        description="The same component appears here as a wardrobe capsule browser, visually distinct from the stack above."
      />
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <WardrobeIcon size={24} color="#1B1F3B" />
            <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
              {t("wardrobe.title")}
            </h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            {t("wardrobe.subtitle")}
          </p>
        </div>

        {/* Tab Selector & Add Piece Button */}
        <div className="flex items-center gap-3">
          <div className="flex bg-slate-100 p-1 rounded-2xl border border-slate-200">
            <button
              onClick={() => setActiveTab("closet")}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                activeTab === "closet"
                  ? "bg-white text-[#1B1F3B] shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t("nav.my_closet")}
            </button>
            <button
              onClick={() => setActiveTab("looks")}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                activeTab === "looks"
                  ? "bg-white text-[#1B1F3B] shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t("nav.my_looks")}
            </button>
            <button
              onClick={() => {
                setActiveTab("gaps");
                if (isAuthenticated) fetchGaps();
              }}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-1 ${
                activeTab === "gaps"
                  ? "bg-white text-[#B8935A] shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <GapAnalysisIcon size={14} color="#B8935A" />
              <span>{t("nav.gap_analysis")}</span>
            </button>
            <button
              onClick={() => {
                setActiveTab("boards");
                if (isAuthenticated && !hasLoadedBoards) fetchMoodBoards();
              }}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                activeTab === "boards"
                  ? "bg-white text-[#B8935A] shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t("wardrobe.mood_boards_tab")}
            </button>
          </div>

          <button
            onClick={() => setUploadModalOpen(true)}
            className="px-4 py-2.5 rounded-2xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white text-xs font-semibold shadow-sm transition-all"
          >
            + Upload Piece
          </button>
        </div>
      </div>

      {/* TAB 1: My Closet Grid */}
      {activeTab === "closet" && (
        <div className="space-y-6">
          {/* Category Filter Chips */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {[
              "All",
              "Outerwear",
              "Tops",
              "Bottoms",
              "Footwear",
              "Accessories",
            ].map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all ${
                  activeCategory === cat
                    ? "bg-[#1B1F3B] text-white shadow-xs"
                    : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {isLoading ? (
            <LoadingSpinner text="Scanning your wardrobe..." />
          ) : isClosetError ? (
            /* Honest error state: a failed fetch is NOT an empty wardrobe. */
            <div
              role="alert"
              className="rounded-[32px] border border-rose-200 bg-rose-50 p-6 text-center"
            >
              <p className="text-sm font-semibold text-rose-800">
                {t("wardrobe.closet_load_failed")}
              </p>
              <p className="text-xs text-rose-600 mt-1">{isClosetError}</p>
              <button
                onClick={() => fetchWardrobe(activeCategory)}
                className="mt-4 px-5 py-2.5 rounded-2xl bg-[#1B1F3B] text-white text-xs font-bold hover:bg-[#2A3C78] transition-all"
              >
                {t("common.try_again")}
              </button>
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-[32px] border border-[#C5A059]/25 bg-white p-6 shadow-2xs">
              <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
                <div className="space-y-4">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-[#7A5C28]">
                    Wardrobe retention engine
                  </span>
                  <h2 className="font-serif text-3xl font-bold text-[#1B1F3B]">
                    Upload a few pieces to see what you can wear next
                  </h2>
                  <p className="text-sm font-light leading-relaxed text-slate-500">
                    Start with three everyday garments. Photo uploads are
                    auto-tagged when persistent storage and analysis are
                    available; manual entries remain editable and clearly marked
                    as no-photo items.
                  </p>
                  <div className="rounded-2xl bg-[#FAF9F6] p-3 text-xs text-slate-600">
                    Privacy note: garment photos are sent to the wardrobe
                    backend for this workflow. In this deployment, photo upload
                    availability depends on configured persistent storage.
                  </div>
                  <button
                    onClick={() => setUploadModalOpen(true)}
                    className="rounded-2xl bg-[#1B1F3B] px-5 py-3 text-xs font-bold text-white transition hover:bg-[#C5A059] hover:text-[#0C0E1E]"
                  >
                    Batch upload from gallery →
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500&auto=format&fit=crop&q=80",
                    "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500&auto=format&fit=crop&q=80",
                    "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=500&auto=format&fit=crop&q=80",
                  ].map((src, index) => (
                    <div
                      key={src}
                      className="overflow-hidden rounded-3xl border border-slate-200 bg-slate-100 shadow-sm"
                    >
                      <img
                        src={src}
                        alt={`Example wardrobe upload ${index + 1}`}
                        className="h-56 w-full object-cover"
                      />
                    </div>
                  ))}
                  <div className="col-span-3 rounded-2xl border border-[#C5A059]/25 bg-[#FDF8EE] p-4 text-center text-xs font-semibold text-[#7A5C28]">
                    Upload pieces → see realistic combinations from what you
                    own.
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
              {items.map((item) => (
                <div
                  key={item.id}
                  className="bg-white rounded-3xl border border-slate-200 p-3.5 shadow-sm hover:shadow-lg transition-all flex flex-col justify-between group"
                >
                  <div>
                    <div className="h-64 rounded-2xl overflow-hidden bg-slate-100 mb-3 relative">
                      <img
                        src={item.image_url}
                        alt={item.title}
                        className="w-full h-full object-cover"
                      />
                      <button
                        onClick={() => deleteItem(item.id)}
                        className="absolute top-2 right-2 w-7 h-7 rounded-full bg-black/60 hover:bg-rose-600 text-white flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-all"
                        title="Delete from wardrobe"
                      >
                        ✕
                      </button>
                      {/* Favorite toggle (BRD 4.1: persistent Favorite state) */}
                      <button
                        onClick={() => toggleFavorite(item)}
                        className={`absolute top-2 left-2 w-7 h-7 rounded-full flex items-center justify-center text-xs transition-all ${
                          item.is_favorite
                            ? "bg-[#B8935A] text-white"
                            : "bg-black/40 text-white opacity-0 group-hover:opacity-100"
                        }`}
                        title={
                          item.is_favorite
                            ? "Remove from favorites"
                            : "Mark as favorite"
                        }
                      >
                        ★
                      </button>
                      <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded-full bg-white/90 text-[10px] font-bold text-slate-800">
                        Worn {item.wear_count}x
                      </span>
                      {/* Lifecycle status badge — upload is not 'done' until AI analysis succeeded */}
                      {item.processing_status &&
                        item.processing_status !== "ready" && (
                          <span
                            className={`absolute bottom-2 right-2 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              item.processing_status === "failed"
                                ? "bg-rose-100 text-rose-800"
                                : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {item.processing_status === "failed"
                              ? "AI failed — retry"
                              : "Processing…"}
                          </span>
                        )}
                    </div>

                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                      {item.brand_name}
                    </span>
                    <h3 className="font-serif text-sm font-bold text-[#1B1F3B] truncate mt-0.5">
                      {item.title}
                    </h3>
                    <p className="text-xs text-slate-500">
                      {item.color_name} · {item.category}
                    </p>

                    {/* Persistent wear-state selector: Favorite / Regular / Rarely Worn / Seasonal */}
                    <select
                      value={item.wear_frequency}
                      onChange={(e) => setWearFrequency(item, e.target.value)}
                      className="mt-1.5 w-full px-2 py-1 rounded-lg border border-slate-200 text-[10px] bg-white text-slate-600"
                      title="Wear frequency"
                    >
                      <option value="favorite">★ Favorite</option>
                      <option value="regular">Regular rotation</option>
                      <option value="rarely_worn">Rarely worn</option>
                      <option value="seasonal">Seasonal</option>
                    </select>

                    {/* AI Tags */}
                    {item.ai_tags && item.ai_tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {item.ai_tags.slice(0, 2).map((t) => (
                          <span
                            key={t}
                            className="text-[9px] px-2 py-0.5 rounded-md bg-[#FDF8EE] text-[#B8935A] font-medium border border-[#B8935A]/20"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="pt-3 border-t border-slate-100 mt-3 flex items-center gap-2">
                    {item.processing_status === "failed" ? (
                      <button
                        onClick={() => retryAnalysis(item.id)}
                        disabled={retryingItemId === item.id}
                        className="w-full py-2 rounded-xl bg-rose-50 border border-rose-200 hover:bg-rose-100 text-xs font-semibold text-rose-800 transition-all disabled:opacity-50"
                      >
                        {retryingItemId === item.id
                          ? "Retrying…"
                          : "↻ Retry AI Analysis"}
                      </button>
                    ) : (
                      <button
                        onClick={() => navigate("/builder")}
                        className="w-full py-2 rounded-xl bg-slate-100 hover:bg-[#1B1F3B] hover:text-white text-xs font-semibold text-slate-800 transition-all"
                      >
                        Style in Canvas
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: Saved Outfits + Wardrobe-First Styling (BRD §24) */}
      {activeTab === "looks" && (
        <div className="space-y-6">
          {/* Shop-your-wardrobe-first: build a look from owned pieces; only
              genuine gaps surface purchasable catalog items. */}
          <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
            <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 mb-4">
              <div>
                <h3 className="font-serif text-lg font-bold text-[#1B1F3B] flex items-center gap-2">
                  <SparkleIcon size={18} color="#B8935A" />
                  Shop Your Wardrobe First
                </h3>
                <p className="text-xs text-slate-500">
                  A look built from pieces you already own — only what you're
                  missing is suggested for purchase.
                </p>
              </div>
              <button
                onClick={() => fetchOutfitSuggestion("Smart Casual")}
                disabled={isOutfitLoading}
                className="px-4 py-2 rounded-xl bg-[#B8935A] hover:bg-[#a07f4c] text-white text-xs font-semibold shadow-sm disabled:opacity-50"
              >
                {isOutfitLoading ? "Styling…" : "Build Wardrobe-First Look"}
              </button>
            </div>

            {outfitSuggestion && (
              <div className="space-y-4">
                <p className="text-xs text-slate-600 bg-[#FAF9F6] border border-slate-100 rounded-xl p-3">
                  {outfitSuggestion.message}
                  {outfitSuggestion.owned_count > 0 && (
                    <span className="ml-1 font-semibold text-[#1B1F3B]">
                      Compatibility: {outfitSuggestion.compatibility_score}%
                    </span>
                  )}
                </p>

                {outfitSuggestion.owned_items.length > 0 && (
                  <div>
                    <span className="text-[10px] font-bold text-emerald-700 uppercase tracking-wider">
                      From your closet ({outfitSuggestion.owned_count})
                    </span>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 mt-2">
                      {outfitSuggestion.owned_items.map((it) => (
                        <div
                          key={`owned-${it.wardrobe_item_id}`}
                          className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-2"
                        >
                          <div className="h-24 rounded-xl overflow-hidden bg-white mb-1.5">
                            <img
                              src={it.image_url}
                              alt={it.product_title}
                              className="w-full h-full object-cover"
                            />
                          </div>
                          <span className="text-[9px] font-bold text-emerald-700 uppercase">
                            {it.position} · owned
                          </span>
                          <p className="text-[11px] font-semibold text-[#1B1F3B] truncate">
                            {it.product_title}
                          </p>
                          <p className="text-[10px] text-slate-500">
                            {it.color_family}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {outfitSuggestion.purchase_suggestions.length > 0 && (
                  <div>
                    <span className="text-[10px] font-bold text-[#B8935A] uppercase tracking-wider">
                      Missing pieces — suggested for purchase
                    </span>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-2">
                      {outfitSuggestion.purchase_suggestions.map((it) => (
                        <div
                          key={`buy-${it.position}-${it.product_id}`}
                          className="rounded-2xl border border-slate-200 bg-white p-2"
                        >
                          <div className="h-24 rounded-xl overflow-hidden bg-slate-100 mb-1.5">
                            <img
                              src={it.image_url}
                              alt={it.product_title}
                              className="w-full h-full object-cover"
                            />
                          </div>
                          <span className="text-[9px] font-bold text-slate-400 uppercase">
                            {it.position} · {it.brand_name}
                          </span>
                          <p className="text-[11px] font-semibold text-[#1B1F3B] truncate">
                            {it.product_title}
                          </p>
                          <p className="text-[11px] font-bold text-[#B8935A]">
                            ${it.price}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                  Saved Curated Ensembles
                </h3>
                <p className="text-xs text-slate-500">
                  Your personalized styling collections
                </p>
              </div>
              <button
                onClick={() => navigate("/builder")}
                className="px-4 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold shadow-sm"
              >
                + Build New Look
              </button>
            </div>

            {!isAuthenticated ? (
              <div className="bg-[#FAF9F6] rounded-2xl border border-dashed border-slate-300 p-6 text-center">
                <p className="text-xs text-slate-600 font-medium">
                  Sign in to see your saved looks.
                </p>
                <p className="text-[11px] text-slate-400 mt-1">
                  Ensembles you save in the Builder appear here — synced to your
                  account.
                </p>
              </div>
            ) : savedLooksQuery.isLoading ? (
              <div className="space-y-3" role="status" aria-live="polite">
                <div className="h-20 rounded-2xl bg-slate-100 animate-pulse" />
                <div className="h-20 rounded-2xl bg-slate-100 animate-pulse" />
              </div>
            ) : savedLooks.length === 0 ? (
              <div className="bg-[#FAF9F6] rounded-2xl border border-dashed border-slate-300 p-6 text-center">
                <p className="text-xs text-slate-600 font-medium">
                  No saved looks yet.
                </p>
                <p className="text-[11px] text-slate-400 mt-1">
                  Build an outfit in the Canvas and press “Save Ensemble” — it
                  lands here.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {savedLooks.map((look) => (
                  <div
                    key={look.id}
                    className="bg-[#FAF9F6] rounded-2xl border border-slate-200 p-4 space-y-3"
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <span className="text-[10px] font-bold text-[#B8935A] uppercase">
                          {look.occasion}
                        </span>
                        <h4 className="font-serif text-base font-bold text-[#1B1F3B]">
                          {look.title}
                        </h4>
                      </div>
                      <FitScoreBadge
                        score={look.compatibility_score}
                        label="Match"
                        verdict="stylist engine"
                      />
                    </div>
                    <div className="flex justify-between items-center pt-2 text-xs font-bold text-[#1B1F3B]">
                      <span>Total: ${Number(look.total_price).toFixed(2)}</span>
                      <button
                        onClick={() => handleDeleteLook(look.id)}
                        disabled={deletingLookId === look.id}
                        className="text-rose-500 hover:text-rose-700 disabled:opacity-40"
                        aria-label={`Delete ${look.title}`}
                      >
                        {deletingLookId === look.id ? "Deleting…" : "Delete"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: Wardrobe Gap Analysis (PDF Feature G4.1) */}
      {activeTab === "gaps" && (
        <div className="space-y-6">
          <div className="bg-[#FDF8EE] border border-[#B8935A]/30 rounded-3xl p-6">
            <div className="flex items-center gap-2 mb-2">
              <GapAnalysisIcon size={22} color="#B8935A" />
              <h3 className="font-serif text-xl font-bold text-[#1B1F3B]">
                {t("wardrobe.gap_analysis_title")}
              </h3>
            </div>
            <p className="text-xs text-slate-700 max-w-2xl leading-relaxed">
              {t("wardrobe.gap_analysis_desc")}
            </p>
          </div>

          {!isAuthenticated ? (
            <div className="bg-[#FAF9F6] rounded-2xl border border-dashed border-slate-300 p-6 text-center">
              <p className="text-xs text-slate-600 font-medium">
                {t("wardrobe.gaps_signin")}
              </p>
            </div>
          ) : isGapLoading ? (
            /* Loading: distinct skeleton, never the grid's "empty" look */
            <div className="space-y-4" role="status" aria-live="polite">
              <div className="h-32 rounded-3xl bg-slate-100 animate-pulse" />
              <div className="h-32 rounded-3xl bg-slate-100 animate-pulse" />
            </div>
          ) : isGapError ? (
            <div
              role="alert"
              className="rounded-3xl border border-rose-200 bg-rose-50 p-6 text-center"
            >
              <p className="text-sm font-semibold text-rose-800">
                {t("wardrobe.gaps_failed")}
              </p>
              <p className="text-xs text-rose-600 mt-1">{isGapError}</p>
              <button
                onClick={() => fetchGaps()}
                className="mt-4 px-5 py-2.5 rounded-2xl bg-[#1B1F3B] text-white text-xs font-bold hover:bg-[#2A3C78] transition-all"
              >
                {t("common.try_again")}
              </button>
            </div>
          ) : hasLoadedGaps && gapAnalyses.length === 0 ? (
            /* No gaps: a real state, not a silent blank page */
            <div className="bg-emerald-50 border border-emerald-200 rounded-3xl p-6 text-center">
              <p className="text-sm font-bold text-emerald-800">
                {t("wardrobe.gaps_none_title")}
              </p>
              <p className="text-xs text-emerald-700 mt-1">
                {t("wardrobe.gaps_none_sub")}
              </p>
            </div>
          ) : (
          <div className="space-y-4">
            {gapAnalyses.map((gap) => (
              <div
                key={gap.id}
                className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div>
                    <span className="text-[10px] font-bold text-[#B8935A] uppercase tracking-wider">
                      Identified Closet Gap #{gap.id}
                    </span>
                    <h4 className="font-serif text-lg font-bold text-[#1B1F3B]">
                      Missing: {gap.missing_subcategory} ({gap.missing_category}
                      )
                    </h4>
                  </div>
                  {/* Honest figure: 0 (no core pieces yet) is a real state,
                      shown as "Starter staple" instead of a fake count. */}
                  {gap.unlocks_outfit_count > 0 ? (
                    <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold self-start sm:self-auto">
                      Unlocks +{gap.unlocks_outfit_count} New Outfits
                    </span>
                  ) : (
                    <span className="px-3 py-1 rounded-full bg-slate-100 text-slate-600 text-xs font-bold self-start sm:self-auto">
                      {t("wardrobe.gaps_starter")}
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-600 leading-relaxed bg-[#FAF9F6] p-3 rounded-xl border border-slate-100">
                  💡 <strong>AI Analysis:</strong> {gap.rationale}
                </p>

                {/* Recommended Catalog Bridges */}
                <div>
                  <span className="text-xs font-bold text-slate-700 block mb-2">
                    Recommended Catalog Pieces to Bridge this Gap:
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {gap.recommended_products.map((rec) => (
                      <div
                        key={rec.product_id}
                        className="flex items-center gap-3 p-2.5 rounded-2xl bg-white border border-slate-200 hover:border-[#B8935A] transition-all group"
                      >
                        <div className="w-14 h-16 rounded-xl overflow-hidden bg-slate-100 shrink-0">
                          <img
                            src={rec.image_url}
                            alt={rec.title}
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-[9px] font-bold text-slate-400 block truncate">
                            {rec.brand_name}
                          </span>
                          <span className="text-xs font-bold text-[#1B1F3B] block truncate">
                            {rec.title}
                          </span>
                          <span className="text-xs font-bold text-[#B8935A]">
                            ${rec.price}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
          )}
        </div>
      )}

      {/* TAB 4: Mood Boards — real CRUD + real media upload (G4 surface) */}
      {activeTab === "boards" && (
        <div className="space-y-6">
          {!isAuthenticated ? (
            <div className="bg-[#FAF9F6] rounded-2xl border border-dashed border-slate-300 p-6 text-center">
              <p className="text-xs text-slate-600 font-medium">
                {t("wardrobe.boards_signin_title")}
              </p>
              <p className="text-[11px] text-slate-400 mt-1">
                {t("wardrobe.boards_signin_sub")}
              </p>
            </div>
          ) : isBoardsLoading ? (
            <div className="space-y-3" role="status" aria-live="polite">
              <div className="h-24 rounded-3xl bg-slate-100 animate-pulse" />
              <div className="h-24 rounded-3xl bg-slate-100 animate-pulse" />
            </div>
          ) : isBoardsError ? (
            <div role="alert" className="rounded-3xl border border-rose-200 bg-rose-50 p-6 text-center">
              <p className="text-sm font-semibold text-rose-800">{t("wardrobe.boards_load_failed")}</p>
              <p className="text-xs text-rose-600 mt-1">{isBoardsError}</p>
              <button
                onClick={() => fetchMoodBoards()}
                className="mt-4 px-5 py-2.5 rounded-2xl bg-[#1B1F3B] text-white text-xs font-bold hover:bg-[#2A3C78] transition-all"
              >
                {t("common.try_again")}
              </button>
            </div>
          ) : (
            <>
              {/* New board */}
              <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
                <h3 className="font-serif text-lg font-bold text-[#1B1F3B] mb-3">
                  {t("wardrobe.boards_new_title")}
                </h3>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!newBoardTitle.trim()) return;
                    createMoodBoard(newBoardTitle.trim());
                    setNewBoardTitle("");
                  }}
                  className="flex gap-2"
                >
                  <input
                    value={newBoardTitle}
                    onChange={(e) => setNewBoardTitle(e.target.value)}
                    placeholder={t("wardrobe.boards_new_placeholder")}
                    maxLength={255}
                    className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#B8935A]"
                  />
                  <button
                    type="submit"
                    disabled={!newBoardTitle.trim()}
                    className="px-4 py-2.5 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold disabled:opacity-40 hover:bg-[#2A3C78] transition-all"
                  >
                    + {t("wardrobe.boards_new_create")}
                  </button>
                </form>
              </div>

              {/* Boards list */}
              {hasLoadedBoards && moodBoards.length === 0 ? (
                <div className="bg-[#FAF9F6] rounded-2xl border border-dashed border-slate-300 p-8 text-center">
                  <p className="text-xs text-slate-600 font-medium">{t("wardrobe.boards_empty_title")}</p>
                  <p className="text-[11px] text-slate-400 mt-1">
                    {t("wardrobe.boards_empty_sub")}
                  </p>
                </div>
              ) : (
                <div className="space-y-6">
                  {moodBoards.map((board) => (
                    <div
                      key={board.id}
                      className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4"
                    >
                      <div className="flex items-center justify-between gap-3">
                        {renamingBoardId === board.id ? (
                          <form
                            className="flex gap-2 flex-1"
                            onSubmit={(e) => {
                              e.preventDefault();
                              if (!renameTitle.trim()) return;
                              renameMoodBoard(board.id, renameTitle.trim());
                              setRenamingBoardId(null);
                            }}
                          >
                            <input
                              autoFocus
                              value={renameTitle}
                              onChange={(e) => setRenameTitle(e.target.value)}
                              maxLength={255}
                              className="flex-1 px-3 py-1.5 rounded-lg border border-slate-200 text-xs focus:outline-none focus:border-[#B8935A]"
                            />
                            <button type="submit" className="text-xs font-bold text-[#B8935A]">
                              {t("common.save")}
                            </button>
                            <button
                              type="button"
                              onClick={() => setRenamingBoardId(null)}
                              className="text-xs font-bold text-slate-400"
                            >
                              {t("common.cancel")}
                            </button>
                          </form>
                        ) : (
                          <div className="min-w-0">
                            <h4 className="font-serif text-base font-bold text-[#1B1F3B] truncate">
                              {board.title}
                            </h4>
                            {board.description && (
                              <p className="text-xs text-slate-500 truncate">{board.description}</p>
                            )}
                          </div>
                        )}
                        <div className="flex items-center gap-3 shrink-0 text-xs font-bold">
                          <button
                            onClick={() => {
                              setRenamingBoardId(board.id);
                              setRenameTitle(board.title);
                            }}
                            className="text-slate-400 hover:text-[#B8935A]"
                          >
                            {t("common.rename")}
                          </button>
                          <button
                            onClick={() => deleteMoodBoard(board.id)}
                            className="text-rose-400 hover:text-rose-600"
                          >
                            {t("common.delete")}
                          </button>
                        </div>
                      </div>

                      {/* Tiles */}
                      {board.items.length > 0 && (
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                          {board.items.map((tile) => (
                            <div
                              key={tile.id}
                              className="relative rounded-2xl border border-slate-200 bg-slate-50 overflow-hidden group"
                            >
                              {tile.kind === "upload" && tile.payload.url ? (
                                <img
                                  src={tile.payload.url}
                                  alt={`Mood board tile ${tile.id}`}
                                  className="h-28 w-full object-cover"
                                />
                              ) : tile.kind === "url" && tile.payload.url ? (
                                <a href={tile.payload.url} target="_blank" rel="noreferrer">
                                  <img
                                    src={tile.payload.url}
                                    alt={`Mood board link ${tile.id}`}
                                    className="h-28 w-full object-cover"
                                  />
                                </a>
                              ) : (
                                <div className="h-28 w-full flex flex-col items-center justify-center text-center px-2">
                                  <BagIcon size={20} color="#B8935A" />
                                  <span className="text-[10px] font-bold text-slate-500 mt-1">
                                    {t("wardrobe.boards_product_tile", { id: tile.payload.product_id })}
                                  </span>
                                </div>
                              )}
                              <button
                                onClick={() => removeMoodBoardTile(board.id, tile.id)}
                                title={t("wardrobe.boards_remove_tile")}
                                className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/60 text-white text-[10px] opacity-0 group-hover:opacity-100 hover:bg-rose-600 transition-all"
                              >
                                ✕
                              </button>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Add tile: URL or real upload */}
                      <div className="flex flex-col sm:flex-row gap-2 pt-2 border-t border-slate-100">
                        <form
                          className="flex gap-2 flex-1"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const url = newTileUrl.trim();
                            if (!url || !/^https?:\/\//i.test(url)) return;
                            setBusyBoardId(board.id);
                            addMoodBoardTile(board.id, "url", { url }).finally(() => {
                              setBusyBoardId(null);
                              setNewTileUrl("");
                            });
                          }}
                        >
                          <input
                            value={newTileUrl}
                            onChange={(e) => setNewTileUrl(e.target.value)}
                            placeholder={t("wardrobe.boards_link_placeholder")}
                            className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#B8935A]"
                          />
                          <button
                            type="submit"
                            disabled={busyBoardId === board.id}
                            className="px-3 py-2 rounded-xl bg-slate-100 text-[#1B1F3B] text-xs font-semibold disabled:opacity-40"
                          >
                            {t("wardrobe.boards_add_link")}
                          </button>
                        </form>
                        <label className="px-3 py-2 rounded-xl bg-slate-100 text-[#1B1F3B] text-xs font-semibold cursor-pointer hover:bg-slate-200 transition-all">
                          {t("wardrobe.boards_upload_photo")}
                          <input
                            type="file"
                            accept="image/jpeg,image/png,image/webp,image/gif"
                            className="hidden"
                            onChange={async (e) => {
                              const file = e.target.files?.[0];
                              e.target.value = "";
                              if (!file) return;
                              if (file.size > 5 * 1024 * 1024) {
                                // 5MB is the mood-board upload contract (backend)
                                showToast(msg("toast.board_upload_too_large"), "error");
                                return;
                              }
                              setBusyBoardId(board.id);
                              await uploadMoodBoardTile(board.id, file);
                              setBusyBoardId(null);
                            }}
                          />
                        </label>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Upload Piece Modal — real photo upload (single + bulk) with honest AI status */}
      {uploadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-150">
          <div
            ref={uploadPanelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Upload garment"
            tabIndex={-1}
            className="w-full max-w-lg bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden max-h-[90vh] overflow-y-auto"
          >
            <div className="p-5 bg-[#1B1F3B] text-white flex justify-between items-center">
              <h3 className="font-serif text-base font-bold text-white flex items-center gap-2">
                <span>Upload Garment Photos</span>
              </h3>
              <button
                onClick={() => {
                  setUploadModalOpen(false);
                  setSelectedFiles([]);
                }}
                className="text-slate-300 hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Mode 1: real photo upload (single or bulk import) */}
            <form
              onSubmit={handleUploadSubmit}
              className="p-6 space-y-4 border-b border-slate-100"
            >
              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1">
                  Garment Photos{" "}
                  <span className="text-slate-400 font-normal">
                    (JPEG/PNG/WebP, up to 15MB each, max 20)
                  </span>
                </label>
                {photoUploadUnavailable && (
                  <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-xl p-3 mb-2 leading-relaxed">
                    Heads up: photo uploads are not configured in this
                    environment (no persistent object storage yet) — the server
                    will reject them with a clear error. Use manual add below,
                    which works fully.
                  </p>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  onChange={handleFileChange}
                  className="w-full text-xs text-slate-600 file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:bg-[#1B1F3B] file:text-white file:text-xs file:font-semibold hover:file:bg-[#2A3C78] file:cursor-pointer"
                />
                {selectedFiles.length > 0 && (
                  <p className="text-[11px] text-slate-500 mt-1.5">
                    {selectedFiles.length} file(s) selected:{" "}
                    {selectedFiles
                      .map((f) => f.name)
                      .slice(0, 3)
                      .join(", ")}
                    {selectedFiles.length > 3
                      ? ` +${selectedFiles.length - 3} more`
                      : ""}
                  </p>
                )}

                {uploadSkipNotes.length > 0 && (
                  <ul
                    className="text-[11px] text-rose-600 mt-1.5 space-y-1"
                    role="alert"
                  >
                    {uploadSkipNotes.map((n) => (
                      <li key={n}>• {n}</li>
                    ))}
                  </ul>
                )}
              </div>

              <button
                type="submit"
                disabled={!selectedFiles.length || isUploading || isCompressing}
                className="w-full py-3 rounded-xl bg-[#B8935A] hover:bg-[#a07f4c] text-white font-semibold text-xs transition-all shadow-md flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                <SparkleIcon size={14} color="#fff" />
                <span>
                  {isCompressing
                    ? "Optimizing photos…"
                    : isUploading
                      ? "Uploading & Analyzing…"
                      : `Upload ${selectedFiles.length > 1 ? `${selectedFiles.length} Pieces` : "Piece"} & Auto-Tag with AI`}
                </span>
              </button>

              {/* Per-file batch report: partial success is surfaced, not hidden */}
              {uploadReport && (
                <div className="space-y-1.5">
                  {uploadReport.results.map((r, idx) => (
                    <div
                      key={idx}
                      className={`flex items-center justify-between text-[11px] px-3 py-2 rounded-xl border ${
                        r.status === "failed"
                          ? "bg-rose-50 border-rose-200 text-rose-800"
                          : r.status === "duplicate"
                            ? "bg-amber-50 border-amber-200 text-amber-800"
                            : r.item?.processing_status === "failed"
                              ? "bg-amber-50 border-amber-200 text-amber-800"
                              : "bg-emerald-50 border-emerald-200 text-emerald-800"
                      }`}
                    >
                      <span className="truncate font-medium">{r.filename}</span>
                      <span className="font-bold ml-2 shrink-0">
                        {r.status === "failed"
                          ? "Failed"
                          : r.status === "duplicate"
                            ? "Duplicate — already owned"
                            : r.item?.processing_status === "ready"
                              ? "Analyzed ✓"
                              : r.item?.processing_status === "failed"
                                ? "Saved (AI retryable)"
                                : "Processing…"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </form>

            {/* Mode 2: manual entry fallback (metadata-complete -> ready immediately) */}
            <form onSubmit={handleAddSubmit} className="p-6 space-y-4">
              <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                Or add manually (no photo)
              </p>
              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1">
                  Garment Title
                </label>
                <input
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Navy Double-Breasted Blazer"
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#B8935A]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-bold text-slate-800 block mb-1">
                    Category
                  </label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-xs bg-white"
                  >
                    <option value="Outerwear">Outerwear</option>
                    <option value="Tops">Tops & Shirts</option>
                    <option value="Bottoms">Bottoms & Trousers</option>
                    <option value="Footwear">Footwear</option>
                    <option value="Accessories">Accessories</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-bold text-slate-800 block mb-1">
                    Color Family
                  </label>
                  <input
                    type="text"
                    value={newColor}
                    onChange={(e) => setNewColor(e.target.value)}
                    placeholder="e.g. Navy Blue"
                    className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-xs"
                  />
                </div>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white font-semibold text-xs transition-all shadow-md"
                >
                  Save Piece Manually
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
