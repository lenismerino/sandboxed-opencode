# Recipe: Local Offline Semantic Code Search

This recipe details how `sandboxed-opencode` provides offline semantic code search using local embeddings without any external vector databases (such as Chroma, Pinecone, or Milvus) or cloud dependencies.

---

## 1. Overview & Architecture

When navigating medium-to-large codebases with local open-weights models (like Google Gemma 4 E4B), keyword search (`grep`) can miss conceptually related implementations. 

`sandboxed-opencode` includes an embedded semantic code search system implemented in `harness/embeddings.py`:
- **Local Embeddings**: Consumes embeddings directly from LM Studio (`/v1/embeddings`) or Ollama (`/api/embeddings`) using standard local models (e.g. `text-embedding-nomic-embed-text-v1.5` or `bge-small-en-v1.5`).
- **Zero Heavy Dependencies**: Built entirely on the Python standard library (`sqlite3`, `math`, `urllib.request`).
- **SQLite Vector Store**: Indexes chunks into a persistent SQLite table (`.cache/semantic_index.db`) with file timestamps for efficient incremental re-indexing.
- **Fast Cosine Similarity**: In-memory vectorized dot-product ranking across chunk embeddings.
- **100% Host-Isolated**: Zero telemetry, zero cloud calls; embeddings never leave your local machine or LAN.

---

## 2. Setting Up an Embedding Model

### Option A: LM Studio
1. In LM Studio, download a compact embedding model:
   - `nomic-ai/nomic-embed-text-v1.5-GGUF` (Recommended, 768 dimensions)
   - or `BAAI/bge-small-en-v1.5-GGUF` (384 dimensions)
2. Load the embedding model into LM Studio.
3. LM Studio automatically serves embeddings at `http://<LLM_HOST>:<LLM_PORT>/v1/embeddings`.

### Option B: Ollama
Pull your preferred embedding model:
```bash
ollama pull nomic-embed-text
```

Ensure `.env` contains:
```bash
EMBEDDING_MODEL_NAME=text-embedding-nomic-embed-text-v1.5
```

---

## 3. How the Agent Uses Semantic Search

The `semantic_search` tool is registered in both the standalone tool registry (`tools/registry.py`) and the Conductor MCP bridge (`scripts/mcp-bridge.py`).

### Agent Tool Call Signature
```json
{
  "name": "semantic_search",
  "arguments": {
    "query": "Where is the exponential backoff retry logic implemented?",
    "top_k": 3
  }
}
```

### Agent Tool Response Example
```
Found 3 semantic matches:
1. harness/model_client.py:45-72 (Score: 0.8842)
   for attempt in range(self.max_retries):
       try:
           ...
           time.sleep(2 ** attempt)
2. harness/model_client.py:15-38 (Score: 0.7410)
   class ModelClient:
       ...
```

---

## 4. Programmatic Usage in the Harness

You can also use the semantic index directly within custom scripts or harness workflows:

```python
from pathlib import Path
from harness.embeddings import LocalEmbeddingClient, SemanticCodeIndex

# 1. Initialize local embedding client
client = LocalEmbeddingClient(
    base_url="http://192.168.1.3:1234/v1",
    model="text-embedding-nomic-embed-text-v1.5"
)

# 2. Point index to the project directory
project_path = Path("/home/agent/projects")
index = SemanticCodeIndex(
    project_dir=project_path,
    embedding_client=client,
    db_path=project_path / ".cache" / "semantic_index.db"
)

# 3. Index code files incrementally
indexed_count = index.index_project()
print(f"Indexed {indexed_count} chunks.")

# 4. Query concepts
results = index.query("How are model profiles validated?", top_k=5)
for r in results:
    print(f"[{r['score']:.3f}] {r['file_path']}:{r['start_line']}-{r['end_line']}")
```

---

## 5. Verification & Testing

Verify that semantic indexing and query operations pass unit tests:

```bash
python3 -m unittest harness.harness_test.TestSemanticEmbeddings -v
```

Output:
```
test_cosine_similarity (harness.harness_test.TestSemanticEmbeddings.test_cosine_similarity) ... ok
test_semantic_indexing_and_query (harness.harness_test.TestSemanticEmbeddings.test_semantic_indexing_and_query) ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.005s

OK
```
