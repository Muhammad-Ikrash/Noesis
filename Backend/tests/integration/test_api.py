import uuid

from sqlalchemy import select

from backend.models import Document, DocumentChunk, MessageSource
from backend.models.enums import DocumentStatus
from backend.services.ingestion import ingest_document
from backend.services.storage import FileStorage
from tests.fakes import FakeEmbedder
from tests.pdfs import make_pdf

API = "/api/v1"
BIO = [
    "Photosynthesis happens in chloroplasts using chlorophyll.",
    "Mitochondria produce ATP by respiration.",
]
HISTORY = ["The French revolution began in 1789 with the storming of the Bastille."]


def upload(client, pages, name="bio.pdf"):
    return client.post(
        f"{API}/documents", files={"file": (name, make_pdf(pages), "application/pdf")}
    )


def new_chat(client, doc_ids, scope="session"):
    r = client.post(
        f"{API}/conversations", json={"document_ids": doc_ids, "retrieval_scope": scope}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def ask(client, conv_id, question, mode="basic", scope=None):
    body = {"question": question, "mode": mode} | (
        {"retrieval_scope": scope} if scope else {}
    )
    return client.post(f"{API}/conversations/{conv_id}/messages", json=body)


# --- ingestion -----------------------------------------------------------------


def test_upload_ingests_with_page_provenance(client, db):
    r = upload(client, BIO, name="../../etc/Biology Notes.pdf")
    assert r.status_code == 201
    doc_id = r.json()["document"]["id"]

    detail = client.get(f"{API}/documents/{doc_id}").json()
    assert detail["status"] == "completed" and detail["page_count"] == 2
    assert detail["filename"] == "Biology Notes.pdf"
    assert "storage_key" not in detail

    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == uuid.UUID(doc_id))
        .order_by(DocumentChunk.chunk_index)
    ).all()
    assert {c.page_number for c in chunks} == {1, 2}
    assert any("ATP" in c.text and c.page_number == 2 for c in chunks)
    assert all(
        len(c.embedding) == 1024 and c.embedding_model == "fake-embedder"
        for c in chunks
    )


def test_duplicate_upload_reuses_document(client):
    first = upload(client, BIO).json()["document"]["id"]
    again = upload(client, BIO)
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["document"]["id"] == first


def test_rejects_non_pdf_and_oversized(client):
    fake = client.post(
        f"{API}/documents",
        files={"file": ("x.pdf", b"PK\x03\x04zip", "application/pdf")},
    )
    assert fake.status_code == 415
    wrong_ext = client.post(
        f"{API}/documents", files={"file": ("x.txt", make_pdf(["a"]), "text/plain")}
    )
    assert wrong_ext.status_code == 415
    big = client.post(
        f"{API}/documents",
        files={
            "file": ("big.pdf", b"%PDF-" + b"0" * (2 * 1024 * 1024), "application/pdf")
        },
    )
    assert big.status_code == 413


def test_image_only_pdf_fails_clearly_and_reports_ocr_pages(client):
    doc_id = upload(client, [None, None], name="scan.pdf").json()["document"]["id"]
    detail = client.get(f"{API}/documents/{doc_id}").json()
    assert detail["status"] == "failed"
    assert "OCR is not enabled" in detail["error_message"]
    assert detail["ocr_pages"] == [1, 2]


def test_corrupt_pdf_fails(client):
    r = client.post(
        f"{API}/documents",
        files={"file": ("bad.pdf", b"%PDF-1.4 broken", "application/pdf")},
    )
    assert (
        client.get(f"{API}/documents/{r.json()['document']['id']}").json()["status"]
        == "failed"
    )


def test_embedding_dimension_mismatch_fails_ingestion(
    session_factory, settings, db, client
):
    doc_id = upload(client, BIO).json()["document"]["id"]
    doc = db.get(Document, uuid.UUID(doc_id))
    doc.status = DocumentStatus.PENDING
    db.commit()
    ingest_document(
        doc.id,
        session_factory=session_factory,
        storage=FileStorage(settings.storage_dir),
        embedder=FakeEmbedder(output_dimension=384),
        settings=settings,
    )
    db.refresh(doc)
    assert (
        doc.status is DocumentStatus.FAILED
        and "dimension mismatch" in doc.error_message
    )
    assert (
        db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        is None
    )


