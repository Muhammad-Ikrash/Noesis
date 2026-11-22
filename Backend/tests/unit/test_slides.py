import io
import json
import uuid

import pytest
from pptx import Presentation
from pptx.oxml.ns import qn

from backend.models import Slide, SlideDeck
from backend.models.enums import ChunkKind
from backend.services.retrieval import RetrievedChunk
from backend.services.slides_export import build_pptx, cite
from backend.services.slides_service import SlideGenerationError, _parse

DOC = uuid.uuid4()
CHUNKS = [
    RetrievedChunk(uuid.uuid4(), DOC, "Bio.pdf", 5, ChunkKind.TEXT, "ATP...", 1.0),
    RetrievedChunk(uuid.uuid4(), DOC, "Bio.pdf", 2, ChunkKind.TEXT, "Cells...", 1.0),
]


def slide(**kw):
    base = {
        "title": "Cellular respiration",
        "bullets": ["Glucose is broken down", "ATP is produced"],
        "notes": "Explain the  steps.",
        "sources": ["S1", "S2", "S1"],
    }
    return base | kw


def test_valid_slides_keep_sources_in_page_order():
    raw = json.dumps(
        {"title": "Energy", "subtitle": "How cells work", "slides": [slide()]}
    )
    title, subtitle, out = _parse(raw, CHUNKS, 8)
    assert (title, subtitle) == ("Energy", "How cells work")
    s = out[0]
    assert (s.position, s.title, s.notes) == (
        1,
        "Cellular respiration",
        "Explain the steps.",
    )
    assert s.bullets == ["Glucose is broken down", "ATP is produced"]
    assert s.sources == [
        {"document_id": str(DOC), "filename": "Bio.pdf", "page_number": 2},
        {"document_id": str(DOC), "filename": "Bio.pdf", "page_number": 5},
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {"sources": ["S9"]},
        {"sources": []},
        {"title": ""},
        {"title": "x" * 121},
        {"bullets": []},
        {"bullets": ["", 4, None]},
        {"bullets": "not a list"},
    ],
)
def test_unusable_slides_are_dropped(bad):
    raw = json.dumps({"slides": [slide(**bad), slide(title="Second")]})
    _, _, out = _parse(raw, CHUNKS, 8)
    assert [s.title for s in out] == ["Second"]


def test_bullets_are_trimmed_capped_and_duplicates_dropped():
    raw = json.dumps(
        {
            "slides": [
                slide(bullets=["  a  ", "", "b", "c", "d", "e", "f", "g", "x" * 301]),
                slide(title="cellular RESPIRATION"),
                slide(title="Third"),
            ]
        }
    )
    _, _, out = _parse(raw, CHUNKS, 8)
    assert out[0].bullets == ["a", "b", "c", "d", "e", "f"]
    assert [s.title for s in out] == ["Cellular respiration", "Third"]


def test_count_caps_slides_and_missing_title_is_none():
    raw = json.dumps({"slides": [slide(title=f"S{i}") for i in range(5)]})
    title, subtitle, out = _parse(raw, CHUNKS, 3)
    assert len(out) == 3 and title is None and subtitle is None


@pytest.mark.parametrize("raw", ["nope", "[]", '{"slides": {}}', '{"slides": []}'])
def test_unusable_response_is_a_clear_error(raw):
    with pytest.raises(SlideGenerationError):
        _parse(raw, CHUNKS, 8)


def test_cite_groups_pages_per_file():
    sources = [
        {"filename": "a.pdf", "page_number": 7},
        {"filename": "a.pdf", "page_number": 3},
        {"filename": "b.pdf", "page_number": 1},
        {"filename": "a.pdf", "page_number": 3},
    ]
    assert cite(sources) == "a.pdf p. 3, 7; b.pdf p. 1"


def test_pptx_has_title_slide_content_and_notes():
    deck = SlideDeck(title="Energy in cells", subtitle="From Bio.pdf")
    deck.slides = [
        Slide(
            position=1,
            title="Cellular respiration",
            bullets=["Glucose is broken down", "ATP is produced"],
            notes="Say more.",
            sources=[{"document_id": None, "filename": "Bio.pdf", "page_number": 5}],
        ),
        Slide(position=2, title="Takeaways", bullets=["One"], notes="", sources=[]),
    ]
    prs = Presentation(io.BytesIO(build_pptx(deck)))
    slides = list(prs.slides)
    assert len(slides) == 3
    assert prs.slide_width > prs.slide_height  # 16:9

    def texts(s):
        return [sh.text_frame.text for sh in s.shapes if sh.has_text_frame]

    assert "Energy in cells" in texts(slides[0])
    assert "From Bio.pdf" in " ".join(texts(slides[0]))
    body = texts(slides[1])
    assert "Cellular respiration" in body
    assert "Glucose is broken down\nATP is produced" in body
    assert "Source: Bio.pdf p. 5" in body
    assert "01 / 02" in body
    notes = slides[1].notes_slide.notes_text_frame.text
    assert notes.startswith("Say more.") and "Bio.pdf p. 5" in notes
    assert (
        not slides[2].has_notes_slide or not slides[2].notes_slide.notes_text_frame.text
    )


