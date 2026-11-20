"""PowerPoint export for slide decks, using the deck's design settings (theme, fonts, layout)."""

import io
from collections import defaultdict
from dataclasses import dataclass

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from backend.models import SlideDeck
from backend.schemas.slides import SlideDesign

# background, text, accent - the same palettes the app uses for its slide themes.
THEMES: dict[str, tuple[str, str, str]] = {
    "paper": ("F5F0E6", "1E1A15", "962F22"),  # Noesis light
    "ink": ("14161B", "EBE3D3", "E58466"),  # Noesis dark
    "slate": ("F4F6F8", "1F2937", "2563EB"),
    "forest": ("F2F5EF", "1D2B22", "2F6B45"),
    "midnight": ("0F172A", "E2E8F0", "38BDF8"),
}
FONTS = {"serif": "Georgia", "sans": "Calibri", "mono": "Consolas"}

WIDTH, HEIGHT = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.9)


@dataclass(frozen=True)
class Style:
    paper: RGBColor
    ink: RGBColor
    ink_2: RGBColor
    ink_3: RGBColor
    accent: RGBColor
    heading: str
    body: str
    align: PP_ALIGN
    bullets: str
    show_numbers: bool
    show_sources: bool


def _mix(a: str, b: str, weight: float) -> RGBColor:
    """`weight` of colour a blended into colour b (both hex)."""
    pa, pb = bytes.fromhex(a), bytes.fromhex(b)
    return RGBColor(
        *(round(x * weight + y * (1 - weight)) for x, y in zip(pa, pb, strict=True))
    )


def style_for(design: SlideDesign) -> Style:
    paper, ink, accent = THEMES.get(design.theme, THEMES["paper"])
    if design.accent:
        accent = design.accent.lstrip("#").upper()
    return Style(
        paper=RGBColor.from_string(paper),
        ink=RGBColor.from_string(ink),
        ink_2=_mix(ink, paper, 0.75),
        ink_3=_mix(ink, paper, 0.55),
        accent=RGBColor.from_string(accent),
        heading=FONTS[design.heading_font],
        body=FONTS[design.body_font],
        align=PP_ALIGN.CENTER if design.align == "center" else PP_ALIGN.LEFT,
        bullets=design.bullets,
        show_numbers=design.show_numbers,
        show_sources=design.show_sources,
    )


def cite(sources: list[dict]) -> str:
    """ "file.pdf p. 3, 5; other.pdf p. 2" in reading order."""
    pages: dict[str, list[int]] = defaultdict(list)
    for s in sources:
        if s["page_number"] not in pages[s["filename"]]:
            pages[s["filename"]].append(s["page_number"])
    return "; ".join(
        f"{name} p. {', '.join(str(p) for p in sorted(nums))}"
        for name, nums in pages.items()
    )


def _background(slide, st: Style) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = st.paper


def _text(slide, left, top, width, height, text, *, size, color, font, align=None):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    paragraph = frame.paragraphs[0]
    if align is not None:
        paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    run.font.size, run.font.name = Pt(size), font
    run.font.color.rgb = color
    return box


def _rule(slide, st: Style, top, width) -> None:
    left = (WIDTH - width) // 2 if st.align == PP_ALIGN.CENTER else MARGIN
    line = slide.shapes.add_shape(1, left, top, width, Pt(2.5))  # 1 = rectangle
    line.fill.solid()
    line.fill.fore_color.rgb = st.accent
    line.line.fill.background()


def _bullet_marker(p_pr, st: Style) -> None:
    indent = Emu(Inches(0.4))
    if st.bullets == "none":
        p_pr.append(p_pr.makeelement(qn("a:buNone"), {}))
        return
    p_pr.set("marL", str(indent))
    p_pr.set("indent", str(-indent))
    color = p_pr.makeelement(qn("a:buClr"), {})
    color.append(color.makeelement(qn("a:srgbClr"), {"val": str(st.accent)}))
    p_pr.append(color)
    if st.bullets == "number":
        p_pr.append(p_pr.makeelement(qn("a:buFont"), {"typeface": st.body}))
        p_pr.append(p_pr.makeelement(qn("a:buAutoNum"), {"type": "arabicPeriod"}))
        return
    p_pr.append(p_pr.makeelement(qn("a:buFont"), {"typeface": "Arial"}))
    char = "•" if st.bullets == "dot" else "–"
    p_pr.append(p_pr.makeelement(qn("a:buChar"), {"char": char}))


