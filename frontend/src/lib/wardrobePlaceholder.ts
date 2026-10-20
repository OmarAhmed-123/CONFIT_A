/**
 * The stand-in artwork for a wardrobe item that has no photograph.
 *
 * A manually-added item ("I own a black wool coat") has no image to upload, so
 * the grid needs a neutral frame. This is NOT a product photo and must never
 * look like one: it is a blank card, drawn locally, with no text baked in
 * (text inside an image is invisible to translation and cannot be resized —
 * WCAG 1.4.5). The accessible name lives on the <img alt>, a translated string.
 *
 * ENCODING RULE
 * -------------
 * The colour literals are written as plain `#RRGGBB` and `encodeURIComponent`
 * is the single encoding step: it turns `#` into `%23` exactly once.
 *
 * The pre-escaped form (`fill="%23F8FAFC"` fed through `encodeURIComponent`)
 * escapes the `%` a second time, so the browser receives `fill="%23F8FAFC"` —
 * an invalid CSS colour. Invalid fills are dropped silently and SVG's initial
 * fill, solid black, paints instead: every manual wardrobe item rendered as a
 * black tile in production. The regression test in
 * `lib/__tests__/wardrobePlaceholder.test.ts` decodes this value the way a
 * browser does and asserts the colours survive.
 */
export const MANUAL_WARDROBE_IMAGE =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 750"><rect width="600" height="750" fill="#F8FAFC"/><rect x="90" y="120" width="420" height="510" rx="42" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="4"/></svg>',
  );
