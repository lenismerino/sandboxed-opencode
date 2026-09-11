"""Pure-Python Local Semantic Code Search & Vector Index using Local Embeddings.

Provides vector indexing and semantic similarity search across project source code
using local OpenAI-compatible embedding endpoints (e.g. nomic-embed-text in LM Studio or Ollama).
Requires zero external vector DB dependencies (pure standard library: sqlite3 + math).
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if len(vec_a) != len(vec_b):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


@dataclass
class CodeChunk:
    file_path: str
    chunk_index: int
    start_line: int
    end_line: int
    content: str
    vector: Optional[List[float]] = None


@dataclass
class SearchResult:
    file_path: str
    start_line: int
    end_line: int
    content: str
    score: float

    def format_snippet(self) -> str:
        return f"[{self.file_path}:{self.start_line}-{self.end_line}] (score: {self.score:.3f})\n{self.content.strip()}"


class LocalEmbeddingClient:
    """Client for local OpenAI-compatible embedding endpoints."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234/v1",
        model: str = "text-embedding-nomic-embed-text-v1.5",
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Fetch embedding vectors for a list of text strings."""
        if not texts:
            return []

        url = f"{self.base_url}/embeddings"
        payload = {"model": self.model, "input": texts}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("data", [])
                # Ensure sorted by index
                items.sort(key=lambda x: x.get("index", 0))
                return [item["embedding"] for item in items]
        except Exception as err:
            raise RuntimeError(f"Failed to fetch embeddings from {url}: {err}") from err

    def embed_query(self, query: str) -> List[float]:
        """Fetch embedding vector for a single query."""
        results = self.embed_texts([query])
        if not results:
            raise RuntimeError("Empty embedding response returned.")
        return results[0]


class SemanticCodeIndex:
    """SQLite-backed semantic code index for the active project."""

    def __init__(
        self,
        project_dir: str = ".",
        db_path: Optional[str] = None,
        embedding_client: Optional[LocalEmbeddingClient] = None,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.db_path = Path(db_path or self.project_dir / ".cache" / "semantic_index.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.client = embedding_client or LocalEmbeddingClient()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_path ON chunks(file_path)")
            conn.commit()

    def _chunk_file(self, file_path: Path, max_lines: int = 40, overlap: int = 10) -> List[CodeChunk]:
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return []

        chunks: List[CodeChunk] = []
        rel_path = str(file_path.resolve().relative_to(self.project_dir))
        total_lines = len(lines)
        if total_lines == 0:
            return chunks

        start = 0
        chunk_idx = 0
        while start < total_lines:
            end = min(start + max_lines, total_lines)
            chunk_content = "\n".join(lines[start:end])
            if chunk_content.strip():
                chunks.append(
                    CodeChunk(
                        file_path=rel_path,
                        chunk_index=chunk_idx,
                        start_line=start + 1,
                        end_line=end,
                        content=chunk_content,
                    )
                )
                chunk_idx += 1
            if end >= total_lines:
                break
            start += max_lines - overlap

        return chunks

    def index_project(
        self,
        extensions: Optional[List[str]] = None,
        max_files: int = 200,
        batch_size: int = 16,
    ) -> int:
        """Scan project files, chunk them, embed, and store in the SQLite index."""
        exts = extensions or [".py", ".md", ".sh", ".json", ".yml", ".yaml"]
        files_to_index: List[Path] = []

        ignore_dirs = {".git", ".venv", "__pycache__", ".cache", "temp", "node_modules"}
        for root, dirs, files in os.walk(self.project_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                p = Path(root) / file
                if p.suffix in exts and p.stat().st_size < 200000:
                    files_to_index.append(p)
                    if len(files_to_index) >= max_files:
                        break
            if len(files_to_index) >= max_files:
                break

        all_chunks: List[CodeChunk] = []
        for file_path in files_to_index:
            all_chunks.extend(self._chunk_file(file_path))

        if not all_chunks:
            return 0

        # Clear existing chunks
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM chunks")
            conn.commit()

        # Batch embed and insert
        indexed_count = 0
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]
            texts = [c.content for c in batch]
            try:
                embeddings = self.client.embed_texts(texts)
                with sqlite3.connect(self.db_path) as conn:
                    for chunk, emb in zip(batch, embeddings):
                        conn.execute(
                            """
                            INSERT INTO chunks (file_path, chunk_index, start_line, end_line, content, embedding_json)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                chunk.file_path,
                                chunk.chunk_index,
                                chunk.start_line,
                                chunk.end_line,
                                chunk.content,
                                json.dumps(emb),
                            ),
                        )
                    conn.commit()
                indexed_count += len(batch)
            except Exception as err:
                print(f"Warning: Failed to embed batch {i}: {err}")

        return indexed_count

    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Perform semantic similarity search against indexed code chunks."""
        try:
            query_vec = self.client.embed_query(query)
        except Exception as err:
            return [
                SearchResult(
                    file_path="error",
                    start_line=0,
                    end_line=0,
                    content=f"Error embedding query: {err}",
                    score=0.0,
                )
            ]

        results: List[SearchResult] = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT file_path, start_line, end_line, content, embedding_json FROM chunks")
            for row in cursor:
                file_path, start_line, end_line, content, emb_json = row
                try:
                    emb = json.loads(emb_json)
                    sim = _cosine_similarity(query_vec, emb)
                    results.append(
                        SearchResult(
                            file_path=file_path,
                            start_line=start_line,
                            end_line=end_line,
                            content=content,
                            score=sim,
                        )
                    )
                except Exception:
                    continue

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
