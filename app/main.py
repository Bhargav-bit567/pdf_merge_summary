"""FastAPI application: serves the web UI and the PDF summarization API."""
import base64
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import summarizer
from app.extractor import count_pages, extract_text_from_pdf, merge_pdfs

STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB (supports 100-200+ pages)


def _looks_like_pdf(filename: str | None, content_type: str | None, data: bytes) -> bool:
    """Accept PDFs even when browsers send blank or generic MIME types."""
    if filename and filename.lower().endswith(".pdf"):
        return True
    if content_type and content_type.lower() == "application/pdf":
        return True
    return data.startswith(b"%PDF-")


app = FastAPI(title="Local PDF Summarizer", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def api_health() -> dict:
    return await run_in_threadpool(summarizer.health)


@app.post("/api/summarize")
async def api_summarize(
    file: UploadFile = File(...),
    mode: str = Form("detailed"),
    model: str = Form(summarizer.DEFAULT_MODEL),
) -> dict:
    if mode not in summarizer.SUMMARY_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown summary mode '{mode}'.")

    filename = file.filename or "document.pdf"
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not _looks_like_pdf(filename, file.content_type, data):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (max 100 MB).")
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        text = await run_in_threadpool(extract_text_from_pdf, data)
        pages = await run_in_threadpool(count_pages, data)
        result = await run_in_threadpool(
            summarizer.summarize, text, mode, filename, model
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except summarizer.OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result.update({"filename": filename, "pages": pages})
    return result


@app.post("/api/merge")
async def api_merge(files: list[UploadFile] = File(...)) -> dict:
    """Merge multiple PDFs (or PDF chunks) into a single PDF."""
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Please select at least 2 PDF files to merge.")

    pdfs: list[bytes] = []
    total_pages = 0
    total_size = 0
    max_single = 50 * 1024 * 1024  # 50 MB per individual file during merge

    for file in files:
        data = await file.read(max_single + 1)
        total_size += len(data)
        if len(data) > max_single:
            raise HTTPException(status_code=413, detail=f"{file.filename} exceeds 50 MB.")
        if not data:
            raise HTTPException(status_code=400, detail=f"{file.filename} is empty.")
        if not _looks_like_pdf(file.filename, file.content_type, data):
            raise HTTPException(status_code=400, detail=f"{file.filename} is not a PDF.")

        try:
            pages = await run_in_threadpool(count_pages, data)
        except Exception:
            raise HTTPException(status_code=400, detail=f"{file.filename} is not a valid PDF.")

        pdfs.append(data)
        total_pages += pages

    if total_pages == 0:
        raise HTTPException(status_code=422, detail="No extractable content found in any file.")
    if total_size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Combined files exceed the 100 MB limit.")

    merged = await run_in_threadpool(merge_pdfs, pdfs, "merged.pdf")
    base = "_".join(f.filename or "file" for f in files).replace(".pdf", "")
    return {
        "filename": f"{base}_merged.pdf",
        "pages": total_pages,
        "size": len(merged),
        "file": base64.b64encode(merged).decode("ascii"),
    }


@app.post("/api/merge/download")
async def api_merge_download(files: list[UploadFile] = File(...)) -> StreamingResponse:
    """Download the merged PDF directly as an attachment."""
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Please select at least 2 PDF files to merge.")

    pdfs: list[bytes] = []
    total_pages = 0
    total_size = 0
    max_single = 50 * 1024 * 1024

    for file in files:
        data = await file.read(max_single + 1)
        total_size += len(data)
        if len(data) > max_single:
            raise HTTPException(status_code=413, detail=f"{file.filename} exceeds 50 MB.")
        if not data:
            raise HTTPException(status_code=400, detail=f"{file.filename} is empty.")
        if not _looks_like_pdf(file.filename, file.content_type, data):
            raise HTTPException(status_code=400, detail=f"{file.filename} is not a PDF.")

        try:
            total_pages += await run_in_threadpool(count_pages, data)
        except Exception:
            raise HTTPException(status_code=400, detail=f"{file.filename} is not a valid PDF.")

        pdfs.append(data)

    if total_pages == 0:
        raise HTTPException(status_code=422, detail="No extractable content found in any file.")
    if total_size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Combined files exceed the 100 MB limit.")

    merged = await run_in_threadpool(merge_pdfs, pdfs, "merged.pdf")
    filename = "_".join(f.filename or "file" for f in files).replace(".pdf", "") + "_merged.pdf"
    return StreamingResponse(
        BytesIO(merged),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )