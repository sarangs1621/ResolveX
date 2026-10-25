"""RAG Service: BM25 search over markdown knowledge base chunks with dynamic reload."""

import math
import re
from collections import Counter
from pathlib import Path


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def load_chunks(kb_dir: Path = None, max_len: int = 1200) -> list[dict]:
    if kb_dir is None:
        kb_dir = Path(__file__).parent.parent / "kb"
    chunks = []
    if not kb_dir.exists():
        return chunks
    for f in sorted(kb_dir.glob("*.md")):
        buf = ""
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for para in content.split("\n\n"):
            if len(buf) + len(para) > max_len and buf:
                chunks.append({"source": f.name, "text": buf.strip()})
                buf = ""
            buf += para + "\n\n"
        if buf.strip():
            chunks.append({"source": f.name, "text": buf.strip()})
    return chunks


class BM25:
    def __init__(self, docs: list[dict], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d["text"])) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avgdl = (sum(self.lens) / len(self.lens)) if docs else 1
        self.df: Counter = Counter()
        for tf in self.tfs:
            self.df.update(tf.keys())
        self.n = len(docs)

    def search(self, query: str, k: int = 4) -> list[dict]:
        scores = []
        for i, tf in enumerate(self.tfs):
            s = 0.0
            for t in tokenize(query):
                if t not in tf:
                    continue
                idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                norm = tf[t] + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avgdl)
                s += idf * tf[t] * (self.k1 + 1) / norm
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        return [{**self.docs[i], "score": round(s, 2)} for s, i in scores[:k]]


class KnowledgeBaseService:
    def __init__(self, kb_dir: Path):
        self.kb_dir = kb_dir
        self.reload()

    def reload(self) -> int:
        chunks = load_chunks(self.kb_dir)
        self.index = BM25(chunks)
        return len(chunks)

    def search(self, query: str, k: int = 4) -> list[dict]:
        return self.index.search(query, k=k)

    def list_articles(self) -> list[dict]:
        if not self.kb_dir.exists():
            return []
        articles = []
        for f in sorted(self.kb_dir.glob("*.md")):
            articles.append({
                "filename": f.name,
                "title": f.name.replace(".md", "").replace("_", " ").title(),
                "size_bytes": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
        return articles

    def get_article(self, filename: str) -> str:
        filepath = self.kb_dir / filename
        if not filepath.exists() or not filepath.is_file():
            raise FileNotFoundError(f"Article {filename} not found")
        return filepath.read_text(encoding="utf-8")

    def save_article(self, filename: str, content: str) -> dict:
        if not filename.endswith(".md"):
            filename += ".md"
        # Sanitize filename
        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
        filepath = self.kb_dir / safe_name
        filepath.write_text(content, encoding="utf-8")
        chunk_count = self.reload()
        return {"filename": safe_name, "chunk_count": chunk_count, "saved": True}

    def delete_article(self, filename: str) -> bool:
        filepath = self.kb_dir / filename
        if filepath.exists() and filepath.is_file():
            filepath.unlink()
            self.reload()
            return True
        return False
