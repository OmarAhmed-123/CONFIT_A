/**
 * Regression guard for the 2026-10-17 EN -> AR extraction.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `npm run i18n:check` proves only that a key EXISTS in both locales and is
 * not byte-identical to English. It is a structural gate. It cannot see that
 * `Unlocks` was rendered as `أزِل` ("Remove!"), that `funnel` became
 * `القالب` ("the template"), that `failed orders` became `المفلسة`
 * ("bankrupt"), or that "are not established by this screen" was inverted
 * into an assertion that the counters are not reset.
 *
 * Every one of those passed the structural gate.
 *
 * So this file pins the MEANING of the strings that were demonstrably wrong,
 * plus the invariants that make the whole batch trustworthy:
 *
 *   1. the specific corrected leaves (a silent revert fails here);
 *   2. disclaimers must stay hedged — a translation that turns "not
 *      established" / "does not prove" / "is not a probability" into a flat
 *      factual claim is worse than an untranslated string;
 *   3. the same English concept must not ship under two different Arabic
 *      terms on the same screen;
 *   4. placeholders must survive, and must not be invented.
 *
 * These are not style preferences. Items 1-3 are the defect classes that were
 * actually measured on this codebase (see docs/i18n/riva-translate-pipeline.md).
 */
import { describe, expect, it } from 'vitest';
import en from '../en.json';
import ar from '../ar.json';
import baseline from './fixtures/review-baseline.json';

type Tree = { [k: string]: string | Tree };

function flatten(obj: Tree, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'string') out[key] = v;
    else Object.assign(out, flatten(v, key));
  }
  return out;
}

const flatEn = flatten(en as Tree);
const flatAr = flatten(ar as Tree);