# --- retrieval scope -----------------------------------------------------------


def test_session_scope_only_searches_attached_pdfs(client):
    bio = upload(client, BIO).json()["document"]["id"]
    upload(client, HISTORY, name="history.pdf")
    conv = new_chat(client, [bio])
    body = ask(
        client, conv, "When did the French revolution storming of the Bastille happen?"
    ).json()
    assert {r["filename"] for r in body["retrieved"]} == {"bio.pdf"}
    assert body["searched_document_count"] == 1


def test_library_scope_searches_all_owned_pdfs(client):
    bio = upload(client, BIO).json()["document"]["id"]
    upload(client, HISTORY, name="history.pdf")
    conv = new_chat(client, [bio])
    body = ask(client, conv, "French revolution Bastille 1789", scope="library").json()
    assert body["retrieved"][0]["filename"] == "history.pdf"
    assert body["sources"][0]["filename"] == "history.pdf"
    # The slider value is saved on the chat.
    assert (
        client.get(f"{API}/conversations/{conv}").json()["retrieval_scope"] == "library"
    )


def test_default_scope_comes_from_user_settings(client):
    assert (
        client.put(
            f"{API}/settings", json={"default_retrieval_scope": "library"}
        ).status_code
        == 200
    )
    conv = client.post(f"{API}/conversations", json={}).json()
    assert conv["retrieval_scope"] == "library"


def test_basic_mode_without_sources_does_not_call_llm(client, llm):
    conv = new_chat(client, [])
    body = ask(client, conv, "What is ATP?").json()
    assert body["answer_status"] == "insufficient_context" and body["sources"] == []
    assert llm.calls == []


def test_min_score_drops_unrelated_chunks(client, llm, settings):
    doc = upload(client, BIO).json()["document"]["id"]
    conv = new_chat(client, [doc])
    settings.retrieval_min_score = 0.9  # nothing in BIO is that close to this question
    body = ask(client, conv, "When did the French revolution begin?").json()
    assert body["answer_status"] == "insufficient_context" and body["retrieved"] == []
    assert llm.calls == []


# --- ownership -----------------------------------------------------------------


def _foreign_document(db, other_user, storage, embedder) -> Document:
    key = storage.new_key()
    storage.save(key, make_pdf(["secret"]))
    doc = Document(
        owner_id=other_user.id,
        filename="secret.pdf",
        storage_key=key,
        sha256="x" * 64,
        size_bytes=1,
        mime_type="application/pdf",
        status=DocumentStatus.COMPLETED,
    )
    db.add(doc)
    db.flush()
    db.add(
        DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            page_number=1,
            text="French revolution Bastille 1789",
            embedding=embedder.embed_documents(["French revolution Bastille 1789"])[0],
            embedding_model="fake-embedder",
        )
    )
    db.commit()
    return doc


def test_other_users_documents_are_invisible(client, db, other_user, storage, embedder):
    foreign = _foreign_document(db, other_user, storage, embedder)
    assert client.get(f"{API}/documents/{foreign.id}").status_code == 404
    assert client.delete(f"{API}/documents/{foreign.id}").status_code == 404
    assert (
        client.post(
            f"{API}/conversations", json={"document_ids": [str(foreign.id)]}
        ).status_code
        == 404
    )

    conv = new_chat(client, [])
    body = ask(client, conv, "French revolution Bastille 1789", scope="library").json()
    assert all(r["filename"] != "secret.pdf" for r in body["retrieved"])
    patch = client.patch(
        f"{API}/conversations/{conv}", json={"document_ids": [str(foreign.id)]}
    )
    assert patch.status_code == 404


