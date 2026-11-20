from tests.integration.test_api import API, new_chat, upload
from tests.integration.test_quizzes import CELLS


def _queue_cards(llm, n=2):
    llm.queue(
        cards=[
            {"front": f"Card {i}?", "back": "Mitochondria make ATP.", "source": "S1"}
            for i in range(n)
        ]
    )


def test_generate_study_and_reset(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_cards(llm, 3)
    r = client.post(f"{API}/flashcards", json={"document_ids": [doc], "card_count": 3})
    assert r.status_code == 201, r.text
    deck = r.json()
    cards = deck["cards"]
    assert [c["position"] for c in cards] == [1, 2, 3]
    assert cards[0]["filename"] == "bio.pdf" and cards[0]["document_id"] == doc
    assert not any(c["known"] for c in cards)
    assert deck["title"].startswith("Flashcards: ")

    url = f"{API}/flashcards/{deck['id']}/cards"
    r = client.patch(f"{url}/{cards[0]['id']}", json={"known": True})
    assert r.status_code == 200 and r.json()["known"] is True
    assert r.json()["reviewed_at"] is not None
    client.patch(f"{url}/{cards[1]['id']}", json={"known": False})

    summary = client.get(f"{API}/flashcards").json()[0]
    assert summary["card_count"] == 3 and summary["known_count"] == 1
    assert summary["last_studied_at"] is not None

    reset = client.post(f"{API}/flashcards/{deck['id']}/reset")
    assert reset.status_code == 200
    assert not any(c["known"] or c["reviewed_at"] for c in reset.json()["cards"])

    assert client.delete(f"{API}/flashcards/{deck['id']}").status_code == 204
    assert client.get(f"{API}/flashcards/{deck['id']}").status_code == 404


def test_deck_from_conversation_with_topic(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    conv = new_chat(client, [doc])
    _queue_cards(llm, 1)
    r = client.post(
        f"{API}/flashcards", json={"conversation_id": conv, "topic": "mitochondria"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["topic"] == "mitochondria" and body["conversation_id"] == conv
    assert body["title"] == "Flashcards: mitochondria"
    assert "flashcards" in llm.calls[-1][-1].content


def test_invalid_generator_output_is_a_422(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    llm.queue(cards=[{"front": "No source", "back": "x"}])
    r = client.post(f"{API}/flashcards", json={"document_ids": [doc]})
    assert r.status_code == 422 and "No valid flashcards" in r.json()["detail"]


def test_needs_documents_and_processed_pdf(client):
    assert client.post(f"{API}/flashcards", json={}).status_code == 422
    doc = upload(client, [None], name="scan.pdf").json()["document"]["id"]
    r = client.post(f"{API}/flashcards", json={"document_ids": [doc]})
    assert r.status_code == 422 and "processed PDF" in r.json()["detail"]


def test_unknown_card_is_404(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_cards(llm, 1)
    deck = client.post(f"{API}/flashcards", json={"document_ids": [doc]}).json()
    r = client.patch(
        f"{API}/flashcards/{deck['id']}/cards/{deck['id']}", json={"known": True}
    )
    assert r.status_code == 404


def test_decks_are_private(client, db, other_user):
    from backend.models import Flashcard, FlashcardDeck

    deck = FlashcardDeck(owner_id=other_user.id, title="theirs")
    deck.cards = [
        Flashcard(position=1, front="f", back="b", filename="x.pdf", page_number=1)
    ]
    db.add(deck)
    db.commit()
    card_id = deck.cards[0].id
    assert client.get(f"{API}/flashcards/{deck.id}").status_code == 404
    assert (
        client.patch(
            f"{API}/flashcards/{deck.id}/cards/{card_id}", json={"known": True}
        ).status_code
        == 404
    )
    assert client.post(f"{API}/flashcards/{deck.id}/reset").status_code == 404
    assert client.delete(f"{API}/flashcards/{deck.id}").status_code == 404
    assert client.get(f"{API}/flashcards").json() == []