/** Keys added by the 2026-10-17 extraction; the set this file is accountable for. */
const EXTRACTED = [
  // consumer
  'wardrobe.retention_engine_eyebrow', 'wardrobe.retention_engine_headline',
  'wardrobe.retention_engine_body', 'wardrobe.boards_title', 'wardrobe.boards_subtitle',
  'wardrobe.boards_signin_body', 'wardrobe.boards_signin_note', 'wardrobe.boards_empty_body',
  'wardrobe.boards_empty_note', 'wardrobe.gap_card_eyebrow', 'wardrobe.gap_missing',
  'wardrobe.gap_compat_score', 'wardrobe.gap_from_closet', 'wardrobe.gap_unlocks_outfits',
  'wardrobe.gap_ai_analysis', 'wardrobe.gap_recommended', 'wardrobe.form_photos_label',
  'wardrobe.form_photos_hint', 'wardrobe.form_manual_heading', 'wardrobe.form_title_label',
  'wardrobe.form_category_label', 'wardrobe.form_color_family_label',
  'wardrobe.form_save_manual', 'wardrobe.form_photo_unavailable',
  'wardrobe.upload_status_failed', 'wardrobe.upload_status_duplicate',
  'wardrobe.upload_status_analyzed', 'wardrobe.upload_status_saved_retryable',
  'wardrobe.upload_status_processing', 'wardrobe.dup_alert_title',
  'wardrobe.dup_alert_message', 'wardrobe.dup_already_in_closet',
  'wardrobe.dup_stylist_recommendation', 'wardrobe.dup_stylist_message',
  'wardrobe.dup_proceed_anyway', 'wardrobe.dup_worn_times_one', 'wardrobe.dup_worn_times_other',
  // added by the earlier i18n commit and reviewed in this pass
  'wardrobe.upload_piece', 'wardrobe.closet_signin_title', 'wardrobe.closet_signin_body',
  'tryon.multi_layer_title', 'tryon.multi_layer_desc', 'tryon.person_reference',
  'tryon.dressing_canvas', 'tryon.before_after_split', 'tryon.split_original',
  'tryon.step_label', 'tryon.synthesizing_layer', 'tryon.dressed_layers',
  'tryon.clear_all', 'tryon.total_dressed_look', 'tryon.catalog_shelf_title',
  'tryon.catalog_shelf_hint', 'tryon.in_outfit', 'tryon.privacy_note_label',
  'tryon.privacy_note_body', 'tryon.btn_remove', 'tryon.btn_checking_support',
  'tryon.btn_dress_on_body', 'tryon.btn_not_in_vton', 'tryon.capability_title_fallback',
  'tryon.dressed_with_layers', 'tryon.dressed_with_layers_plural',
  'tryon.dress_to_style_hint', 'tryon.btn_synthesizing', 'tryon.btn_play_sequence',
  'tryon.add_items_to_bag_one', 'tryon.add_items_to_bag_other', 'tryon.processing_photo',
  'tryon.upload_your_photo', 'tryon.avatar_athletic_m', 'tryon.avatar_hourglass_f',
  'tryon.avatar_curvy_f', 'tryon.avatar_tall_structured', 'tryon.fit_badge_label',
  'tryon.fit_badge_pending', 'tryon.fit_badge_heuristic', 'tryon.base_silhouette',
  'tryon.rendering_layers', 'tryon.rendering_layers_plural',
  'fit_finder.camera_estimate_note', 'fit_finder.label_height_colon',
  'fit_finder.label_weight_colon', 'fit_finder.body_silhouette',
  'fit_finder.preferred_fit_colon', 'fit_finder.add_colon', 'fit_finder.size_col',
  'fit_finder.size_value', 'fit_finder.return_risk_colon', 'fit_finder.zone_fit_breakdown',
  'fit_finder.rule_based_rating', 'fit_finder.chart_colon', 'fit_finder.add_size',
  'fit_finder.cross_reference_note', 'fit_finder.confidence_band', 'fit_finder.unrated',
  'fit_finder.partly_estimated_suffix',
  // b2b
  'b2b.inv_heading', 'b2b.inv_heading_note', 'b2b.inv_bopis_title', 'b2b.inv_store_id',
  'b2b.inv_store_ids_placeholder', 'b2b.inv_on_hand_note', 'b2b.inv_orphan_stores',
  'b2b.inv_empty', 'b2b.inv_total_stock', 'b2b.inv_total_stock_value', 'b2b.inv_sku',
  'b2b.inv_size_color', 'b2b.inv_latitude', 'b2b.inv_phone',
  'b2b.analytics_funnel_heading', 'b2b.analytics_ratios_note', 'b2b.analytics_empty',
  'b2b.analytics_col_product', 'b2b.analytics_col_views', 'b2b.analytics_col_tryons',
  'b2b.analytics_col_conv', 'b2b.analytics_return_comparison',
  'b2b.analytics_return_reduction', 'b2b.analytics_bopis_fulfillment',
  'b2b.analytics_bopis_line', 'b2b.placements_heading', 'b2b.placements_heading_note',
  'b2b.placements_impressions', 'b2b.placements_impressions_src',
  'b2b.placements_clicks_total', 'b2b.placements_clicks_src', 'b2b.placements_spent_total',
  'b2b.placements_spent', 'b2b.placements_revenue', 'b2b.placements_roas',
  'b2b.placements_active', 'b2b.placements_real_from_db', 'b2b.placements_empty',
  'b2b.placements_product_id', 'b2b.placements_created_at', 'b2b.placements_cpc_bid',
  'b2b.placements_clicks', 'b2b.placements_conversions', 'b2b.placements_daily_budget',
  'b2b.placements_counters_note', 'b2b.placements_form_heading',
  'b2b.placements_select_product',
  // b2b analytics_view (BrandAnalyticsView professional redesign)
  'b2b.analytics_view.unavailable_title', 'b2b.analytics_view.eyebrow',
  'b2b.analytics_view.heading', 'b2b.analytics_view.no_activity',
  'b2b.analytics_view.funnel_title', 'b2b.analytics_view.top_skus',
  'b2b.analytics_view.no_skus', 'b2b.analytics_view.cohort_title',
  'b2b.analytics_view.cohort_subtitle',
  // PR #351/#352 CSV product-import surface (preview steps, table headers,
  // result summary, branch targeting): reviewed with en/ar parity checks.
  'b2b.cat.import_products_cta',
  'b2b.cat.import_benefit_copy',
  'b2b.cat.target_branch_label',
  'b2b.cat.target_branch_all',
  'b2b.cat.step_upload',
  'b2b.cat.step_preview',
  'b2b.cat.step_result',
  'b2b.cat.preview_valid_count',
  'b2b.cat.preview_error_count',
  'b2b.cat.preview_warning_count',
  'b2b.cat.preview_dup_count',
  'b2b.cat.preview_title',
  'b2b.cat.preview_desc',
  'b2b.cat.th_action',
  'b2b.cat.th_product',
  'b2b.cat.th_sku',
  'b2b.cat.th_category',
  'b2b.cat.th_price',
  'b2b.cat.th_stock',
  'b2b.cat.th_variant',
  'b2b.cat.th_branch',
  'b2b.cat.action_create',
  'b2b.cat.action_update',
  'b2b.cat.notif_toggle_label',
  'b2b.cat.btn_confirm_import',
  'b2b.cat.btn_back_upload',
  'b2b.cat.btn_download_error_report',
  'b2b.cat.result_title',
  'b2b.cat.result_created',
  'b2b.cat.result_updated',
  'b2b.cat.result_failed',
  'b2b.cat.result_notifications',
  'b2b.cat.btn_view_catalog',
  'b2b.cat.search_placeholder',
  'b2b.cat.filter_all_categories',
  // CSV-import honesty surface: the processing label, the warnings/blockers
  // panels, the accessible table caption, the two download failures, and the
  // result facts the API returns (media registered, missing Arabic, inferred
  // gender). Reviewed: Arabic is a real translation (no English left), the
  // digits are Arabic-Indic where the locale uses them, and each message says
  // what actually happened rather than a generic "error".
  'b2b.cat.step_processing',
  'b2b.cat.warnings_title',
  'b2b.cat.warnings_more',
  'b2b.cat.blocked_title',
  'b2b.cat.row_label',
  'b2b.cat.file_label',
  'b2b.cat.preview_table_caption',
  'b2b.cat.err_template_download',
  'b2b.cat.err_report_download',
  'b2b.cat.result_job',
  'b2b.cat.result_media',
  'b2b.cat.result_missing_ar',
  'b2b.cat.result_gender_inferred',
  'b2b.cat.result_missing_ar_hint',
  'b2b.cat.result_rejected_title',
  // Gallery honesty: the import can complete with fewer photographs than the
  // CSV asked for, and the result screen states how many were not imported.
  'b2b.cat.result_photos_not_imported',
  // Background-import lifecycle. The import is accepted before it runs, so the
  // result screen can be showing a queued, running or dead job. Reviewed: the
  // Arabic distinguishes قيد التنفيذ (running) from اكتمل (done) and from لم
  // يكتمل (did not finish) — the three states the old single headline collapsed
  // into one — and the progress copy promises only what the server does (the
  // job keeps running after the tab closes), never a completion the client
  // cannot know.
  'b2b.cat.result_title_running',
  'b2b.cat.result_title_failed',
  'b2b.cat.status_queued',
  'b2b.cat.progress_processed',
  'b2b.cat.progress_safe_to_close',
  'b2b.cat.progress_stopped_watching',
  'b2b.cat.failed_reason',
  'b2b.cat.failed_no_reason',
  'b2b.cat.btn_retry_import',
  'b2b.cat.err_not_accepted',
  'b2b.cat.err_retry_refused',
  'b2b.cat.domains_cta',
  'b2b.cat.domains_title',
  'b2b.cat.domains_subtitle',
  'b2b.cat.domain_input_label',
  'b2b.cat.domain_placeholder',
  'b2b.cat.domain_claim_btn',
  'b2b.cat.domain_verify_btn',
  'b2b.cat.domain_revoke_btn',
  'b2b.cat.domain_release_btn',
  'b2b.cat.domains_empty',
  'b2b.cat.domain_status_expired',
  'b2b.cat.domain_expires_label',
  'b2b.cat.domain_claimed_msg',
  'b2b.cat.domain_verified_msg',
  'b2b.cat.domain_pending_msg',
  'b2b.cat.domain_revoked_msg',
  'b2b.cat.domain_released_msg',
  'b2b.cat.domain_err_generic',
  'b2b.cat.curation_readonly',
  'b2b.cat.edit_details_cta',
  'b2b.cat.field_title',
  'b2b.cat.field_gender',
  'b2b.cat.field_material',
  'b2b.cat.field_care',
  'b2b.cat.field_style_tags',
  'b2b.cat.field_occasion_tags',
  'b2b.cat.field_description',
  'b2b.cat.chart_section_title',
  'b2b.cat.chart_unit',
  'b2b.cat.chart_basis',
  'b2b.cat.chart_fit',
  'b2b.cat.chart_source',
  'b2b.cat.chart_rows_label',
  'b2b.cat.chart_notes_label',
  'b2b.cat.chart_notes_placeholder',
  'b2b.cat.details_saved_msg',
  'b2b.cat.details_err_msg',
  'b2b.cat.style_placeholder',
  'b2b.cat.occasion_placeholder',
  'b2b.cat.chart_source_placeholder',
  'b2b.cat.chart_rows_placeholder',
  'tryon.scan_feature_desc',
  'tryon.ruler_feature_desc',
  'tryon.ruler_feature_cta',
  'tryon.visual_feature_desc',
  'tryon.visual_feature_cta',
  'b2b.store_modal_subtitle',
  'b2b.label_store_name',
  'b2b.label_store_city',
  'b2b.label_store_country',
  'b2b.label_store_address',
  'b2b.placeholder_store_name',
  'b2b.placeholder_store_city',
  'b2b.placeholder_store_country',
  'b2b.placeholder_store_address',
  'b2b.media_engagement_title',
  'b2b.media_engagement_subtitle',
  'b2b.media_gallery_views',
  'b2b.media_fit_recommendations',
  'b2b.media_wishlist_saves',
  'b2b.media_photo_slot',
  'fit_finder.applied_size_banner',
  'fit_finder.applied_size_oos_banner',
  'fit_finder.select_placeholder',
  'fit_finder.brand_chart_note',
  'fit_finder.error_rejected_fields',
  'fit_finder.error_generic',
];

