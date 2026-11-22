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


def test_difficulty_and_question_types(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    llm.queue(
        questions=[
            {
                "type": "multiple",
                "question": "Which happen in mitochondria?",
                "options": [
                    "Glycolysis",
                    "Krebs cycle",
                    "Electron transport",
                    "Calvin cycle",
                ],
                "correct_indices": [1, 2],
                "explanation": "Stated on the page.",
                "source": "S1",
            },
            {
                "type": "true_false",
                "question": "The Calvin cycle releases oxygen.",
                "options": ["False", "True"],
                "correct_indices": [0],
                "explanation": "Oxygen comes from splitting water.",
                "source": "S1",
            },
        ]
    )
    r = client.post(
        f"{API}/quizzes",
        json={
            "document_ids": [doc],
            "question_count": 2,
            "difficulty": "hard",
            "question_types": ["multiple", "true_false"],
        },
    )
    assert r.status_code == 201, r.text
    quiz = r.json()
    assert quiz["difficulty"] == "hard"
    assert [x["kind"] for x in quiz["questions"]] == ["multiple", "true_false"]
    assert quiz["questions"][1]["options"] == ["True", "False"]
    prompt = llm.calls[-1][-1].content
    assert "Hard:" in prompt and '"multiple", "true_false"' in prompt

    res = client.post(
        f"{API}/quizzes/{quiz['id']}/attempts", json={"answers": [[2, 1], 1]}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["score"] == 2 and body["answers"] == [[2, 1], 1]
    assert body["questions"][0]["correct_indices"] == [1, 2]

    assert client.get(f"{API}/quizzes").json()[0]["difficulty"] == "hard"


def test_partial_multiple_choice_answer_scores_zero(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    llm.queue(
        questions=[
            {
                "type": "multiple",
                "question": "Which need oxygen?",
                "options": [
                    "Electron transport",
                    "Glycolysis",
                    "Aerobic respiration",
                    "Fermentation",
                ],
                "correct_indices": [0, 2],
                "source": "S1",
            }
        ]
    )
    quiz = client.post(
        f"{API}/quizzes",
        json={"document_ids": [doc], "question_types": ["multiple"]},
    ).json()
    res = client.post(
        f"{API}/quizzes/{quiz['id']}/attempts", json={"answers": [[0]]}
    )
    assert res.json()["score"] == 0


def test_several_answers_to_a_single_choice_question_rejected(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_quiz(llm, 1)
    quiz = client.post(f"{API}/quizzes", json={"document_ids": [doc]}).json()
    r = client.post(
        f"{API}/quizzes/{quiz['id']}/attempts", json={"answers": [[0, 1]]}
    )
    assert r.status_code == 422


def test_defaults_are_medium_single_choice(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_quiz(llm, 1)
    quiz = client.post(f"{API}/quizzes", json={"document_ids": [doc]}).json()
    assert quiz["difficulty"] == "medium"
    assert quiz["questions"][0]["kind"] == "single"
    assert "Medium:" in llm.calls[-1][-1].content


def test_empty_question_types_rejected(client):
    doc = upload(client, CELLS).json()["document"]["id"]
    r = client.post(
        f"{API}/quizzes", json={"document_ids": [doc], "question_types": []}
    )
    assert r.status_code == 422


# ---- Retry missed questions ----------------------------------------------------


def _attempt(client, quiz_id, answers):
    r = client.post(f"{API}/quizzes/{quiz_id}/attempts", json={"answers": answers})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_retry_contains_only_wrong_and_skipped_questions(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_quiz(llm, 3)
    quiz = client.post(
        f"{API}/quizzes",
        json={"document_ids": [doc], "question_count": 3, "difficulty": "hard"},
    ).json()
    # Q0 right, Q1 wrong, Q2 skipped.
    attempt = _attempt(client, quiz["id"], [0, 2, None])
    calls_before = len(llm.calls)

    r = client.post(f"{API}/quizzes/{quiz['id']}/attempts/{attempt}/retry")
    assert r.status_code == 201, r.text
    retry = r.json()
    assert retry["id"] != quiz["id"]
    assert retry["title"] == f"Retry: {quiz['title']}"
    assert retry["difficulty"] == "hard"
    assert [q["prompt"] for q in retry["questions"]] == ["Q1?", "Q2?"]
    assert [q["position"] for q in retry["questions"]] == [1, 2]
    assert len(llm.calls) == calls_before  # copied, no model call

    # The copy keeps its answer key: answering correctly scores full marks.
    result = client.post(
        f"{API}/quizzes/{retry['id']}/attempts", json={"answers": [0, 0]}
    ).json()
    assert result["score"] == 2
    assert result["questions"][0]["filename"] == "bio.pdf"

    # The original quiz and its attempt are untouched.
    original = client.get(f"{API}/quizzes/{quiz['id']}").json()
    assert len(original["questions"]) == 3 and len(original["attempts"]) == 1


def test_retry_of_a_retry_keeps_one_prefix(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_quiz(llm, 2)
    quiz = client.post(
        f"{API}/quizzes", json={"document_ids": [doc], "question_count": 2}
    ).json()
    first = client.post(
        f"{API}/quizzes/{quiz['id']}/attempts/{_attempt(client, quiz['id'], [1, 1])}/retry"
    ).json()
    second = client.post(
        f"{API}/quizzes/{first['id']}/attempts/{_attempt(client, first['id'], [1, 0])}/retry"
    ).json()
    assert second["title"] == f"Retry: {quiz['title']}"
    assert [q["prompt"] for q in second["questions"]] == ["Q0?"]


def test_retry_keeps_multiple_choice_answer_keys(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    llm.queue(
        questions=[
            {
                "type": "multiple",
                "question": "Which need oxygen?",
                "options": [
                    "Electron transport",
                    "Glycolysis",
                    "Aerobic respiration",
                    "Fermentation",
                ],
                "correct_indices": [0, 2],
                "source": "S1",
            }
        ]
    )
    quiz = client.post(
        f"{API}/quizzes",
        json={"document_ids": [doc], "question_types": ["multiple"]},
    ).json()
    retry = client.post(
        f"{API}/quizzes/{quiz['id']}/attempts/{_attempt(client, quiz['id'], [[0]])}/retry"
    ).json()
    assert retry["questions"][0]["kind"] == "multiple"
    result = client.post(
        f"{API}/quizzes/{retry['id']}/attempts", json={"answers": [[2, 0]]}
    ).json()
    assert result["score"] == 1 and result["questions"][0]["correct_indices"] == [0, 2]


def test_retry_with_nothing_missed_is_rejected(client, llm):
    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_quiz(llm, 2)
    quiz = client.post(
        f"{API}/quizzes", json={"document_ids": [doc], "question_count": 2}
    ).json()
    attempt = _attempt(client, quiz["id"], [0, 0])
    r = client.post(f"{API}/quizzes/{quiz['id']}/attempts/{attempt}/retry")
    assert r.status_code == 422 and "every answer was correct" in r.json()["detail"]


def test_retry_unknown_attempt_or_other_users_quiz(client, llm, db, other_user):
    from backend.models import Quiz

    doc = upload(client, CELLS).json()["document"]["id"]
    _queue_quiz(llm, 1)
    quiz = client.post(f"{API}/quizzes", json={"document_ids": [doc]}).json()
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        client.post(f"{API}/quizzes/{quiz['id']}/attempts/{missing}/retry").status_code
        == 404
    )

    theirs = Quiz(owner_id=other_user.id, title="theirs")
    db.add(theirs)
    db.commit()
    assert (
        client.post(f"{API}/quizzes/{theirs.id}/attempts/{missing}/retry").status_code
        == 404
    )
