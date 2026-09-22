"""Renders the brand product/sales report as a professional PDF.

This module is deliberately a PURE RENDERER. It receives the dataset produced by
`BrandReportService` and draws it; it performs no aggregation, no filtering and
no business arithmetic of its own. That is what keeps the PDF and the dashboard
from ever disagreeing: there is exactly one place that decides what "units sold"
means, and it is not here.

Design notes:
  * The CONFIT logo is drawn as VECTOR geometry (the same interlocking C+F
    monogram as `frontend/src/components/common/ConfitLogo.tsx`, gold #C5A059 on
    navy), positioned top-LEFT of page 1. There is no raster logo in the
    repository, and embedding a bitmap would print badly; vector stays sharp at
    any zoom and adds no binary asset to the tree.
  * Tables repeat their header row on every page and never split a row across a
    page break (ReportLab's `repeatRows` + flowable splitting), which is the
    usual way these reports become unreadable.
  * Long product titles wrap inside their cell via Paragraph rather than being
    silently truncated.
  * Every page carries "Page N of M", the generation timestamp and the tenant
    name, so a printed page is self-identifying.
  * Money is formatted from Decimal, never float.
  * An empty dataset renders an explicit "no sales recorded" statement rather
    than an empty table or invented rows.
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

NAVY = colors.HexColor("#1B1F3B")
NAVY_DEEP = colors.HexColor("#0C0E1E")
GOLD = colors.HexColor("#C5A059")
GREY = colors.HexColor("#6B7280")
LIGHT = colors.HexColor("#F3F4F6")

PAGE = landscape(A4)
MARGIN = 14 * mm


def _money(value: Any, currency: str = "") -> str:
    if value is None:
        return "N/A"
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    s = f"{d:,.2f}"
    return f"{currency} {s}".strip() if currency else s


def _pct(value: Any) -> str:
    """A rate whose denominator was zero is undefined -- say so."""
    return "N/A" if value is None else f"{value:.1f}%"


def draw_logo(canvas, x: float, y: float, size: float = 17 * mm) -> None:
    """Draw the CONFIT monogram as vector art with its bottom-left at (x, y).

    Mirrors the app's ConfitLogo SVG (40x40 viewBox) so the printed report and
    the product carry the same mark.
    """
    canvas.saveState()
    s = size / 40.0  # viewBox is 40x40
    canvas.translate(x, y)
    canvas.scale(s, s)

    # Rounded navy tile.
    canvas.setFillColor(NAVY_DEEP)
    canvas.roundRect(0, 0, 40, 40, 10, stroke=0, fill=1)

    # SVG's y-axis points down; PDF's points up. Flip so the path coordinates
    # below can be copied straight from the component.
    canvas.translate(0, 40)
    canvas.scale(1, -1)

    # Outer gold arc -- the 'C'.
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(2.75)
    canvas.setLineCap(1)
    p = canvas.beginPath()
    p.moveTo(26, 12)
    p.curveTo(23.5, 9.8, 19.8, 9.5, 16.5, 11.2)
    p.curveTo(13.2, 12.9, 11, 16.3, 11, 20)
    p.curveTo(11, 23.7, 13.2, 27.1, 16.5, 28.8)
    p.curveTo(19.8, 30.5, 23.5, 30.2, 26, 28)
    canvas.drawPath(p, stroke=1, fill=0)

    # Inner white 'F'.
    canvas.setStrokeColor(colors.white)
    canvas.setLineWidth(2.5)
    f = canvas.beginPath()
    f.moveTo(18, 15.5); f.lineTo(27, 15.5)
    f.moveTo(18, 20.5); f.lineTo(24, 20.5)
    f.moveTo(18, 15.5); f.lineTo(18, 26)
    canvas.drawPath(f, stroke=1, fill=0)

    canvas.restoreState()


class _ReportDoc(BaseDocTemplate):
    """Two page templates: a first page with the logo header, then plain pages."""

    def __init__(self, buf, meta: Dict[str, Any]):
        super().__init__(buf, pagesize=PAGE,
                         leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=MARGIN, bottomMargin=16 * mm,
                         title=f"CONFIT Brand Report — {meta['brand_name']}",
                         author="CONFIT", subject="Brand product and sales report")
        self.meta = meta
        first_top = 46 * mm  # room for the logo block on page 1
        self.addPageTemplates([
            # autoNextPageTemplate is essential: without it EVERY page keeps the
            # first page's short frame (which reserves 46mm for the logo block)
            # and the logo header is redrawn on every page. Worse, a flowable
            # that needs the full height then raises LayoutError instead of
            # flowing on -- observed with long wrapped product titles.
            PageTemplate(id="first",
                         frames=[Frame(MARGIN, self.bottomMargin,
                                       PAGE[0] - 2 * MARGIN,
                                       PAGE[1] - first_top - self.bottomMargin)],
                         onPage=self._first_page,
                         autoNextPageTemplate="rest"),
            PageTemplate(id="rest",
                         frames=[Frame(MARGIN, self.bottomMargin,
                                       PAGE[0] - 2 * MARGIN,
                                       PAGE[1] - 26 * mm - self.bottomMargin)],
                         onPage=self._later_page),
        ])

    # -- page furniture --------------------------------------------------
    def _footer(self, canvas):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(MARGIN, 9 * mm,
                          f"CONFIT · {self.meta['brand_name']} · generated {self.meta['generated']}")
        canvas.drawRightString(PAGE[0] - MARGIN, 9 * mm,
                               f"Page {canvas.getPageNumber()} of {self.meta.get('total_pages', '?')}")
        canvas.setStrokeColor(LIGHT)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 12 * mm, PAGE[0] - MARGIN, 12 * mm)
        canvas.restoreState()

    def _first_page(self, canvas, doc):
        canvas.saveState()
        top = PAGE[1] - MARGIN

        # LOGO: top-left of page one, as required.
        draw_logo(canvas, MARGIN, top - 17 * mm, 17 * mm)

        # Wordmark beside the monogram.
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(MARGIN + 21 * mm, top - 7 * mm, "CONFIT")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GOLD)
        canvas.drawString(MARGIN + 21 * mm, top - 11.5 * mm, "FASHION INTELLIGENCE")

        # Title block, right aligned.
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 17)
        canvas.drawRightString(PAGE[0] - MARGIN, top - 6 * mm,
                               "Product & Sales Report")
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(GREY)
        canvas.drawRightString(PAGE[0] - MARGIN, top - 11.5 * mm,
                               self.meta["brand_name"])
        canvas.drawRightString(PAGE[0] - MARGIN, top - 16 * mm,
                               f"Period: {self.meta['period']}")
        canvas.drawRightString(PAGE[0] - MARGIN, top - 20.5 * mm,
                               f"Generated: {self.meta['generated']}  ·  Tenant ID: {self.meta['brand_id']}")

        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(1.2)
        canvas.line(MARGIN, top - 25 * mm, PAGE[0] - MARGIN, top - 25 * mm)
        self._footer(canvas)
        canvas.restoreState()

    def _later_page(self, canvas, doc):
        canvas.saveState()
        top = PAGE[1] - MARGIN
        draw_logo(canvas, MARGIN, top - 9 * mm, 9 * mm)
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(MARGIN + 12 * mm, top - 6 * mm,
                          f"CONFIT · Product & Sales Report · {self.meta['brand_name']}")
        canvas.setStrokeColor(LIGHT)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, top - 11 * mm, PAGE[0] - MARGIN, top - 11 * mm)
        self._footer(canvas)
        canvas.restoreState()


def render_report_pdf(data: Dict[str, Any]) -> bytes:
    """Render the dataset from BrandReportService into PDF bytes."""
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=8, leading=10,
                          textColor=NAVY)
    cell = ParagraphStyle("cell", parent=body, fontSize=7.6, leading=9)
    cell_r = ParagraphStyle("cellr", parent=cell, alignment=TA_RIGHT)
    # A TableStyle TEXTCOLOR does NOT override a Paragraph's own colour, so the
    # header must carry white explicitly or it renders navy-on-navy (invisible).
    head_s = ParagraphStyle("head", parent=cell, textColor=colors.white,
                            fontName="Helvetica-Bold")
    head_r = ParagraphStyle("headr", parent=head_s, alignment=TA_RIGHT)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, leading=13,
                        textColor=NAVY, spaceBefore=4, spaceAfter=5)
    note = ParagraphStyle("note", parent=body, fontSize=7.2, leading=9.4,
                          textColor=GREY, alignment=TA_LEFT)

    totals = data["totals"]
    cur = totals["currency"]
    meta = {
        "brand_name": data["brand"]["name"],
        "brand_id": data["brand"]["id"],
        "period": data["period"]["label"],
        "generated": data["generated_at"].strftime("%d %b %Y %H:%M UTC"),
    }

    def build_story() -> List[Any]:
        """Construct a FRESH flowable list for every build pass.

        ReportLab MUTATES flowables while laying them out (tables are split in
        place), so passing the same objects to a second build reuses exhausted
        state and raises LayoutError on long documents. `list(story)` only
        shallow-copies the container, not the flowables, so it does not help.
        """
        story: List[Any] = []

            # ---- summary tiles --------------------------------------------------
        summary = [[
            Paragraph("<b>Products</b><br/><br/><font size=13>%d</font>" % totals["products"], body),
            Paragraph("<b>Units sold</b><br/><br/><font size=13>%d</font>" % totals["units_sold"], body),
            Paragraph("<b>Gross sales</b><br/><br/><font size=13>%s</font>"
                      % _money(totals["gross_sales"], cur), body),
            Paragraph("<b>Net of returns opened</b><br/><br/><font size=13>%s</font>"
                      % _money(totals["net_sales"], cur), body),
            Paragraph("<b>Returns opened</b><br/><br/><font size=13>%d</font>" % totals["returned_units"], body),
            Paragraph("<b>Return rate</b><br/><br/><font size=13>%s</font>" % _pct(totals["return_rate"]), body),
        ]]
        t = Table(summary, colWidths=[(PAGE[0] - 2 * MARGIN) / 6.0] * 6)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ]))
        story += [t, Spacer(1, 7)]

        # ---- main table -----------------------------------------------------
        story.append(Paragraph("Products", h2))
        rows = data["rows"]
        if not rows:
            story.append(Paragraph(
                "<b>No products match the selected filters.</b> Nothing is inferred or "
                "estimated here: when the underlying tables hold no matching records the "
                "report says so.", note))
        else:
            head = ["Product", "Category", "Colour", "SKUs", "Units sold",
                    f"Gross ({cur})", f"Net ({cur})", "Returns", "Return rate",
                    "Sellable stock", "BOPIS qty", "BOPIS reserved"]
            # Numeric columns are right-aligned in the body, so their headers are too.
            numeric_from = 3
            table_rows: List[List[Any]] = [[
                Paragraph(h, head_s if i < numeric_from else head_r)
                for i, h in enumerate(head)]]
            for r in rows:
                table_rows.append([
                    Paragraph(r["title"], cell),
                    Paragraph(r["category"], cell),
                    Paragraph(r["color"], cell),
                    Paragraph(str(r["sku_count"]), cell_r),
                    Paragraph(str(r["units_sold"]), cell_r),
                    Paragraph(_money(r["gross_sales"]), cell_r),
                    Paragraph(_money(r["net_sales"]), cell_r),
                    Paragraph(str(r["returned_units"]), cell_r),
                    Paragraph(_pct(r["return_rate"]), cell_r),
                    Paragraph(str(r["stock_level"]), cell_r),
                    Paragraph(str(r["bopis_quantity"]), cell_r),
                    Paragraph(str(r["bopis_reserved"]), cell_r),
                ])
            table_rows.append([
                Paragraph("<b>TOTAL</b>", cell), Paragraph("", cell), Paragraph("", cell),
                Paragraph("", cell_r),
                Paragraph(f"<b>{totals['units_sold']}</b>", cell_r),
                Paragraph(f"<b>{_money(totals['gross_sales'])}</b>", cell_r),
                Paragraph(f"<b>{_money(totals['net_sales'])}</b>", cell_r),
                Paragraph(f"<b>{totals['returned_units']}</b>", cell_r),
                Paragraph(f"<b>{_pct(totals['return_rate'])}</b>", cell_r),
                Paragraph("", cell_r), Paragraph("", cell_r), Paragraph("", cell_r),
            ])

            avail = PAGE[0] - 2 * MARGIN
            weights = [3.0, 1.45, 1.0, 0.72, 0.95, 1.3, 1.3, 0.85, 1.0, 1.1, 0.88, 1.05]
            widths = [avail * w / sum(weights) for w in weights]
            main = Table(table_rows, colWidths=widths, repeatRows=1)
            main.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#FAFAFA")]),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FDF6E8")),
                ("LINEABOVE", (0, -1), (-1, -1), 0.9, GOLD),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ]))
            story.append(main)

        # ---- methodology ----------------------------------------------------
        story += [Spacer(1, 9), Paragraph("How these numbers are produced", h2),
                  Paragraph(data["methodology"], note), Spacer(1, 5),
                  Paragraph(
                      "This report is generated from the same authoritative commerce tables "
                      "that serve the portal dashboard, through one shared reporting service. "
                      "It contains no sample, placeholder or estimated values. Where a figure "
                      "cannot be derived truthfully it is shown as N/A with the reason stated "
                          "above rather than substituted with a zero.", note)]
        return story

    # Two-pass build so the footer can print "Page N of M": pass one counts the
    # pages, pass two renders with that count. Each pass gets its own flowables.
    doc = _ReportDoc(BytesIO(), meta)
    doc.build(build_story())
    meta["total_pages"] = doc.page

    buf = BytesIO()
    doc = _ReportDoc(buf, meta)
    doc.build(build_story())
    return buf.getvalue()
