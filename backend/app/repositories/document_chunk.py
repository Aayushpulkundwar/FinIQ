import uuid
from typing import List, Tuple, Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document_chunk import DocumentChunk
from app.models.document import Document, DocumentType
from app.repositories.base import BaseRepository


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    """
    Repository for PostgreSQL database operations on the DocumentChunk model.
    Handles data access for vector chunk records and executes cosine similarity searches.
    """
    def __init__(self, db: AsyncSession):
        super().__init__(DocumentChunk, db)

    async def search_similarity(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: Optional[float] = None,
        company_id: Optional[uuid.UUID] = None,
        document_type: Optional[DocumentType] = None,
        fiscal_year: Optional[int] = None,
        page_number: Optional[int] = None,
        query_text: Optional[str] = None,
        include_mock: bool = False,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Executes a pgvector cosine similarity search, applies optional metadata filters,
        and optionally filters by a minimum similarity threshold.
        Returns:
            List[Tuple[DocumentChunk, float]]: Pairs of (DocumentChunk, similarity_score).
        """
        # Check if the query embedding is a mock/zero vector (local dev mock mode)
        is_zero_vector = all(v == 0.0 for v in query_embedding)

        if is_zero_vector:
            import re
            stmt = select(DocumentChunk).options(selectinload(DocumentChunk.document).selectinload(Document.company))
            filters = []
            if not include_mock:
                filters.append(DocumentChunk.is_mock_embedding == False)
            if company_id is not None:
                filters.append(DocumentChunk.company_id == company_id)
            if document_type is not None:
                filters.append(DocumentChunk.document_type == document_type)
            if fiscal_year is not None:
                filters.append(DocumentChunk.fiscal_year == fiscal_year)
            if page_number is not None:
                filters.append(DocumentChunk.page_number == page_number)
            if filters:
                stmt = stmt.where(and_(*filters))

            result = await self.db.execute(stmt)
            chunks = [row[0] for row in result.all()]

            scored_chunks = []
            if query_text:
                # Basic case-insensitive word matching frequency score
                query_words = [w.lower() for w in re.findall(r'\b\w{3,}\b', query_text.lower())]
                for chunk in chunks:
                    text_lower = chunk.chunk_text.lower()
                    score = sum(text_lower.count(word) for word in query_words)
                    # Convert to normalized score: [0.5, 1.0] if matched
                    sim_score = min(0.5 + 0.05 * score, 1.0) if score > 0 else 0.5
                    scored_chunks.append((chunk, sim_score))
                scored_chunks.sort(key=lambda x: x[1], reverse=True)
            else:
                scored_chunks = [(c, 0.5) for c in chunks]

            return scored_chunks[:top_k]

        # Cosine distance expression using pgvector operator
        distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding)

        # Similarity score = 1.0 - cosine_distance
        similarity_expr = (1.0 - distance_expr).label("similarity")

        # Build select query returning the entity and the score
        stmt = select(DocumentChunk, similarity_expr).options(selectinload(DocumentChunk.document).selectinload(Document.company))

        # Apply metadata filters
        filters = []
        if not include_mock:
            filters.append(DocumentChunk.is_mock_embedding == False)
        if company_id is not None:
            filters.append(DocumentChunk.company_id == company_id)
        if document_type is not None:
            filters.append(DocumentChunk.document_type == document_type)
        if fiscal_year is not None:
            filters.append(DocumentChunk.fiscal_year == fiscal_year)
        if page_number is not None:
            filters.append(DocumentChunk.page_number == page_number)

        # Apply minimum similarity threshold filtering at database query level
        if min_similarity is not None:
            filters.append(distance_expr <= (1.0 - min_similarity))

        if filters:
            stmt = stmt.where(and_(*filters))

        # Order by distance (closest first) and limit results count
        stmt = stmt.order_by(distance_expr.asc()).limit(top_k)

        # Execute transaction
        result = await self.db.execute(stmt)

        # Map results to tuples of (DocumentChunk, float)
        return [(row[0], float(row[1])) for row in result.all()]

    async def search_keyword(
        self,
        query_text: str,
        top_k: int = 5,
        company_id: Optional[uuid.UUID] = None,
        document_type: Optional[DocumentType] = None,
        fiscal_year: Optional[int] = None,
        page_number: Optional[int] = None,
        include_mock: bool = False,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Executes a PostgreSQL Full-Text Search rank query.
        """
        from sqlalchemy import func
        if not query_text or not query_text.strip():
            return []

        fts_filter = func.to_tsvector('english', DocumentChunk.chunk_text).op('@@')(func.plainto_tsquery('english', query_text))
        rank_expr = func.ts_rank_cd(func.to_tsvector('english', DocumentChunk.chunk_text), func.plainto_tsquery('english', query_text)).label("rank")

        stmt = select(DocumentChunk, rank_expr).options(selectinload(DocumentChunk.document).selectinload(Document.company))

        filters = [fts_filter]
        if not include_mock:
            filters.append(DocumentChunk.is_mock_embedding == False)
        if company_id is not None:
            filters.append(DocumentChunk.company_id == company_id)
        if document_type is not None:
            filters.append(DocumentChunk.document_type == document_type)
        if fiscal_year is not None:
            filters.append(DocumentChunk.fiscal_year == fiscal_year)
        if page_number is not None:
            filters.append(DocumentChunk.page_number == page_number)

        stmt = stmt.where(and_(*filters)).order_by(rank_expr.desc()).limit(top_k)
        result = await self.db.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]
