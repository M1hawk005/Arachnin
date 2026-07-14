import pytest

from app.services.extraction import chunk_text, extract_document


def test_chunk_text_preserves_overlap_and_order():
    text = " ".join(f"word-{index}" for index in range(620))

    chunks = chunk_text(text, chunk_size=250, overlap=40)

    assert [chunk["index"] for chunk in chunks] == [0, 1, 2]
    assert chunks[0]["word_count"] == 250
    assert chunks[0]["text"].split()[-40:] == chunks[1]["text"].split()[:40]
    assert chunks[-1]["text"].endswith("word-619")


def test_chunk_text_handles_empty_input():
    assert chunk_text("", chunk_size=500, overlap=50) == []


def test_extract_document_returns_rag_ready_metadata():
    body = " ".join(
        "Arachnin turns public articles into reliable retrieval context." for _ in range(12)
    )
    html = f"""
    <html lang="en-AU">
      <head>
        <title>Fallback title</title>
        <meta property="og:title" content="Production RAG ingestion">
        <meta name="description" content="A practical ingestion guide">
        <meta name="author" content="A. Engineer">
      </head>
      <body><main><article><p>{body}</p></article></main></body>
    </html>
    """

    document = extract_document(html, chunk_size=200, overlap=20)

    assert document.title == "Production RAG ingestion"
    assert document.description == "A practical ingestion guide"
    assert document.author == "A. Engineer"
    assert document.language == "en"
    assert document.word_count > 20
    assert len(document.content_hash) == 64
    assert document.chunks[0]["index"] == 0


def test_extract_document_falls_back_to_visible_text(monkeypatch):
    monkeypatch.setattr("app.services.extraction.trafilatura.extract", lambda *args, **kwargs: None)
    visible = " ".join("useful sentence for retrieval" for _ in range(10))
    html = f"<html><head><title>Visible</title><script>ignore me</script></head><body>{visible}</body></html>"

    document = extract_document(html, chunk_size=200, overlap=10)

    assert "ignore me" not in document.content
    assert document.title == "Visible"


def test_extract_document_rejects_empty_pages(monkeypatch):
    monkeypatch.setattr(
        "app.services.extraction.trafilatura.extract", lambda *args, **kwargs: "short"
    )
    with pytest.raises(ValueError, match="enough readable content"):
        extract_document("<p>short</p>", chunk_size=200, overlap=10)
