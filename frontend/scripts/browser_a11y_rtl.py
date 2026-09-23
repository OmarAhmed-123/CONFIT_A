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
from typing import Any, Dict, List, Tuple

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

ONLY_ROUTES: Optional[set] = None   # set by --only; None means all


ROUTES = [
    ("home", "/"),
    ("discover", "/discover"),
    # A REAL slug, not /product/1: the route is /product/:slug, so an arbitrary
    # numeric id may render an empty or partial shell — measuring a surface the
    # shopper never sees would make the whole sweep unfaithful.
    ("product", "/product/silk-slip-column-maxi-dress"),
    ("cart", "/cart"),
    ("checkout", "/checkout"),
    ("stylist", "/stylist"),
    ("wardrobe", "/wardrobe"),
    # Added 2026-09-23 after the route table was read instead of assumed: these
    # consumer routes existed all cycle and were never in the sweep, so their
    # findings could not appear in any total the report quoted.
    ("fit_finder", "/fit"),
    ("my_looks", "/my-looks"),
    ("builder", "/builder"),
    ("orders", "/orders"),
    ("profile", "/profile"),
    ("returns", "/returns"),
]


def _axe(page, injected=None) -> Dict[str, Any]:
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
    # ORDER MATTERS FOR MEASUREMENT INTEGRITY: `add_script_tag` was tried first,
    # and in production the CSP `script-src 'self'` blocks it — which the browser
    # logs as "Executing inline script violates the following Content Security
    # Policy". Those log lines were then collected by this script's own console
    # listener and reported as console errors, i.e. the probe accused the app of
    # a violation the probe itself committed. A no-injection control run on the
    # same deployment shows 0 console errors. The debugger channel used by
    # `page.evaluate` is not governed by the page CSP, so it goes FIRST and the
    # (noisier, sometimes-blocked) script-tag route is only a fallback.
    try:
        page.evaluate(source)
        assert page.evaluate("typeof window.axe !== 'undefined'")
    except Exception:
        page.add_script_tag(content=source)
    if injected is not None:
        injected[0] = True
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
                const text = (node.nodeValue || '').replace(/\\s+/g, ' ').trim();
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


#: ARIA roles that are controls a user must be able to identify by name.
_AX_CONTROL_ROLES = {
    "button", "link", "checkbox", "radio", "combobox", "listbox", "menuitem",
    "menuitemcheckbox", "menuitemradio", "slider", "spinbutton", "switch", "tab",
    "textbox", "searchbox",
}


