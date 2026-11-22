import io

from pptx import Presentation

from tests.integration.test_api import API, new_chat, upload
from tests.integration.test_quizzes import CELLS


def _queue_slides(llm, n=2, **deck):
    llm.queue(
        **(
            {"title": "Energy in cells", "subtitle": "Respiration and photosynthesis"}
            | deck
        ),
        slides=[
            {
                "title": f"Slide {i}",
                "bullets": ["Point one", "Point two"],
                "notes": "Speaker notes.",
                "sources": ["S1"],
            }
            for i in range(n)
        ],
    )


def test_generate_view_download_and_delete(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_slides(llm, 3)
    r = client.post(f"{API}/slides", json={"document_ids": [doc], "slide_count": 3})
    assert r.status_code == 201, r.text
    deck = r.json()
    assert deck["title"] == "Energy in cells"
    assert [s["position"] for s in deck["slides"]] == [1, 2, 3]
    src = deck["slides"][0]["sources"][0]
    assert src["filename"] == "bio.pdf" and src["document_id"] == doc
    assert "<source" in llm.calls[-1][-1].content

    listing = client.get(f"{API}/slides").json()
    assert listing[0]["slide_count"] == 3 and listing[0]["filenames"] == ["bio.pdf"]
    assert client.get(f"{API}/slides/{deck['id']}").json()["id"] == deck["id"]

    f = client.get(f"{API}/slides/{deck['id']}/pptx")
    assert f.status_code == 200
    assert f.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="Energy in cells.pptx"' in f.headers["content-disposition"]
    assert len(Presentation(io.BytesIO(f.content)).slides) == 4  # title + 3

    assert client.delete(f"{API}/slides/{deck['id']}").status_code == 204
    assert client.get(f"{API}/slides/{deck['id']}").status_code == 404


def test_deck_from_conversation_with_topic_and_fallback_title(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    conv = new_chat(client, [doc])
    _queue_slides(llm, 1, title=None, subtitle=None)
    r = client.post(
        f"{API}/slides", json={"conversation_id": conv, "topic": "mitochondria"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "mitochondria" and body["topic"] == "mitochondria"
    assert body["subtitle"] == "Based on bio.pdf"
    assert body["conversation_id"] == conv


def test_invalid_generator_output_is_a_422(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    llm.queue(slides=[{"title": "No sources", "bullets": ["x"]}])
    r = client.post(f"{API}/slides", json={"document_ids": [doc]})
    assert r.status_code == 422 and "No valid slides" in r.json()["detail"]


def test_needs_documents_and_processed_pdf(client):
    assert client.post(f"{API}/slides", json={}).status_code == 422
    assert (
        client.post(
            f"{API}/slides", json={"document_ids": [], "slide_count": 2}
        ).status_code
        == 422
    )
    doc = upload(client, [None], name="scan.pdf").json()["document"]["id"]
    r = client.post(f"{API}/slides", json={"document_ids": [doc]})
    assert r.status_code == 422 and "processed PDF" in r.json()["detail"]


def test_decks_are_private(client, db, other_user):
    from backend.models import SlideDeck

    deck = SlideDeck(owner_id=other_user.id, title="theirs")
    db.add(deck)
    db.commit()
    assert client.get(f"{API}/slides/{deck.id}").status_code == 404
    assert client.get(f"{API}/slides/{deck.id}/pptx").status_code == 404
    assert client.delete(f"{API}/slides/{deck.id}").status_code == 404
    assert client.get(f"{API}/slides").json() == []


def _make(client, llm, n=3):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_slides(llm, n)
    return client.post(
        f"{API}/slides", json={"document_ids": [doc], "slide_count": n}
    ).json()


def test_design_and_title_are_saved_and_used_in_export(client, llm):
    deck = _make(client, llm)
    assert deck["design"]["theme"] == "auto" and deck["design"]["bullets"] == "dot"
    url = f"{API}/slides/{deck['id']}"
    r = client.patch(
        url,
        json={
            "title": "My talk",
            "subtitle": None,
            "design": {"theme": "forest", "accent": "#123456", "align": "center"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "My talk" and body["subtitle"] is None
    assert (
        body["design"]["theme"] == "forest"
        and body["design"]["heading_font"] == "serif"
    )
    assert client.get(url).json()["design"]["accent"] == "#123456"

    # Leaving fields out keeps them.
    client.patch(url, json={"subtitle": "New sub"})
    again = client.get(url).json()
    assert again["title"] == "My talk" and again["design"]["theme"] == "forest"

    f = client.get(f"{url}/pptx")
    assert 'filename="My talk.pptx"' in f.headers["content-disposition"]
    first = next(iter(Presentation(io.BytesIO(f.content)).slides))
    assert str(first.background.fill.fore_color.rgb) == "F2F5EF"

    assert client.patch(url, json={"design": {"theme": "neon"}}).status_code == 422


def test_edit_reorder_add_and_delete_slides(client, llm):
    deck = _make(client, llm, 3)
    a, b, c = deck["slides"]
    new_id = "11111111-2222-4333-8444-555555555555"
    r = client.put(
        f"{API}/slides/{deck['id']}/slides",
        json={
            "slides": [
                {"id": c["id"], "title": "  Moved first ", "bullets": [" x ", "", "y"]},
                {"id": new_id, "title": "Brand new", "bullets": ["z"], "notes": "n"},
                {"id": a["id"], "title": a["title"], "bullets": a["bullets"]},
            ]
        },
    )
    assert r.status_code == 200, r.text
    slides = r.json()["slides"]
    assert [s["title"] for s in slides] == ["Moved first", "Brand new", a["title"]]
    assert [s["position"] for s in slides] == [1, 2, 3]
    assert slides[0]["id"] == c["id"] and slides[0]["bullets"] == ["x", "y"]
    assert slides[0]["sources"] == c["sources"]  # citations survive edits
    assert slides[1]["id"] == new_id and slides[1]["sources"] == []
    assert b["id"] not in {s["id"] for s in slides}

    pptx = client.get(f"{API}/slides/{deck['id']}/pptx").content
    assert len(Presentation(io.BytesIO(pptx)).slides) == 4


def test_slide_edits_are_validated(client, llm):
    deck = _make(client, llm, 3)
    url = f"{API}/slides/{deck['id']}/slides"
    assert client.put(url, json={"slides": []}).status_code == 422
    assert client.put(url, json={"slides": [{"title": ""}]}).status_code == 422
    assert (
        client.put(
            url, json={"slides": [{"title": "t", "bullets": ["x" * 501]}]}
        ).status_code
        == 422
    )


def test_editing_another_users_deck_is_404(client, db, other_user):
    from backend.models import SlideDeck

    deck = SlideDeck(owner_id=other_user.id, title="theirs")
    db.add(deck)
    db.commit()
    assert (
        client.patch(f"{API}/slides/{deck.id}", json={"title": "x"}).status_code == 404
    )
    assert (
        client.put(
            f"{API}/slides/{deck.id}/slides", json={"slides": [{"title": "x"}]}
        ).status_code
        == 404
    )


def _slide_json(title, sources=("S1",)):
    return {
        "title": title,
        "bullets": ["Point one", "Point two"],
        "notes": "Notes.",
        "sources": list(sources),
    }


def test_missing_slides_are_topped_up_before_takeaways(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    llm.queue(
        title="Cells",
        subtitle="",
        slides=[_slide_json("Intro"), _slide_json("Key takeaways")],
    )
    # Second request: one repeat (dropped) and two new slides.
    llm.queue(
        slides=[_slide_json("Intro"), _slide_json("Extra A"), _slide_json("Extra B")]
    )
    r = client.post(f"{API}/slides", json={"document_ids": [doc], "slide_count": 4})
    assert r.status_code == 201, r.text
    titles = [s["title"] for s in r.json()["slides"]]
    assert titles == ["Intro", "Extra A", "Extra B", "Key takeaways"]
    assert [s["position"] for s in r.json()["slides"]] == [1, 2, 3, 4]
    follow_up = llm.calls[-1][-1].content
    assert "Write exactly 2 more" in follow_up and "- Intro" in follow_up


def test_top_up_stops_after_two_tries(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    llm.queue(slides=[_slide_json("Only one")])
    llm.queue(slides=[])
    r = client.post(f"{API}/slides", json={"document_ids": [doc], "slide_count": 5})
    assert r.status_code == 201
    assert [s["title"] for s in r.json()["slides"]] == ["Only one"]


def test_revise_one_slide_keeps_others_and_citations(client, llm):
    deck = _make(client, llm, 3)
    target = deck["slides"][1]
    llm.queue(
        slides=[
            {
                "title": "Shorter slide",
                "bullets": ["Just one point"],
                "notes": "",
                "sources": [],
            }
        ]
    )
    r = client.post(
        f"{API}/slides/{deck['id']}/revise",
        json={"instruction": "Make it shorter", "slide_id": target["id"]},
    )
    assert r.status_code == 200, r.text
    slides = r.json()["slides"]
    assert slides[1]["id"] == target["id"] and slides[1]["title"] == "Shorter slide"
    assert slides[1]["sources"] == target["sources"]  # rewording keeps citations
    assert [s["title"] for s in slides[::2]] == [
        deck["slides"][0]["title"],
        deck["slides"][2]["title"],
    ]
    prompt = llm.calls[-1][-1].content
    assert "<instruction>\nMake it shorter\n</instruction>" in prompt
    assert "<current_slide>" in prompt and "<source" in prompt


def test_revise_whole_deck_and_undo_restores_citations(client, llm):
    deck = _make(client, llm, 3)
    llm.queue(
        title="Revised deck",
        subtitle="Now simpler",
        slides=[
            {**_slide_json(deck["slides"][0]["title"], ()), "bullets": ["Simpler"]},
            _slide_json("A new slide", ("S1",)),
        ],
    )
    url = f"{API}/slides/{deck['id']}"
    r = client.post(f"{url}/revise", json={"instruction": "Use simpler language"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Revised deck" and body["subtitle"] == "Now simpler"
    assert [s["title"] for s in body["slides"]] == [
        deck["slides"][0]["title"],
        "A new slide",
    ]
    # Reused slide text keeps the old slide's citations.
    assert body["slides"][0]["sources"] == deck["slides"][0]["sources"]

    # Undo = restore the snapshot, citations included.
    snapshot = [
        {k: s[k] for k in ("id", "title", "bullets", "notes", "sources")}
        for s in deck["slides"]
    ]
    assert client.put(f"{url}/slides", json={"slides": snapshot}).status_code == 200
    client.patch(url, json={"title": deck["title"], "subtitle": deck["subtitle"]})
    restored = client.get(url).json()
    assert restored["title"] == deck["title"]
    assert [s["sources"] for s in restored["slides"]] == [
        s["sources"] for s in deck["slides"]
    ]


def test_revise_validation_and_unknown_slide(client, llm):
    deck = _make(client, llm, 3)
    url = f"{API}/slides/{deck['id']}/revise"
    assert client.post(url, json={"instruction": "x"}).status_code == 422
    r = client.post(
        url, json={"instruction": "Make it shorter", "slide_id": deck["id"]}
    )
    assert r.status_code == 404
    llm.queue(slides="not a list")
    r = client.post(url, json={"instruction": "Make it shorter"})
    assert r.status_code == 422
