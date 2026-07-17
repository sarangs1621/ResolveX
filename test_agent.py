"""Smallest checks that fail if the non-LLM logic breaks. Run: python test_agent.py"""

from main import BM25, load_chunks, should_escalate, exec_tool


def run():
    chunks = load_chunks()
    assert len(chunks) >= 3, "KB should produce chunks"
    assert all(c["text"] and c["source"].endswith(".md") for c in chunks)

    index = BM25(chunks)
    hits = index.search("how do I get a refund")
    assert hits, "refund query should hit the KB"
    assert hits[0]["source"] == "billing.md", f"expected billing.md first, got {hits[0]['source']}"
    assert index.search("zqxwv nonsense gibberish") == []

    assert should_escalate(0.3) and not should_escalate(0.9)
    assert should_escalate(0.69) and not should_escalate(0.7)

    assert "billing" in exec_tool("search_kb", {"query": "refund policy"})
    assert "No knowledge base results" in exec_tool("search_kb", {"query": "zqxwv"})

    print("all checks passed")


if __name__ == "__main__":
    run()