def _ax_name_audit(page) -> Dict[str, Any]:
    """Ask the BROWSER for accessible names instead of guessing them.

    Why this replaced a JavaScript heuristic (2026-09-23)
    ----------------------------------------------------
    The previous version decided a control was unnamed unless it had
    `aria-label`, `title` or text content:

        const name = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('title') || '').trim();

    That ignores the most ordinary way to name a form field — a `<label for>` —
    so it reported five nameless inputs on /fit (fit-height, fit-weight,
    fit-chest, fit-waist, fit-hip) when the browser's own accessibility tree
    names every one of them ("Height", "Weight", "Chest / Bust (optional)", ...).
    Five invented findings is the same class of failure as a hidden one: the
    report would have claimed a defect that does not exist, and a future fix
    would have "resolved" nothing.

    The authoritative source is the accessibility tree Chrome builds. It applies
    the full accessible-name computation (aria-labelledby → aria-label →
    associated label → placeholder → title → contents), so what it reports is
    what a screen reader actually announces. `placeholder` as the ONLY name is
    real but weaker — the name disappears the moment the user types — so it is
    counted in its own bucket and never silently merged into "unnamed".
    """
    cdp = page.context.new_cdp_session(page)
    try:
        cdp.send("Accessibility.enable")
        # The DOM domain must be enabled before pushNodesByBackendIdsToFrontend /
        # getOuterHTML / getAttributes will answer ("Document needs to be
        # requested first" otherwise) — a probe-side protocol requirement, not an
        # application defect.
        cdp.send("DOM.enable")
        cdp.send("DOM.getDocument", {"depth": 0})   # "Document needs to be requested first"
        tree = cdp.send("Accessibility.getFullAXTree")
        nameless: List[Dict[str, Any]] = []
        placeholder_only: List[Dict[str, Any]] = []
        controls = 0
        pending: List[Tuple[str, int]] = []       # (bucket, backendNodeId)
        for node in tree.get("nodes", []):
            if node.get("ignored"):
                continue
            role = (node.get("role") or {}).get("value") or ""
            if role not in _AX_CONTROL_ROLES:
                continue
            backend_id = node.get("backendDOMNodeId")
            if not backend_id:
                continue
            controls += 1
            name = ((node.get("name") or {}).get("value") or "").strip()
            if not name:
                pending.append(("nameless", backend_id, ""))
            else:
                pending.append(("check_placeholder", backend_id, name))

        # Resolve the DOM element for each control of interest so the evidence
        # shows real markup, not just a role name.
        frontend_ids = cdp.send(
            "DOM.pushNodesByBackendIdsToFrontend",
            {"backendNodeIds": [entry[1] for entry in pending]},
        ).get("nodeIds", [])
        # Ids that a real <label for=...> points at: a control with one of these is
        # labelled by content, whatever else it also carries.
        labelled_ids = set(
            cdp.send("Runtime.evaluate", {
                "expression": "Array.from(document.querySelectorAll('label[for]')).map(l => l.htmlFor)",
                "returnByValue": True,
            }).get("result", {}).get("value") or []
        )
        for (bucket, _, ax_name), node_id in zip(pending, frontend_ids):
            if not node_id:
                continue
            html = cdp.send("DOM.getOuterHTML", {"nodeId": node_id}).get("outerHTML", "")
            if bucket == "nameless":
                nameless.append({"html": html[:160]})
                continue
            attrs = cdp.send("DOM.getAttributes", {"nodeId": node_id}).get("attributes", [])
            amap = dict(zip(attrs[0::2], attrs[1::2]))
            placeholder = (amap.get("placeholder") or "").strip()
            # PLACEHOLDER-ONLY means the placeholder IS the name. The first rule tested
            # for the mere PRESENCE of a placeholder attribute and so flagged any input
            # that had one — measured 2026-09-23: it reported
            # `<input placeholder="…" aria-label="اسم الإطلالة">` as placeholder-only, an
            # input whose accessible name comes from aria-label and survives typing. A
            # check that fires on a correctly labelled control is not a finding, it is a
            # broken instrument. Three conditions are required instead:
            #   1. the computed accessible NAME is the placeholder text, and
            #   2. no aria-label / aria-labelledby is present, and
            #   3. no <label for=...> points at the control.
            has_explicit_label = bool(
                (amap.get("aria-label") or "").strip()
                or (amap.get("aria-labelledby") or "").strip()
                or (amap.get("id") and amap["id"] in labelled_ids)
            )
            if placeholder and not has_explicit_label and ax_name == placeholder:
                placeholder_only.append({
                    "placeholder": placeholder[:80], "accessibleName": ax_name[:80],
                    "html": html[:160],
                })
        return {
            "axControls": controls,
            "namelessCount": len(nameless),
            "nameless": nameless[:10],
            "placeholderOnlyCount": len(placeholder_only),
            "placeholderOnly": placeholder_only[:10],
        }
    finally:
        cdp.detach()


