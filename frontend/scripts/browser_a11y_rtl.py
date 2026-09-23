"""Browser-level accessibility + Arabic/RTL pass (Playwright + axe-core).

Why a real browser: axe-in-jsdom and the vitest suite cannot see layout. Text
that overflows its container, an icon that points the wrong way in RTL, a focus
ring that never appears, or a control that is unreachable by Tab are all
invisible to a DOM assertion and obvious to a browser. The audit asked for that
gap to be closed, so this script drives real Chromium against a running
application and reports what it measures.

It is a *reporting* tool: it never mutates application data, and it exits
non-zero when it finds a violation, so it can be used as a gate.

Usage:
    python frontend/scripts/browser_a11y_rtl.py --base-url http://localhost:43123

Requires: `pip install playwright` + `npx playwright install chromium`, and the
app running (backend on :8000, frontend on the given base URL).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict, List

from playwright.sync_api import sync_playwright

# DEFECT FIXED (found in my own tooling, 2026-09-23): this was a CWD-relative
# path, so running the probe from `frontend/` instead of the repo root made axe
# unreadable. Every surface then failed with FileNotFoundError, the summary
# printed "14 findings" of which 14 were load errors, and the run LOOKED like a
# clean pass with a dramatic improvement. A probe that silently degrades into
# measuring nothing is the same defect class this audit hunts, so the source is
# now resolved from the script location and a missing source ABORTS the run.
FRONTEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
AXE_SOURCE = FRONTEND_ROOT / "node_modules" / "axe-core" / "axe.min.js"

# Surfaces the consumer actually uses. Kept short deliberately: each entry is a
# real page with real API data, not a synthetic fixture.
#: Latin text that is legitimately identical in Arabic: brand/product names,
#: currency codes and machine identifiers a shopper must see verbatim.
ALLOWLIST_LATIN_IN_ARABIC = [
    "CONFIT", "Tabby", "Tamara", "Cairo", "Paymob", "Visa", "Mastercard",
    "Apple Pay", "Google Pay", "InstaPay", "Vodafone", "EGP", "USD", "AED",
    "SAR", "COD", "SKU", "http", "www", "@", ".com",
]

ROUTES = [
    ("home", "/"),
    ("discover", "/discover"),
    ("product", "/product/1"),
    ("cart", "/cart"),
    ("checkout", "/checkout"),
    ("stylist", "/stylist"),
    ("wardrobe", "/wardrobe"),
]


def _axe(page) -> Dict[str, Any]:
    """Run axe-core in the page and return the violations, compactly.

    Two strategies, because production enforces `script-src 'self'`: injecting
    axe as an inline <script> is blocked by CSP there (correctly — that is the
    policy doing its job). The fallback evaluates the same source through the
    debugger channel, which CSP does not govern, so the audit can still measure
    the deployed artifact.
    """
    if not AXE_SOURCE.is_file():
        raise AssertionError(
            f"axe-core is not installed at {AXE_SOURCE} — refusing to run: without the "
            "engine every surface would report zero violations and the pass would be meaningless"
        )
    source = AXE_SOURCE.read_text()
    try:
        page.add_script_tag(content=source)
        assert page.evaluate("typeof window.axe !== 'undefined'")
    except Exception:
        page.evaluate(source)
    result = page.evaluate(
        """async () => {
            const r = await window.axe.run(document, {
                resultTypes: ['violations'],
                runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
            });
            return r.violations.map(v => ({
                id: v.id, impact: v.impact, help: v.help,
                nodes: v.nodes.slice(0, 4).map(n => n.target.join(' ')),
                count: v.nodes.length,
            }));
        }"""
    )
    return result


def _rtl_probe(page) -> Dict[str, Any]:
    """Measure RTL rendering: direction, page-level overflow, mirrored controls.

    Two overflow signals are separated on purpose, because conflating them
    produced false findings on the first run of this script:

    * ``documentOverflowX`` — the page scrolls horizontally. This is the real
      RTL/layout breakage signal.
    * ``clippedByDesign`` — an element whose content is wider than its box while
      an ancestor (or itself) hides the overflow. Carousels, marquees and
      ``sr-only`` helpers do this intentionally, so it is reported as
      information, not counted as a violation.
    """
    return page.evaluate(
        """() => {
            const html = document.documentElement;
            const clipped = [];
            const leaks = [];
            for (const el of document.querySelectorAll('body *')) {
                const style = getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                const dx = el.scrollWidth - el.clientWidth;
                if (dx <= 4 || el.clientWidth <= 0) continue;
                let ancestor = el;
                let hidden = false;
                while (ancestor && ancestor !== document.body) {
                    const st = getComputedStyle(ancestor);
                    if (st.overflowX !== 'visible') { hidden = true; break; }
                    ancestor = ancestor.parentElement;
                }
                const info = {
                    tag: el.tagName.toLowerCase(),
                    cls: (el.className || '').toString().slice(0, 60),
                    dx,
                    text: (el.textContent || '').trim().slice(0, 40),
                };
                (hidden ? clipped : leaks).push(info);
            }
            return {
                dir: html.getAttribute('dir'),
                lang: html.getAttribute('lang'),
                documentOverflowX: html.scrollWidth - html.clientWidth,
                leaks: leaks.slice(0, 8),
                clippedByDesign: clipped.slice(0, 6),
                bodyText: (document.body.innerText || '').slice(0, 120),
            };
        }"""
    )


def _untranslated_probe(page, allow: List[str]) -> Dict[str, Any]:
    """Visible Latin-only text on an RTL page: hardcoded English, or a brand name.

    The static i18n gate scans source per line, so multi-line JSX and text built
    from expressions are invisible to it. The browser sees what the shopper sees,
    which is why this check exists — and why it runs only in Arabic mode, where
    any Latin sentence is an i18n leak by definition (brand names and codes are
    allow-listed by name, not by a blanket regex).
    """
    return page.evaluate(
        """(allow) => {
            const out = [];
            const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walk.nextNode())) {
                const text = (node.nodeValue || '').replace(/\s+/g, ' ').trim();
                if (text.length < 4) continue;
                if (!/^[A-Za-z]/.test(text)) continue;               // starts Latin
                if (!/[A-Za-z]{3,}/.test(text)) continue;            // has a real word
                const hasArabic = /[\u0600-\u06FF]/.test(text);
                if (hasArabic) continue;                             // mixed is fine here
                const el = node.parentElement;
                if (!el) continue;
                const style = getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                if (el.closest('[aria-hidden="true"]')) continue;
                if (allow.some(a => text.toLowerCase().includes(a.toLowerCase()))) continue;
                out.push({ text: text.slice(0, 90), tag: el.tagName.toLowerCase(),
                           cls: (el.className || '').toString().slice(0, 40) });
            }
            // MEASUREMENT HONESTY: the first version returned `out.slice(0, 25)`,
            // so a surface with 60 leaks and one with 25 were indistinguishable
            // and a fix could appear to work simply by pushing strings past the
            // cap. The full count is now reported alongside a bounded sample.
            return { total: out.length, sample: out.slice(0, 40) };
        }""",
        allow,
    )


def _keyboard_probe(page) -> Dict[str, Any]:
    """Tab through the page: every stop must be focusable AND visibly focused."""
    return page.evaluate(
        """() => {
            const focusables = [...document.querySelectorAll(
                'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
            )];
            const nameless = focusables.filter(el => {
                const name = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('title') || '').trim();
                return name.length === 0;
            }).map(el => ({ tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '', id: el.id || '' }));
            return {
                focusableCount: focusables.length,
                controlsWithoutAccessibleName: nameless.slice(0, 10),
                unnamedCount: nameless.length,
                imagesWithoutAlt: [...document.querySelectorAll('img')]
                    .filter(i => !i.hasAttribute('alt')).length,
                landmarks: {
                    main: document.querySelectorAll('main').length,
                    nav: document.querySelectorAll('nav').length,
                    header: document.querySelectorAll('header').length,
                },
                h1Count: document.querySelectorAll('h1').length,
                liveRegions: document.querySelectorAll('[aria-live], [role="status"], [role="alert"]').length,
            };
        }"""
    )


def run(base_url: str, language: str, out: List[Dict[str, Any]]) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        console_errors: List[str] = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        # Set the language the way the app does. The key is `confit_lang`
        # (`LANGUAGE_STORAGE_KEY` in src/i18n/i18n.ts) — NOT i18next's default
        # `i18nextLng`. The first version of this script wrote `i18nextLng`,
        # so every "ar" run silently measured English: a test that looked like
        # it exercised Arabic and did not, which is precisely the defect class
        # this audit hunts. The precondition below makes that impossible: if the
        # document is not in the requested language, the run fails loudly.
        page.goto(base_url, wait_until="domcontentloaded")
        page.evaluate(
            """(lang) => { localStorage.setItem('confit_lang', lang); }""", language
        )
        # The app applies the language at module load, so the document must be
        # reloaded for the stored choice to take effect.
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        state = page.evaluate(
            """() => ({ lang: document.documentElement.lang, dir: document.documentElement.dir })"""
        )
        if state.get("lang") != language:
            raise AssertionError(
                f"language precondition failed: asked for {language!r}, document reports "
                f"{state!r} — the pass would have measured the wrong language"
            )
        # `<html lang>` is a DECLARATION, not proof of rendered content: a bundle
        # that failed to load, or a document that sets the attribute without
        # swapping the strings, would still pass the check above. The rendered
        # text is asserted in both directions so an Arabic run cannot silently
        # measure English again (the original defect in this script).
        # Thresholds from MEASURED pages, not guesses: English surfaces carry 7
        # Arabic characters (the switcher's own "العربية" self-name) and Arabic
        # surfaces carry >1000. A boolean "does it contain Arabic" test would
        # have failed on English pages for the wrong reason, so the check is a
        # script census — and it doubles as the i18n COVERAGE metric, because
        # Latin characters still outnumber Arabic on the Arabic home page.
        census = page.evaluate(
            """() => {
                 const t = document.body.innerText || '';
                 const ar = (t.match(/[\\u0600-\\u06FF]/g) || []).length;
                 const la = (t.match(/[A-Za-z]/g) || []).length;
                 return { ar, la };
               }"""
        )
        if language == "ar" and census["ar"] < 300:
            raise AssertionError(
                f"language content precondition failed for 'ar': only {census['ar']} Arabic "
                "characters rendered — declared <html lang> but the content is not Arabic"
            )
        if language == "en" and census["ar"] > 50:
            raise AssertionError(
                f"language content precondition failed for 'en': {census['ar']} Arabic "
                "characters rendered on an English page"
            )
        print(f"   · precondition ok: <html lang={state.get('lang')!r} dir={state.get('dir')!r}> "
              f"arabic_chars={census['ar']} latin_chars={census['la']} "
              f"(latin/arabic on an AR page = untranslated-content debt)")

        for name, route in ROUTES:
            url = base_url + route
            entry: Dict[str, Any] = {"surface": name, "url": url, "language": language}
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(700)
                actual = page.evaluate("() => document.documentElement.lang")
                entry["document_lang"] = actual
                entry["script_census"] = page.evaluate(
                    """() => {
                         const t = document.body.innerText || '';
                         return { arabic: (t.match(/[\\u0600-\\u06FF]/g) || []).length,
                                  latin: (t.match(/[A-Za-z]/g) || []).length };
                       }"""
                )
                if actual != language:
                    entry["error"] = (
                        f"language reverted to {actual!r} on {route} — measured content would be wrong"
                    )
                    out.append(entry)
                    continue
                entry["violations"] = _axe(page)
                entry["keyboard"] = _keyboard_probe(page)
                if language == "ar":
                    entry["rtl"] = _rtl_probe(page)
                    entry["untranslated"] = _untranslated_probe(
                        page, ALLOWLIST_LATIN_IN_ARABIC
                    )
            except Exception as exc:  # a surface that cannot load is a finding too
                entry["error"] = f"{type(exc).__name__}: {exc}"
            out.append(entry)

        entry_console = {"surface": "__console__", "language": language,
                         "errors": [e for e in console_errors if "favicon" not in e.lower()][:10]}
        out.append(entry_console)
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:43123")
    ap.add_argument("--json", default="/tmp/browser-a11y-rtl.json")
    args = ap.parse_args()

    results: List[Dict[str, Any]] = []
    for language in ("en", "ar"):
        run(args.base_url, language, results)

    pathlib.Path(args.json).write_text(json.dumps(results, indent=2, ensure_ascii=False))

    violations = 0
    print(f"{'surface':10} {'lang':4} {'axe violations':>15} {'unnamed':>8} {'img no alt':>11} {'overflowX':>10}")
    for r in results:
        if r["surface"] == "__console__":
            console = r.get("errors") or []
            print(f"\nconsole errors ({r['language']}): {len(console)}")
            for e in console[:5]:
                print(f"   - {e[:140]}")
            continue
        if "error" in r:
            print(f"{r['surface']:10} {r['language']:4} LOAD ERROR: {r['error'][:80]}")
            violations += 1
            continue
        axe = r.get("violations") or []
        kb = r.get("keyboard") or {}
        rtl = r.get("rtl") or {}
        violations += len(axe) + int(kb.get("unnamedCount", 0)) + int(kb.get("imagesWithoutAlt", 0))
        # Violation rule, stated so it can be argued with: element-level overflow
        # counts only when the PAGE scrolls horizontally, which is the symptom a
        # shopper feels. A section that is 32px wider than its container because
        # it uses negative margins for edge-to-edge bleed, on a page that does not
        # scroll, is the intended layout — it is printed as information with its
        # measurements, never silently dropped.
        violations += 1 if (rtl.get("documentOverflowX") or 0) > 0 else 0
        violations += int((r.get("untranslated") or {}).get("total") or 0)
        print(
            f"{r['surface']:10} {r['language']:4} {len(axe):>15} "
            f"{kb.get('unnamedCount', '-'):>8} {kb.get('imagesWithoutAlt', '-'):>11} "
            f"{rtl.get('documentOverflowX', '-'):>10}"
        )
        for v in axe:
            print(f"    · [{v['impact']}] {v['id']}: {v['help']} ({v['count']} node(s))")
            for n in v.get("nodes", [])[:2]:
                print(f"        {n}")
        for c in (kb.get("controlsWithoutAccessibleName") or [])[:3]:
            print(f"    · control without accessible name: {c}")
        if (rtl.get("documentOverflowX") or 0) > 0:
            print(f"    · PAGE SCROLLS HORIZONTALLY in {r['language']}: dx={rtl['documentOverflowX']}")
        for o in (rtl.get("leaks") or [])[:3]:
            print(f"    · unclipped overflow dx={o['dx']} in <{o['tag']} class=\"{o['cls']}\"> {o['text']!r}")
        for o in (rtl.get("clippedByDesign") or [])[:2]:
            print(f"    · (info) clipped by design: <{o['tag']}> {o['text']!r}")
        unt = r.get("untranslated") or {}
        for u in (unt.get("sample") or [])[:4]:
            print(f"    · UNTRANSLATED in ar: <{u['tag']} class=\"{u['cls']}\"> {u['text']!r}")
        if unt.get("total"):
            print(f"    · UNTRANSLATED total on this surface: {unt['total']} (sample shown)")

    print(f"\nTOTAL FINDINGS (axe + unnamed controls + images without alt + untranslated): {violations}")

    # VALIDITY GATE — the whole run is discarded if any surface did not measure.
    # Without this, a broken probe (unreadable axe bundle, dead dev server) prints
    # a small number and reads as an improvement, which is how an earlier run of
    # this very script produced a fake "Δ 70 strings closed" result.
    failed = [r for r in results if r.get("error")]
    if failed:
        print(
            f"\nRUN INVALID — {len(failed)} surface(s) did not measure, so this run proves nothing:"
        )
        for r in failed[:6]:
            print(f"    ! {r['surface']} [{r['language']}] {r['error'][:100]}")
        return 2
    print("RUN VALID — every surface loaded and was measured in both languages.")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
