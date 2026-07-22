"""
scratch/test_bge_m3_embeddings.py

Standalone verification script for the BGE-M3 embedding service.
Renamed from test_nomic_embeddings.py after migrating from nomic-embed-text (768-dim)
to bge-m3 (1024-dim) via Ollama.

Prerequisites:
    - Ollama running at the configured OLLAMA_BASE_URL
    - BGE-M3 pulled: `ollama pull bge-m3`
"""
import asyncio
from app.rag.embeddings import EmbeddingService

def main():
    print("Initializing EmbeddingService (BGE-M3 via Ollama)...")
    service = EmbeddingService()

    print("\n--- Testing Single Query Embedding ---")
    query = "What is the net profit of Arvind Limited in 2025?"
    single_emb = service.get_embedding(query)
    print(f"Generated single embedding successfully!")
    print(f"Embedding type: {type(single_emb)}")
    print(f"Embedding length: {len(single_emb)}")
    print(f"Sample values (first 5): {single_emb[:5]}")
    
    # BGE-M3 produces 1024-dimensional vectors
    assert len(single_emb) == 1024, f"Expected 1024 dimensions (BGE-M3), got {len(single_emb)}"

    print("\n--- Testing Batch Chunks Embedding ---")
    chunks = [
        "Revenue from operations increased by 10% year-on-year.",
        "The EBITDA margin for the textile segment was 12.5%.",
        "Arvind Limited's retail segment registered strong growth."
    ]
    batch_embs = service.get_embeddings(chunks)
    print(f"Generated batch embeddings successfully!")
    print(f"Batch size: {len(batch_embs)}")
    for i, emb in enumerate(batch_embs):
        print(f"Chunk {i} embedding length: {len(emb)}")
        assert len(emb) == 1024, f"Expected 1024 dimensions (BGE-M3), got {len(emb)}"

    print("\nStandalone verification passed successfully! All embedding dimensions are exactly 1024 (BGE-M3).")

if __name__ == "__main__":
    main()