def _keyboard_census(page) -> Dict[str, Any]:
    """A STATIC census of the focusable controls on the page.

    Renamed 2026-09-23. It used to be called `_keyboard_probe` with the
    docstring "Tab through the page: every stop must be focusable AND visibly
    focused" — but it never pressed Tab, never checked that focus is visible and
    never looked at focus order. The name claimed a measurement the function did
    not perform, which is the defect class this whole script exists to catch, so
    the claim was corrected in both directions: this function now says what it
    is, and `_keyboard_traversal` below performs the real traversal.
    """
    return page.evaluate(
        """() => {
            const focusables = [...document.querySelectorAll(
                'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
            )];
            // Accessible-name verdicts moved to `_ax_name_audit`, which asks the
            // browser's accessibility tree. A DOM-text guess here produced five
            // false "unnamed control" findings on /fit.
            return {
                focusableCount: focusables.length,
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


#: How many Tab presses per page. Bounded on purpose: a page with a hundred
#: stops should not spend a minute proving it, and 30 stops is enough to reach
#: the primary navigation, the main content and any sticky overlay — which is
#: where focus problems actually live. The bound is REPORTED as a bound.
KEYBOARD_TAB_BUDGET = 30

#: Controls that exist only in the DEV build and must not be reported as
#: application accessibility findings. `App.tsx` renders
#: `{import.meta.env.DEV && <ReactQueryDevtools/>}`, and that widget's toggle is
#: a focusable button with no visible focus indicator — measured locally and, on
#: purpose, absent from production (the production pass of 2026-09-23 found zero
#: such controls), which is what makes it environment noise rather than a
#: defect. Classified by name so any NEW indicator-less control still fails.
DEV_ONLY_CONTROL_MARKERS = ("tanstack query devtools", "open tanstack")

_FOCUS_SNAPSHOT_JS = """() => {
    // Reads `document.activeElement` INSIDE the page. The first version took the
    // element as an argument from a separate `page.evaluate`, which serialises a
    // DOM node into a plain object — `getComputedStyle` then threw
    // "Failed to execute 'getComputedStyle' on 'Window'" on every surface, and
    // the run was correctly reported as RUN INVALID rather than as a clean pass
    // (that gate is the reason this bug was caught instead of published).
    const el = document.activeElement;
    if (!el || el === document.body || el === document.documentElement) return {};
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();

    // ── WCAG 2.2 2.4.11 (AA) vs 2.4.12 (AAA) ────────────────────────────────
    // AA fails only when the focused component is ENTIRELY hidden; the AAA
    // criterion is the one that forbids PARTIAL covering. A single centre-point
    // hit test cannot tell those apart — it answers "the centre is covered",
    // which is neither claim, and would report a partly visible control as an AA
    // failure. Five points are therefore sampled (centre + four inset corners)
    // and the visible fraction is reported:
    //     visibleFraction == 0 → entirelyObscured → 2.4.11 AA failure
    //     0 < fraction < 1     → partlyObscured   → 2.4.12 AAA concern only
    // PROPORTIONAL sampling, not a fixed 2px inset. With a fixed inset the four
    // "corner" points of a small or visually-clipped control (the skip link is
    // clipped to a sliver by design) fall OUTSIDE the element, so it scored
    // visibleFraction=0.2 and was reported as partly obscured when nothing was
    // covering it at all — a fabricated finding. Sampling at 25%/75% of the
    // element's own width and height keeps every point inside it, whatever its
    // size.
    const pts = [
        [r.left + r.width / 2, r.top + r.height / 2],
        [r.left + r.width * 0.25, r.top + r.height * 0.25],
        [r.left + r.width * 0.75, r.top + r.height * 0.25],
        [r.left + r.width * 0.25, r.top + r.height * 0.75],
        [r.left + r.width * 0.75, r.top + r.height * 0.75],
    ];
    let hits = 0, mine = 0;
    for (const p of pts) {
        if (p[0] <= 0 || p[1] <= 0 || p[0] >= innerWidth || p[1] >= innerHeight) continue;
        const hit = document.elementFromPoint(p[0], p[1]);
        hits += 1;
        if (hit === el || el.contains(hit)) mine += 1;
    }
    const centre = document.elementFromPoint(Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2));
    const centreHit = (centre && centre !== el && !el.contains(centre))
        ? (centre.tagName + '.' + String(centre.className || '').split(' ').slice(0, 2).join('.')) : null;
    return {
        tag: el.tagName.toLowerCase(),
        text: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 50),
        rect: { top: Math.round(r.top), left: Math.round(r.left),
                w: Math.round(r.width), h: Math.round(r.height) },
        inViewport: r.top >= 0 && r.bottom <= innerHeight,
        visible: !!(r.width && r.height) && cs.visibility !== 'hidden' && cs.display !== 'none',
        outline: cs.outlineStyle + ' ' + cs.outlineWidth + ' ' + cs.outlineColor,
        hasOutline: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0,
        boxShadow: cs.boxShadow,
        samplePoints: hits,
        visibleFraction: hits ? Math.round((mine / hits) * 100) / 100 : null,
        entirelyObscured: hits > 0 && mine === 0,
        partlyObscured: hits > 0 && mine > 0 && mine < hits,
        obscuredBy: centreHit,
    };
}"""


def _settle_focus(page, attempts: int = 8) -> None:
    """Wait until focus-driven scrolling has stopped moving the focused element.

    Reason (2026-09-23): the traversal pressed Tab and hit-tested immediately. If
    the browser was still scrolling the newly focused element into view, the
    coordinates were stale and a perfectly visible control could be reported as
    obscured. A measurement that depends on scroll-animation timing is not a
    measurement. The rect must be identical on two consecutive reads.
    """
    previous = None
    for _ in range(attempts):
        rect = page.evaluate(
            """() => { const el = document.activeElement;
                        if (!el) return null;
                        const r = el.getBoundingClientRect();
                        return [Math.round(r.top), Math.round(r.left)]; }"""
        )
        if rect == previous:
            return
        previous = rect
        page.wait_for_timeout(70)


def _keyboard_traversal(page) -> Dict[str, Any]:
    """Press Tab for real and measure what the keyboard user experiences.

    What is actually measured, per stop:
      * the element that received focus (tag, name, geometry);
      * whether it is visible and how far down the page it sits;
      * whether a focus INDICATOR is present, and of which kind — an outline or
        a box-shadow. Both are legitimate; the absence of both is the failure.
        This is a proxy for WCAG 2.4.7 (Focus Visible) and 2.4.13 (Focus
        Appearance); it deliberately does not claim to measure indicator
        CONTRAST, which needs a pixel comparison the probe cannot do reliably
        against gradients.
      * WCAG 2.2 2.4.11 (Focus Not Obscured, AA): whether the element painted at
        the centre of the focused control is the control itself. A sticky header
        covering the focused link is a real failure that axe does not detect.

    Bounded: at most KEYBOARD_TAB_BUDGET stops, reported as `tabBudget`.
    Keyboard state is reset first (focus the document body) so the traversal
    starts from a known point rather than wherever the previous probe left it.
    """
    page.evaluate("() => { document.body.focus?.(); document.activeElement?.blur?.(); }")
    stops: List[Dict[str, Any]] = []
    seen = set()
    for _ in range(KEYBOARD_TAB_BUDGET):
        page.keyboard.press("Tab")
        _settle_focus(page)
        snap = page.evaluate(_FOCUS_SNAPSHOT_JS)
        if not snap.get("tag"):
            break
        # ── An obscured reading must REPRODUCE before it is reported ──────────
        # `entirelyObscured` was measured exactly once per stop. Focus can land
        # while the browser is still scrolling the element into view (or while
        # React is re-rendering around a layout shift), and a single reading taken
        # at that moment describes neither the settled page nor a user experience
        # — it is a photograph of a transition. A finding that cannot be reproduced
        # 300ms later is not a finding; it is my instrument's timing.
        # Measured 2026-09-23: /builder (ar) reported one entirely-obscured button
        # this way; re-checking the identical focus by hand showed the element
        # hit-testing to itself, i.e. not obscured once things settled.
        if snap.get("entirelyObscured"):
            first_read = snap.get("obscuredBy")
            confirmed = False
            for _ in range(3):
                page.wait_for_timeout(300)
                recheck = page.evaluate(_FOCUS_SNAPSHOT_JS)
                if recheck.get("tag") and recheck.get("entirelyObscured"):
                    confirmed = True
                    snap = recheck
                    break
            if not confirmed:
                snap["obscuredTransient"] = True
                snap["obscuredByOnFirstRead"] = first_read
                snap["entirelyObscured"] = False
        key = (snap["tag"], snap.get("text"), snap["rect"]["top"], snap["rect"]["left"])
        if key in seen:  # focus has cycled — the traversal is complete
            break
        seen.add(key)
        stops.append(snap)
    no_indicator = [
        s for s in stops
        if not s["hasOutline"] and s["boxShadow"] in ("none", "")
        and not any(m in (s.get("text") or "").lower() for m in DEV_ONLY_CONTROL_MARKERS)
    ]
    dev_only = [
        s for s in stops
        if not s["hasOutline"] and s["boxShadow"] in ("none", "")
        and any(m in (s.get("text") or "").lower() for m in DEV_ONLY_CONTROL_MARKERS)
    ]
    obscured = [s for s in stops if s.get("entirelyObscured")]
    transient = [
        s for s in stops
        if s.get("obscuredTransient")
    ]
    partly = [s for s in stops if s.get("partlyObscured")]
    return {
        "tabBudget": KEYBOARD_TAB_BUDGET,
        "stopsObserved": len(stops),
        "stoppedEarly": len(stops) < KEYBOARD_TAB_BUDGET,
        "stopsWithoutFocusIndicator": no_indicator[:8],
        "noIndicatorCount": len(no_indicator),
        "devOnlyChrome": [{"tag": s["tag"], "text": s["text"]} for s in dev_only[:4]],
        "obscured": obscured[:8],
        "obscuredCount": len(obscured),
        "obscuredTransientNotReproduced": [
            {"tag": s["tag"], "text": s["text"], "firstReadSaw": s.get("obscuredByOnFirstRead")}
            for s in transient[:6]
        ],
        "obscuredTransientCount": len(transient),
        "partlyObscured": [{"tag": s["tag"], "text": s["text"],
                            "visibleFraction": s["visibleFraction"],
                            "obscuredBy": s.get("obscuredBy")} for s in partly[:8]],
        "partlyObscuredCount": len(partly),
        "truth": [{"tag": s["tag"], "text": s["text"], "indicator": "outline" if s["hasOutline"] else ("shadow" if s["boxShadow"] not in ("none", "") else "none")} for s in stops[:12]],
    }



def _raw_key_probe(page) -> Dict[str, Any]:
    """Visible text that looks like an UNRESOLVED i18n key or a lost placeholder.

    Why this exists (found 2026-09-23, in my own earlier patch): a scripted edit
    rewrote four JSX attributes as `eyebrow="{t('key')}"` instead of
    `eyebrow={t('key')}`. The braces were inside a STRING literal, so React
    rendered the placeholder itself: the Discover mood stack and the product
    "complete the look" stack displayed `{t('discover.mood_stack_title')}` to
    shoppers. TypeScript, ESLint and the i18n key-parity gate all passed — the
    file is syntactically valid JSX and the key really does exist. Only rendering
    it reveals the mistake.

    The untranslated-text detector did see these strings, but reported them as
    generic untranslated copy, which is how a self-inflicted regression passes for
    technical debt. This probe names the shape explicitly.
    """
    return page.evaluate(
        """() => {
            const text = document.body.innerText || '';
            const patterns = [
                /\\{t\\(/gi,            // {t('key')} rendered as text
                /\bt\\(['"][a-z0-9_.]+['"]\\)/gi,  // a bare t('key') call in output
                /\\{\\{\\w+\\}\\}/g,      // unconsumed interpolation slot
            ];
            const hits = [];
            for (const re of patterns) {
                let m;
                while ((m = re.exec(text)) !== null && hits.length < 12) {
                    hits.push({ pattern: String(re), match: m[0].slice(0, 60) });
                }
            }
            return { hits, count: hits.length };
        }"""
    )


def run(base_url: str, language: str, out: List[Dict[str, Any]]) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        console_errors: List[Dict[str, str]] = []
        injected = [False]
        # Errors are tagged with whether THIS SCRIPT had injected axe when they
        # fired. Injected code can itself violate the page CSP (production sends
        # `script-src 'self'`) and Chromium then logs the violation as if the page
        # had caused it — an earlier version of this script collected those and
        # very nearly reported two production defects that were its own doing. The
        # no-injection control pass below is what settles it.
        page.on(
            "console",
            lambda m: console_errors.append(
                {"during": "probe-injected" if injected[0] else "app-only", "text": m.text}
            )
            if m.type == "error"
            else None,
        )
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
            if ONLY_ROUTES is not None and name not in ONLY_ROUTES:
                continue
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
                entry["violations"] = _axe(page, injected)
                entry["raw_keys"] = _raw_key_probe(page)
                entry["keyboard"] = _keyboard_census(page)
                entry["ax_names"] = _ax_name_audit(page)
                entry["keyboard_traversal"] = _keyboard_traversal(page)
                entry["typography"] = page.evaluate(
                    """() => {
                         const body = getComputedStyle(document.body);
                         const faces = [];
                         document.fonts.forEach(f => faces.push(f.family + ' ' + f.status));
                         return { bodyFontFamily: body.fontFamily,
                                  cairoUsable: document.fonts.check('16px Cairo'),
                                  cairoFaces: faces.filter(f => /cairo/i.test(f)),
                                  loadedFaces: document.fonts.size };
                       }"""
                )
                if language == "ar":
                    entry["rtl"] = _rtl_probe(page)
                    entry["untranslated"] = _untranslated_probe(
                        page, ALLOWLIST_LATIN_IN_ARABIC
                    )
            except Exception as exc:  # a surface that cannot load is a finding too
                entry["error"] = f"{type(exc).__name__}: {exc}"
            out.append(entry)

        entry_console = {"surface": "__console__", "language": language,
                         "errors": [e for e in console_errors
                                    if "favicon" not in str(e.get("text", "")).lower()][:10]}
        out.append(entry_console)
        browser.close()


def console_control(base_url: str, language: str) -> Dict[str, Any]:
    """Same pages, same language, NO injection: the app's own console output.

    This exists because the probe's axe injection can trip the production CSP and
    the resulting log lines are indistinguishable from app errors once collected.
    Whatever this pass reports is the application's; whatever the instrumented
    pass reports on top of it belongs to the instrument.
    """
    errors: List[Dict[str, str]] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda m: errors.append({"tag": m.type, "text": m.text})
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append({"tag": "pageerror", "text": str(e)}))
        page.goto(base_url, wait_until="domcontentloaded")
        page.evaluate("(lang) => { localStorage.setItem('confit_lang', lang); }", language)
        page.reload(wait_until="networkidle")
        for _, route in ROUTES:
            page.goto(base_url + route, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(500)
        browser.close()
    return {"surface": "__console_control__", "language": language,
            "injection": False, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:43123")
    ap.add_argument("--json", default="/tmp/browser-a11y-rtl.json")
    # Subset re-measurement: a probe that can only run the full sweep cannot
    # answer "did THIS route change?", and re-running 26 surfaces to check one
    # is how a capped sample starts looking like a total.
    ap.add_argument("--only", default=None,
                    help="comma-separated route names to measure (default: all)")
    args = ap.parse_args()

    global ONLY_ROUTES
    if args.only:
        ONLY_ROUTES = {n.strip() for n in args.only.split(",") if n.strip()}
        unknown = ONLY_ROUTES - {name for name, _ in ROUTES}
        if unknown:
            # a typo would otherwise produce an empty sweep that looks like a clean one
            raise SystemExit(f"--only names not in the route table: {sorted(unknown)}")

    results: List[Dict[str, Any]] = []
    for language in ("en", "ar"):
        run(args.base_url, language, results)
        results.append(console_control(args.base_url, language))

    pathlib.Path(args.json).write_text(json.dumps(results, indent=2, ensure_ascii=False))

    violations = 0
    print(f"{'surface':10} {'lang':4} {'axe violations':>15} {'unnamedAX':>10} {'img no alt':>11} {'overflowX':>10}")
    for r in results:
        if r["surface"] in ("__console__", "__console_control__"):
            console = r.get("errors") or []
            if r["surface"] == "__console_control__":
                print(f"\nconsole errors, NO injection ({r['language']}) — these are the APP's: "
                      f"{len(console)}")
                for e in console[:5]:
                    print(f"   - {str(e.get('text') if isinstance(e, dict) else e)[:140]}")
                continue
            app_only = [e for e in console if isinstance(e, dict) and e.get("during") == "app-only"]
            probe = [e for e in console if isinstance(e, dict) and e.get("during") == "probe-injected"]
            print(f"\nconsole errors while instrumented ({r['language']}): {len(console)} "
                  f"[app-only {len(app_only)}, probe-injected {len(probe)}]")
            for e in console[:5]:
                txt = e.get("text") if isinstance(e, dict) else e
                during = e.get("during", "?") if isinstance(e, dict) else "?"
                print(f"   - [{during}] {str(txt)[:130]}")
            continue
        if "error" in r:
            print(f"{r['surface']:10} {r['language']:4} LOAD ERROR: {r['error'][:80]}")
            violations += 1
            continue
        axe = r.get("violations") or []
        kb = r.get("keyboard") or {}
        rtl = r.get("rtl") or {}
        violations += len(axe) + int((r.get("ax_names") or {}).get("namelessCount") or 0) \
            + int(kb.get("imagesWithoutAlt", 0))
        # Violation rule, stated so it can be argued with: element-level overflow
        # counts only when the PAGE scrolls horizontally, which is the symptom a
        # shopper feels. A section that is 32px wider than its container because
        # it uses negative margins for edge-to-edge bleed, on a page that does not
        # scroll, is the intended layout — it is printed as information with its
        # measurements, never silently dropped.
        violations += int((r.get("raw_keys") or {}).get("count") or 0)
        violations += int((r.get("keyboard_traversal") or {}).get("noIndicatorCount") or 0)
        violations += int((r.get("keyboard_traversal") or {}).get("obscuredCount") or 0)
        violations += 1 if (rtl.get("documentOverflowX") or 0) > 0 else 0
        violations += int((r.get("untranslated") or {}).get("total") or 0)
        print(
            f"{r['surface']:10} {r['language']:4} {len(axe):>15} "
            f"{(r.get('ax_names') or {}).get('namelessCount', '-'):>8} {kb.get('imagesWithoutAlt', '-'):>11} "
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
        typ = r.get("typography") or {}
        if typ:
            print(f"    · typography [{r['language']}]: body={typ.get('bodyFontFamily','')[:46]!r} "
                  f"cairo_usable={typ.get('cairoUsable')} cairo_faces={len(typ.get('cairoFaces') or [])} "
                  f"loaded_faces={typ.get('loadedFaces')}")
        raw = r.get("raw_keys") or {}
        if raw.get("count"):
            print(f"    · RAW i18n PLACEHOLDER rendered [{r['language']}]: {raw['count']} -> "
                  + "; ".join(h['match'] for h in raw['hits'][:3]))
        ax = r.get("ax_names") or {}
        if ax.get("namelessCount"):
            print(f"    · UNNAMED CONTROL (browser AX tree) [{r['language']}]: {ax['namelessCount']} -> "
                  + " | ".join(h["html"][:90] for h in ax["nameless"][:3]))
        if ax.get("placeholderOnlyCount"):
            print(f"    · PLACEHOLDER-ONLY LABEL (weaker, counted separately) [{r['language']}]: "
                  f"{ax['placeholderOnlyCount']} -> '"
                  + " | ".join(h["placeholder"] for h in ax["placeholderOnly"][:3]) + "'")
        kt = r.get("keyboard_traversal") or {}
        if kt:
            print(f"    · keyboard traversal [{r['language']}]: {kt['stopsObserved']}/{kt['tabBudget']} stops"
                  f" (early stop: {kt['stoppedEarly']}), no indicator: {kt['noIndicatorCount']},"
                  f" obscured: {kt['obscuredCount']}")
            for st in (kt.get("stopsWithoutFocusIndicator") or [])[:3]:
                print(f"        no focus indicator: <{st['tag']}> {st['text'][:40]!r}")
            if kt.get("partlyObscuredCount"):
                print(f"        · partly obscured (2.4.12 AAA concern, NOT an AA failure): "
                      f"{kt['partlyObscuredCount']}")
            for st in (kt.get("obscured") or [])[:3]:
                print(f"        OBSCURED (2.4.11): <{st['tag']}> {st['text'][:32]!r} hidden by {st['obscuredBy']}")
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
