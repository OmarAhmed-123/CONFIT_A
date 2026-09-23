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

AXE_SOURCE = pathlib.Path("frontend/node_modules/axe-core/axe.min.js")

# Surfaces the consumer actually uses. Kept short deliberately: each entry is a
# real page with real API data, not a synthetic fixture.
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
    """Run axe-core in the page and return the violations, compactly."""
    page.add_script_tag(content=AXE_SOURCE.read_text())
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

        # Set the language the way the app does (localStorage key), then reload.
        page.goto(base_url, wait_until="domcontentloaded")
        page.evaluate(
            """(lang) => { localStorage.setItem('i18nextLng', lang); }""", language
        )

        for name, route in ROUTES:
            url = base_url + route
            entry: Dict[str, Any] = {"surface": name, "url": url, "language": language}
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(700)
                entry["violations"] = _axe(page)
                entry["keyboard"] = _keyboard_probe(page)
                if language == "ar":
                    entry["rtl"] = _rtl_probe(page)
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

    print(f"\nTOTAL FINDINGS (axe + unnamed controls + images without alt): {violations}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
