import re
from typing import List, Dict, Any
from loguru import logger


def evaluate_hallucination(response_text: str, source_texts: List[str]) -> float:
    """
    Measures the level of potential hallucination in the response text.
    Returns a score from 0.0 (high hallucination / no overlap) to 1.0 (strict alignment / complete overlap).
    Checks keyword overlap and segment containment between response and retrieved source texts.
    """
    if not response_text or not source_texts:
        return 0.0

    # Normalize response text to words
    response_words = set(re.findall(r"\w+", response_text.lower()))
    # Remove common filler words (stop words) to keep meaningful keywords
    stop_words = {
        "and", "the", "a", "of", "to", "in", "is", "for", "that", "this", "it", "on", "with",
        "as", "by", "an", "at", "from", "are", "be", "was", "were", "or", "which", "about"
    }
    keywords = response_words - stop_words
    if not keywords:
        return 1.0

    # Collate all source words
    source_words = set()
    for text in source_texts:
        source_words.update(re.findall(r"\w+", text.lower()))

    # Calculate percentage of response keywords found in sources
    overlap = keywords.intersection(source_words)
    hallucination_score = len(overlap) / len(keywords)
    logger.bind(
        total_keywords=len(keywords),
        overlap_keywords=len(overlap),
        alignment_score=hallucination_score
    ).debug("Hallucination check complete.")

    return round(hallucination_score, 4)


def verify_citations(response_text: str, retrieved_chunks: List[Dict[str, Any]]) -> bool:
    """
    Asserts that every citation in the response (e.g. [1], [2], or document names) matches
    a retrieved document chunk. Returns True if all citations are valid, False otherwise.
    """
    if not response_text:
        return True

    # 1. Parse citation indices from response text (e.g. [1], [2])
    citation_indices = [int(num) for num in re.findall(r"\[(\d+)\]", response_text)]
    if not citation_indices:
        return True

    # Assert indices map to available chunk offsets (1-indexed)
    num_chunks = len(retrieved_chunks)
    for idx in citation_indices:
        if idx < 1 or idx > num_chunks:
            logger.warning(f"Citation mismatch: Response cited [{idx}], but only {num_chunks} chunks were retrieved.")
            return False

    return True


def evaluate_retrieval_accuracy(query: str, retrieved_chunks: List[Dict[str, Any]], similarity_threshold: float = 0.5) -> float:
    """
    Measures the precision of retrieval by calculating the percentage of retrieved chunks
    that have a similarity score above the specified threshold.
    Returns a score from 0.0 (poor retrieval quality) to 1.0 (high retrieval relevance).
    """
    if not retrieved_chunks:
        return 0.0

    relevant_count = 0
    for chunk in retrieved_chunks:
        # Check similarity score field
        score = chunk.get("similarity_score")
        if score is None:
            # Check secondary field
            score = chunk.get("score", 1.0)
        
        if score >= similarity_threshold:
            relevant_count += 1

    precision = relevant_count / len(retrieved_chunks)
    logger.bind(
        total_chunks=len(retrieved_chunks),
        relevant_chunks=relevant_count,
        precision=precision
    ).debug("Retrieval accuracy check complete.")

    return round(precision, 4)