def _bullets(frame, bullets: list[str], st: Style) -> None:
    size = 22 if len(bullets) <= 3 else 20 if len(bullets) == 4 else 18
    for i, text in enumerate(bullets):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.space_after = Pt(size * 0.6)
        p.alignment = st.align
        _bullet_marker(p._p.get_or_add_pPr(), st)
        run = p.add_run()
        run.text = text
        run.font.size, run.font.name = Pt(size), st.body
        run.font.color.rgb = st.ink


def build_pptx(deck: SlideDeck, design: SlideDesign | None = None) -> bytes:
    st = style_for(design or SlideDesign())
    prs = Presentation()
    prs.slide_width, prs.slide_height = WIDTH, HEIGHT
    blank = prs.slide_layouts[6]
    content_width = WIDTH - 2 * MARGIN
    total = len(deck.slides)
    names = list(
        dict.fromkeys(s["filename"] for slide in deck.slides for s in slide.sources)
    )

    # Title slide.
    slide = prs.slides.add_slide(blank)
    _background(slide, st)
    _text(
        slide,
        MARGIN,
        Inches(1.6),
        content_width,
        Inches(0.4),
        "NOESIS · STUDY DECK",
        size=12,
        color=st.accent,
        font=FONTS["mono"],
        align=st.align,
    )
    title = _text(
        slide,
        MARGIN,
        Inches(2.2),
        content_width,
        Inches(2.0),
        deck.title,
        size=48,
        color=st.ink,
        font=st.heading,
        align=st.align,
    )
    title.text_frame.vertical_anchor = MSO_ANCHOR.TOP
    title.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    _rule(slide, st, Inches(4.35), Inches(1.2))
    if deck.subtitle:
        _text(
            slide,
            MARGIN,
            Inches(4.6),
            content_width,
            Inches(1.0),
            deck.subtitle,
            size=20,
            color=st.ink_2,
            font=st.heading,
            align=st.align,
        )
    if names and st.show_sources:
        _text(
            slide,
            MARGIN,
            HEIGHT - Inches(1.0),
            content_width,
            Inches(0.4),
            "From " + ", ".join(names),
            size=12,
            color=st.ink_3,
            font=FONTS["mono"],
            align=st.align,
        )

    for item in deck.slides:
        slide = prs.slides.add_slide(blank)
        _background(slide, st)
        if st.show_numbers:
            _text(
                slide,
                WIDTH - MARGIN - Inches(1.5),
                Inches(0.45),
                Inches(1.5),
                Inches(0.3),
                f"{item.position:02d} / {total:02d}",
                size=11,
                color=st.ink_3,
                font=FONTS["mono"],
                align=PP_ALIGN.RIGHT,
            )
        heading = _text(
            slide,
            MARGIN,
            Inches(0.8),
            content_width,
            Inches(1.1),
            item.title,
            size=34,
            color=st.ink,
            font=st.heading,
            align=st.align,
        )
        heading.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _rule(slide, st, Inches(2.0), Inches(0.9))

        if item.bullets:
            body = slide.shapes.add_textbox(
                MARGIN, Inches(2.4), content_width, Inches(4.0)
            )
            frame = body.text_frame
            frame.word_wrap = True
            frame.margin_left = frame.margin_right = 0
            frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
            _bullets(frame, item.bullets, st)

        if item.sources and st.show_sources:
            _text(
                slide,
                MARGIN,
                HEIGHT - Inches(0.7),
                content_width,
                Inches(0.35),
                "Source: " + cite(item.sources),
                size=11,
                color=st.ink_3,
                font=FONTS["mono"],
                align=st.align,
            )
        # Speaker notes always keep the citation, even when it is hidden on the slide.
        notes = item.notes.strip()
        if item.sources:
            notes = f"{notes}\n\nSource: {cite(item.sources)}".strip()
        if notes:
            slide.notes_slide.notes_text_frame.text = notes

    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()
