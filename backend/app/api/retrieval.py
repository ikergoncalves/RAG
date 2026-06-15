"""Retrieval endpoint (internal / debug).

``POST /retrieve`` runs the hybrid retrieval + re-ranking pipeline directly and
returns the matching chunks with their scores and citation metadata. It is meant
for debugging and for inspecting retrieval quality in isolation from generation.
"""

from fastapi import APIRouter, HTTPException, status

from app.schemas.retrieval import RetrievedChunk, RetrieveRequest, RetrieveResponse
from app.services.retrieval import get_default_retrieval_service

router = APIRouter(tags=["retrieval"])


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(request: RetrieveRequest) -> RetrieveResponse:
    """Return the top-k chunks for a query via hybrid search + re-ranking.

    Returns ``503`` when a required backend is unavailable (e.g. no embedding
    provider configured because ``OPENAI_API_KEY`` is missing).
    """
    filters = {"document_ids": request.document_ids} if request.document_ids else None
    try:
        results = await get_default_retrieval_service().retrieve(
            request.query, top_k=request.top_k, filters=filters
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return RetrieveResponse(
        query=request.query,
        results=[RetrievedChunk(**result) for result in results],
    )
