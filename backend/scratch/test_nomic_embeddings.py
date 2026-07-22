import asyncio
from app.rag.embeddings import EmbeddingService

def main():
    print("Initializing EmbeddingService...")
    service = EmbeddingService()

    print("\n--- Testing Single Query Embedding ---")
    query = "What is the net profit of Arvind Limited in 2025?"
    single_emb = service.get_embedding(query)
    print(f"Generated single embedding successfully!")
    print(f"Embedding type: {type(single_emb)}")
    print(f"Embedding length: {len(single_emb)}")
    print(f"Sample values (first 5): {single_emb[:5]}")
    
    assert len(single_emb) == 768, f"Expected 768 dimensions, got {len(single_emb)}"

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
        assert len(emb) == 768, f"Expected 768 dimensions, got {len(emb)}"

    print("\nStandalone verification passed successfully! All embedding dimensions are exactly 768.")

if __name__ == "__main__":
    main()