def test_passage_ids_are_removed_from_slide_text():
    raw = json.dumps(
        {
            "slides": [
                slide(
                    title="Design goals (S2)",
                    bullets=["Modular design [S2, S11]", "S3: extensible"],
                    notes="It uses a domain model (S2) and goals (S11).",
                )
            ]
        }
    )
    _, _, out = _parse(raw, CHUNKS, 8)
    s = out[0]
    assert s.title == "Design goals"
    assert s.bullets == ["Modular design", "extensible"]
    assert s.notes == "It uses a domain model and goals."


def _deck_for_design():
    deck = SlideDeck(title="Energy", subtitle="Sub")
    deck.slides = [
        Slide(
            position=1,
            title="Respiration",
            bullets=["One", "Two"],
            notes="",
            sources=[{"document_id": None, "filename": "Bio.pdf", "page_number": 5}],
        )
    ]
    return deck


def test_pptx_uses_design_theme_fonts_bullets_and_toggles():
    from pptx.dml.color import RGBColor

    from backend.schemas.slides import SlideDesign

    design = SlideDesign(
        theme="midnight",
        accent="#ff8800",
        heading_font="sans",
        body_font="mono",
        align="center",
        bullets="number",
        show_numbers=False,
        show_sources=False,
    )
    prs = Presentation(io.BytesIO(build_pptx(_deck_for_design(), design)))
    content = list(prs.slides)[1]
    assert content.background.fill.fore_color.rgb == RGBColor.from_string("0F172A")
    texts = {sh.text_frame.text: sh for sh in content.shapes if sh.has_text_frame}
    assert "01 / 01" not in texts and not any(t.startswith("Source:") for t in texts)
    heading = texts["Respiration"].text_frame.paragraphs[0]
    assert heading.runs[0].font.name == "Calibri" and heading.alignment == 2  # center
    body = texts["One\nTwo"].text_frame.paragraphs[0]
    assert body.runs[0].font.name == "Consolas"
    assert body._p.pPr.find(qn("a:buAutoNum")) is not None
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    rule = next(
        sh for sh in content.shapes if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
    )
    assert rule.fill.fore_color.rgb == RGBColor.from_string("FF8800")
    # The citation moves to the speaker notes when hidden on the slide.
    assert "Bio.pdf p. 5" in content.notes_slide.notes_text_frame.text


def test_pptx_default_design_matches_the_app():
    from pptx.dml.color import RGBColor

    prs = Presentation(io.BytesIO(build_pptx(_deck_for_design())))
    content = list(prs.slides)[1]
    assert content.background.fill.fore_color.rgb == RGBColor.from_string("F5F0E6")
    body = next(
        sh
        for sh in content.shapes
        if sh.has_text_frame and sh.text_frame.text == "One\nTwo"
    )
    assert body.text_frame.paragraphs[0]._p.pPr.find(qn("a:buChar")).get("char") == "•"


def test_design_rejects_unknown_values():
    from pydantic import ValidationError

    from backend.schemas.slides import SlideDesign

    for bad in ({"theme": "neon"}, {"accent": "red"}, {"bullets": "star"}, {"x": 1}):
        with pytest.raises(ValidationError):
            SlideDesign.model_validate(bad)


@pytest.mark.parametrize("ref", ["S1", "s1", "[S1]", "1", 1, " S1 "])
def test_source_ids_are_read_leniently(ref):
    _, _, out = _parse(json.dumps({"slides": [slide(sources=[ref])]}), CHUNKS, 8)
    assert out[0].sources[0]["page_number"] == 5


def test_revisions_may_keep_uncited_slides_and_skip_known_titles():
    raw = json.dumps(
        {"slides": [slide(sources=[]), slide(title="Existing", sources=["S2"])]}
    )
    with pytest.raises(SlideGenerationError):
        _parse(raw, CHUNKS, 8, skip_titles={"cellular respiration", "existing"})
    _, _, out = _parse(raw, CHUNKS, 8, require_sources=False, skip_titles={"existing"})
    assert [s.title for s in out] == ["Cellular respiration"] and out[0].sources == []
