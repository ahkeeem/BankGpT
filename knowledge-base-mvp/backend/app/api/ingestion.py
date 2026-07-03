"""
Document ingestion API routes.
POST /api/v1/ingestion/upload — upload PDF
POST /api/v1/ingestion/url — ingest web page
GET  /api/v1/ingestion/documents — list documents by org
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])


class UrlIngestionRequest(BaseModel):
    url: str
    org_id: str


class DocumentResponse(BaseModel):
    document_id: str
    name: str
    type: str
    status: str
    chunk_count: int = 0
    source_url: str = ""
    detail: str = ""


@router.post("/upload", response_model=DocumentResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    org_id: str = Form(...),
):
    """
    Upload and ingest a PDF document.
    Extracts text, chunks it, generates embeddings, and indexes to vector store.
    """
    # Import here to avoid circular imports; services are set at startup
    from app.main import document_service

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Max 50MB
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    try:
        result = await document_service.ingest_pdf(
            file_bytes=file_bytes,
            filename=file.filename,
            organization_id=org_id,
        )
        return DocumentResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/url", response_model=DocumentResponse)
async def ingest_url(request: UrlIngestionRequest):
    """
    Ingest a web page by URL.
    Scrapes content, chunks it, generates embeddings, and indexes to vector store.
    """
    from app.main import document_service

    try:
        result = await document_service.ingest_url(
            url=request.url,
            organization_id=request.org_id,
        )
        return DocumentResponse(**result)
    except Exception as e:
        error_msg = str(e)
        if "httpx" in type(e).__module__:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {error_msg}")

        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.get("/documents")
async def list_documents(org_id: str):
    """
    List all documents for a given organization.
    Returns document metadata including indexing status.
    """
    from app.main import metadata_store

    try:
        documents = metadata_store.list_documents(org_id)
        return {"documents": documents, "count": len(documents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")
