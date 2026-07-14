"""HTML extraction and deterministic, token-budget-friendly chunking."""

import hashlib
import re
from dataclasses import dataclass

import trafilatura
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ExtractedDocument:
    title: str | None
    description: str | None
    site_name: str | None
    author: str | None
    published_at: str | None
    language: str | None
    content: str
    content_hash: str
    word_count: int
    chunks: list[dict]


def _meta(soup: BeautifulSoup, *keys: str) -> str | None:
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return None


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[dict]:
    """Split on words with deterministic overlap and stable indexes."""
    words = text.split()
    if not words:
        return []

    chunks: list[dict] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        chunks.append(
            {"index": len(chunks), "text": " ".join(chunk_words), "word_count": len(chunk_words)}
        )
        if end == len(words):
            break
        start = end - overlap
    return chunks


def extract_document(html: str, chunk_size: int, overlap: int) -> ExtractedDocument:
    soup = BeautifulSoup(html, "html.parser")
    content = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        include_links=False,
        favor_precision=True,
    )

    if not content:
        for node in soup(["script", "style", "nav", "footer", "form", "noscript"]):
            node.decompose()
        content = soup.get_text(separator=" ", strip=True)

    content = re.sub(r"[ \t]+", " ", content or "")
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    if len(content.split()) < 20:
        raise ValueError("The page did not contain enough readable content.")

    title = _meta(soup, "og:title", "twitter:title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()

    language = soup.html.get("lang") if soup.html else None
    words = content.split()
    return ExtractedDocument(
        title=title,
        description=_meta(soup, "og:description", "description", "twitter:description"),
        site_name=_meta(soup, "og:site_name"),
        author=_meta(soup, "author", "article:author"),
        published_at=_meta(soup, "article:published_time", "date", "datePublished"),
        language=str(language).split("-")[0].lower() if language else None,
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        word_count=len(words),
        chunks=chunk_text(content, chunk_size, overlap),
    )