describe('extracted strings: presence and shape', () => {
  it('every key added after the audit base is in the reviewed set', () => {
    /**
     * review-baseline.json is the key list of these four namespaces at the
     * audit base (c52bb50). Anything present now and absent there was added
     * by this branch and must therefore appear in EXTRACTED - i.e. it must
     * have been through the review.
     *
     * If this fails, a key reached the locales without being reviewed. Add it
     * to EXTRACTED *after* reviewing it. Do not delete this check: "it is in
     * both locales and is not English" is exactly the bar the mistranslations
     * passed.
     */
    const baselineSet = new Set<string>(baseline);
    const reviewed = new Set(EXTRACTED);
    const unreviewed = Object.keys(flatEn)
      .filter((k) => ['wardrobe', 'tryon', 'fit_finder', 'b2b'].includes(k.split('.')[0]))
      .filter((k) => !baselineSet.has(k) && !reviewed.has(k));
    expect(unreviewed).toEqual([]);
  });

  it('the reviewed set covers every key the branch added, and does not shrink', () => {
    const baselineSet = new Set<string>(baseline);
    const reviewed = new Set(EXTRACTED);
    const added = Object.keys(flatEn)
      .filter((k) => ['wardrobe', 'tryon', 'fit_finder', 'b2b'].includes(k.split('.')[0]))
      .filter((k) => !baselineSet.has(k));
    expect(added.filter((k) => !reviewed.has(k))).toEqual([]);
    // Reused pre-existing keys may also appear (tryon.upload_your_photo was
    // already translated and is now referenced from a second call site), but
    // every reviewed key must at least exist.
    expect(EXTRACTED.filter((k) => !(k in flatEn))).toEqual([]);
    expect(added.length).toBeGreaterThan(130);
  });

  it.each(EXTRACTED)('%s exists in both locales and is non-empty', (key) => {
    expect(flatEn[key], `en:${key}`).toBeTruthy();
    expect(flatAr[key], `ar:${key}`).toBeTruthy();
  });

  it.each(EXTRACTED)('%s keeps every English placeholder and invents none', (key) => {
    const ph = (s: string) => [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort();
    expect(ph(flatAr[key]), `ar:${key}`).toEqual(ph(flatEn[key]));
  });
});

describe('1. the strings that were measurably wrong stay correct', () => {
  /**
   * Each entry is (key, what the Arabic MUST say, what it must NEVER say).
   * The "never" side is the recorded mistranslation.
   */
  const pinned: Array<[string, string[], string[]]> = [
    // riva rendered "Unlocks" as أزِل = "Remove", inverting a benefit into a
    // destructive action.
    ['wardrobe.gap_unlocks_outfits', ['يُتيح'], ['أزِل', 'إزالة', 'إلغاء قفل']],
    // "Conversion Funnel" → القالب ("the template") instead of قمع التحويل.
    ['b2b.analytics_funnel_heading', ['قمع التحويل'], ['القالب']],
    ['b2b.analytics_empty', ['قمع تحويل'], ['القالب']],
    // "Trending Placements" → التقنيات المتطورة ("cutting-edge technology").
    ['b2b.placements_heading', ['المواضع الإعلانية'], ['التقنيات المتطورة']],
    // "failed orders" → المفلسة ("bankrupt").
    ['b2b.analytics_ratios_note', ['الفاشلة'], ['المفلسة', 'الملقاة']],
    // "styling what you own" → تزيين ("decorating") instead of تنسيق.
    ['wardrobe.dup_stylist_message', ['تنسيق'], ['تزيين']],
    // garment "Size" → الحجم ("volume/bulk") instead of المقاس.
    ['fit_finder.size_col', ['المقاس'], ['الحجم']],
    ['fit_finder.size_value', ['المقاس'], ['الحجم']],
    ['fit_finder.add_size', ['مقاس'], ['الحجم']],
    // "Dressing Canvas" → خزانة قماش ("fabric cupboard").
    ['tryon.dressing_canvas', ['لوحة'], ['خزانة قماش']],
    // "return-marked line" → العلامات المرسومة ("drawn marks").
    ['b2b.analytics_return_comparison', ['مرتجع'], ['المرسومة']],
    // "Worn" as a bare label shipped next to a hard-coded English "times".
    ['wardrobe.dup_worn_times_other', ['مرات'], []],
  ];

  it.each(pinned)('%s carries the reviewed meaning', (key, must, mustNot) => {
    const value = flatAr[key];
    for (const m of must) expect(value, `ar:${key} should contain "${m}"`).toContain(m);
    for (const m of mustNot) expect(value, `ar:${key} must NOT contain "${m}"`).not.toContain(m);
  });

  it('the import lifecycle keeps "running", "done" and "did not finish" apart in Arabic', () => {
    // One headline for all three states was the UI half of the same lie the
    // 202-with-a-stale-body told: a green tick over work that had not started.
    expect(flatAr['b2b.cat.result_title_running']).toContain('قيد التنفيذ');
    expect(flatAr['b2b.cat.result_title_failed']).toContain('لم يكتمل');
    expect(flatAr['b2b.cat.status_queued']).toBeTruthy();
    expect(flatAr['b2b.cat.status_queued']).not.toBe(flatAr['b2b.cat.status_processing']);
  });

  it('progress copy promises only what the server actually does', () => {
    // Truthful claim: the job lives in the database and a worker owns it, so
    // closing the tab does not cancel it. A "do not close this window" warning
    // would be the opposite lie — and hiding the stopped-poller state would
    // leave a spinner implying we are still watching.
    expect(flatEn['b2b.cat.progress_safe_to_close']).toMatch(/close this window/i);
    expect(flatEn['b2b.cat.progress_stopped_watching']).toMatch(/may still be running/i);
    expect(flatAr['b2b.cat.progress_safe_to_close']).toContain('إغلاق');
  });

  it('the dead duplicate key tryon.person_ref_value stays removed', () => {
    // It was added twice (person_reference already existed) and was never
    // referenced. Keeping an unreferenced duplicate invites editing the wrong one.
    expect(flatEn['tryon.person_ref_value']).toBeUndefined();
    expect(flatAr['tryon.person_ref_value']).toBeUndefined();
  });
});

describe('2. disclaimers stay hedged', () => {
  /**
   * The most damaging measured error was not a wrong word but an inverted
   * epistemic claim: "are NOT established by this screen" was rendered as an
   * assertion that the counters are not reset. In a B2B surface whose whole
   * purpose is stating what is and is not proven, that is a misstatement.
   *
   * These keys must keep a negation. A translation that drops it fails here.
   */
  const hedged: Array<[string, RegExp]> = [
    ['b2b.placements_counters_note', /لا تُثبت|ليست|غير/],
    ['b2b.placements_heading_note', /لا يُثبت|لا تُثبت/],
    ['b2b.inv_on_hand_note', /لا ينقل/],
    ['b2b.analytics_bopis_line', /وليست|غير/],
    ['fit_finder.rule_based_rating', /وليس|لا /],
    ['tryon.fit_badge_heuristic', /وليس/],
    ['b2b.inv_orphan_stores', /يجب عدم|لا يجب/],
  ];

  it.each(hedged)('%s still carries its negation', (key, negation) => {
    expect(flatAr[key], `ar:${key}`).toMatch(negation);
  });

  it('placements_counters_note does not assert the counters ARE reset or ARE deduplicated',
    () => {
      const v = flatAr['b2b.placements_counters_note'];
      // The dangerous shape: a flat declarative about the counters' behaviour.
      expect(v).not.toMatch(/العدادات (تُصفَّر|تُعاد|يتم إعادة تعيينها)/);
      expect(v).not.toMatch(/يتم (إزالة|استبعاد) تكرار الأحداث/);
    });
});

describe('3. one English concept, one Arabic term', () => {
  it('"Try-Ons" uses the project term, not a second invented one', () => {
    // b2b.total_tryons (pre-existing) is the reference term.
    expect(flatAr['b2b.total_tryons']).toContain('القياس الافتراضي');
    expect(flatAr['b2b.analytics_col_tryons']).toContain('القياس الافتراضي');
    expect(flatAr['b2b.analytics_col_tryons']).not.toContain('التجارب الافتراضية');
    expect(flatAr['b2b.analytics_empty']).not.toContain('التجارب الافتراضية');
  });

  it('"Return reduction" agrees with its sibling key on the same screen', () => {
    expect(flatAr['b2b.analytics_return_reduction']).toBe(flatAr['b2b.return_reduction']);
  });

  it('the same English sentence is not translated two different ways', () => {
    // "Sign in to see your saved looks." appears in two places.
    expect(flatEn['wardrobe.boards_signin_body']).toBe(flatEn['my_looks.signin_title']);
    expect(flatAr['wardrobe.boards_signin_body']).toBe(flatAr['my_looks.signin_title']);
  });

  it('"Builder" is the Outfit Builder everywhere, not the stylist', () => {
    const builder = flatAr['nav.outfit_builder'];
    expect(builder).toContain('مصمم الإطلالات');
    expect(flatAr['wardrobe.boards_signin_note']).toContain(builder);
    expect(flatAr['my_looks.signin_body']).toContain(builder);
  });

  it('stylist terminology matches nav.stylist', () => {
    expect(flatAr['nav.stylist']).toContain('منسق المظهر');
    expect(flatAr['wardrobe.dup_stylist_recommendation']).toContain('منسق المظهر');
    expect(flatAr['b2b.placements_empty']).toContain('منسق المظهر');
  });
});
