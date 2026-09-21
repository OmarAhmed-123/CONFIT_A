import React, { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useTryOnViewModel } from "../../viewmodels/useTryOnViewModel";

/**
 * Honest engine-status banner for Virtual Try-On.
 *
 * Why this component exists (audit closure 2026-09-21):
 * production advertised try-on as available while the GPU workspace was
 * disabled by its spend limit, so users uploaded a photo, waited ~39 s, and got
 * a developer-grade error. The backend now publishes a LIVE verdict
 * (`engine.verdict`) plus a real SLA; this component is the surface that turns
 * those two fields into something a shopper can act on BEFORE spending time on
 * an upload:
 *
 *   ready        -> green, with the published warm-render expectation
 *   cold_start   -> amber, "warming up, first result can take a minute"
 *   unavailable  -> red, the backend's own sentence + retry-after when the
 *                   fail-fast circuit is open
 *   unknown      -> nothing rendered (we do not guess, and we do not shout)
 *
 * It never renders marketing copy that contradicts the measured state.
 */
export const TryOnEngineStatus: React.FC<{
  /** Product ids to resolve capabilities for; omit for the engine-only view. */
  productIds?: number[];
  className?: string;
}> = ({ productIds = [], className = "" }) => {
  const { t } = useTranslation();
  const { engineHealth, engineSla, checkTryOnCapabilities } =
    useTryOnViewModel();

  useEffect(() => {
    // The engine verdict does not depend on the product list; resolving with an
    // empty list still returns engine + sla, which is all this banner needs.
    void checkTryOnCapabilities(productIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(productIds)]);

  if (!engineHealth || engineHealth.verdict === "unknown") return null;

  const verdict = engineHealth.verdict;
  const retryAfter = Math.ceil(engineHealth.retry_after_seconds ?? 0);

  if (verdict === "ready") {
    return (
      <div
        role="status"
        className={`flex items-start gap-3 rounded-2xl border border-emerald-500/40 bg-emerald-950/70 px-4 py-3 text-sm text-emerald-50 backdrop-blur ${className}`}
      >
        <span aria-hidden="true" className="mt-0.5 text-emerald-400">
          ●
        </span>
        <div>
          <p className="font-semibold">{t("tryon.engine_online_title")}</p>
          {engineSla ? (
            <p className="text-emerald-200/80">
              {t("tryon.engine_online_detail", {
                seconds: Math.round(engineSla.warm_render_seconds_p50),
                garments: engineSla.max_garments_per_job
                  ? t("tryon.engine_online_garments", {
                      count: engineSla.max_garments_per_job,
                    })
                  : "",
              })}
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  if (verdict === "cold_start") {
    return (
      <div
        role="status"
        className={`flex items-start gap-3 rounded-2xl border border-amber-500/40 bg-amber-950/70 px-4 py-3 text-sm text-amber-50 backdrop-blur ${className}`}
      >
        <span aria-hidden="true" className="mt-0.5 text-amber-400">
          ▲
        </span>
        <div>
          <p className="font-semibold">{t("tryon.engine_warming_title")}</p>
          <p className="text-amber-200/80">
            {t("tryon.engine_warming_detail", {
              seconds: Math.round(engineSla?.cold_start_seconds_budget ?? 120),
            })}
          </p>
        </div>
      </div>
    );
  }

  // unavailable / not_configured
  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-2xl border border-rose-500/40 bg-rose-950/70 px-4 py-3 text-sm text-rose-50 backdrop-blur ${className}`}
    >
      <span aria-hidden="true" className="mt-0.5 text-rose-400">
        ■
      </span>
      <div>
        <p className="font-semibold">{t("tryon.engine_offline_title")}</p>
        <p className="text-rose-200/85">
          {engineHealth.detail || t("tryon.engine_offline_fallback")}
        </p>
        {retryAfter > 0 ? (
          <p className="mt-1 text-rose-200/70">
            {t("tryon.engine_offline_retry", { seconds: retryAfter })}
          </p>
        ) : null}
      </div>
    </div>
  );
};

export default TryOnEngineStatus;