def test_other_users_conversations_are_invisible(client, db, other_user):
    from backend.models import Conversation

    conv = Conversation(owner_id=other_user.id, title="theirs")
    db.add(conv)
    db.commit()
    assert client.get(f"{API}/conversations/{conv.id}").status_code == 404
    assert ask(client, conv.id, "hi").status_code == 404
    assert client.delete(f"{API}/conversations/{conv.id}").status_code == 404
    assert all(
        c["id"] != str(conv.id) for c in client.get(f"{API}/conversations").json()
    )


# --- conversations -------------------------------------------------------------


def test_follow_up_uses_bounded_history_and_retrieves_again(
    client, llm, embedder, settings
):
    bio = upload(client, BIO).json()["document"]["id"]
    conv = new_chat(client, [bio])
    for q in [
        "What do mitochondria produce?",
        "And chloroplasts?",
        "Tell me more",
        "why?",
    ]:
        assert ask(client, conv, q).status_code == 200

    assert len(embedder.queries) == 4  # retrieval on every turn
    assert "Tell me more" in embedder.queries[-1] and embedder.queries[-1].endswith(
        "why?"
    )
    last_call = llm.calls[-1]
    history = last_call[1:-1]
    assert len(history) == settings.history_max_messages
    assert all("<source" not in m.content for m in history)

    detail = client.get(f"{API}/conversations/{conv}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"] * 4
    assert detail["title"] == "What do mitochondria produce?"
    assert detail["messages"][1]["sources"][0]["page_number"] in (1, 2)


def test_extensive_mode_returns_supplementary_and_citations(client, llm):
    bio = upload(client, BIO).json()["document"]["id"]
    conv = new_chat(client, [bio])
    llm.queue(
        answer_status="answered",
        answer="ATP comes from mitochondria [S1].",
        supplementary="ATP is like a rechargeable battery.",
        clarification_question=None,
        citations=[{"source": "S1", "quote": "Mitochondria produce ATP"}],
    )
    body = ask(client, conv, "Mitochondria ATP?", mode="extensive").json()
    assert body["mode"] == "extensive" and body["supplementary"].startswith(
        "ATP is like"
    )
    assert body["answer"] == "ATP comes from mitochondria [1]."
    assert (
        body["sources"][0]["filename"] == "bio.pdf"
        and body["sources"][0]["page_number"] == 2
    )


def test_invalid_mode_rejected(client):
    conv = new_chat(client, [])
    assert ask(client, conv, "hi", mode="be-creative").status_code == 422


# --- deletion ------------------------------------------------------------------


def test_delete_document_keeps_citation_snapshot(client, db, storage):
    bio = upload(client, BIO).json()["document"]["id"]
    conv = new_chat(client, [bio])
    ask(client, conv, "mitochondria ATP")
    key = db.get(Document, uuid.UUID(bio)).storage_key

    assert client.delete(f"{API}/documents/{bio}").status_code == 204
    assert not storage.exists(key)
    assert (
        db.scalar(
            select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(bio))
        )
        is None
    )

    detail = client.get(f"{API}/conversations/{conv}").json()
    assert detail["documents"] == []
    source = detail["messages"][1]["sources"][0]
    assert (
        source["filename"] == "bio.pdf"
        and source["document_id"] is None
        and source["chunk_id"] is None
    )
    assert db.scalar(select(MessageSource)).page_number in (1, 2)


def test_missing_file_is_flagged_not_deleted(client, db, storage):
    from backend.services.document_service import mark_missing_files

    bio = upload(client, BIO).json()["document"]["id"]
    storage.delete(db.get(Document, uuid.UUID(bio)).storage_key)
    assert mark_missing_files(db, storage) == 1
    assert client.get(f"{API}/documents/{bio}").json()["status"] == "missing"
    assert (
        db.scalar(
            select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(bio))
        )
        is not None
    )


def test_document_file_is_served_to_owner_only(
    client, db, other_user, storage, embedder
):
    bio = upload(client, BIO).json()["document"]["id"]
    r = client.get(f"{API}/documents/{bio}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert (
        r.content.startswith(b"%PDF-") and "inline" in r.headers["content-disposition"]
    )
    foreign = _foreign_document(db, other_user, storage, embedder)
    assert client.get(f"{API}/documents/{foreign.id}/file").status_code == 404
