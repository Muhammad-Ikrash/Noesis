from tests.integration.test_api import API, new_chat, upload

# Quiz sampling skips passages under 150 characters, so these pages are longer than BIO.
CELLS = [
    (
        "Photosynthesis happens in chloroplasts using chlorophyll. Light energy splits water, "
        "releasing oxygen, and the Calvin cycle then fixes carbon dioxide into sugars."
    ),
    (
        "Mitochondria produce ATP by aerobic respiration. Glucose is broken down through "
        "glycolysis, the Krebs cycle and the electron transport chain, which needs oxygen."
    ),
]


def _queue_quiz(llm, n=2):
    llm.queue(
        questions=[
            {
                "question": f"Q{i}?",
                "options": ["Mitochondria", "Ribosome", "Nucleus", "Golgi"],
                "correct_index": 0,
                "explanation": "Stated on the page.",
                "source": "S1",
            }
            for i in range(n)
        ]
    )


def test_generate_attempt_and_review(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_quiz(llm)
    r = client.post(f"{API}/quizzes", json={"document_ids": [doc], "question_count": 2})
    assert r.status_code == 201, r.text
    quiz = r.json()
    assert len(quiz["questions"]) == 2
    assert (
        "correct_index" not in quiz["questions"][0]
    )  # no answer key before attempting

    res = client.post(
        f"{API}/quizzes/{quiz['id']}/attempts", json={"answers": [0, None]}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["score"] == 1 and body["total"] == 2
    assert (
        body["questions"][0]["correct_index"] == 0
        and body["questions"][0]["filename"] == "bio.pdf"
    )

    listing = client.get(f"{API}/quizzes").json()
    assert listing[0]["best_score"] == 1 and listing[0]["attempt_count"] == 1
    assert (
        client.get(f"{API}/quizzes/{quiz['id']}/attempts/{body['id']}").json()["score"]
        == 1
    )


def test_quiz_from_conversation_with_topic(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    conv = new_chat(client, [doc])
    _queue_quiz(llm, 1)
    r = client.post(
        f"{API}/quizzes", json={"conversation_id": conv, "topic": "mitochondria"}
    )
    assert r.status_code == 201 and r.json()["topic"] == "mitochondria"
    assert "<source" in llm.calls[-1][-1].content


def test_wrong_answer_count_rejected(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_quiz(llm)
    quiz = client.post(f"{API}/quizzes", json={"document_ids": [doc]}).json()
    assert (
        client.post(
            f"{API}/quizzes/{quiz['id']}/attempts", json={"answers": [0]}
        ).status_code
        == 422
    )


def test_quiz_needs_processed_pdf(client):
    doc = upload(client, [None], name="scan.pdf").json()["document"]["id"]
    r = client.post(f"{API}/quizzes", json={"document_ids": [doc]})
    assert r.status_code == 422 and "processed PDF" in r.json()["detail"]


def test_quizzes_are_private(client, db, other_user):
    from backend.models import Quiz

    quiz = Quiz(owner_id=other_user.id, title="theirs")
    db.add(quiz)
    db.commit()
    assert client.get(f"{API}/quizzes/{quiz.id}").status_code == 404
    assert (
        client.post(
            f"{API}/quizzes/{quiz.id}/attempts", json={"answers": []}
        ).status_code
        == 404
    )
    assert client.get(f"{API}/quizzes").json() == []
