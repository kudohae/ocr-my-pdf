"""Small web interface for creating searchable PDFs with OCRmyPDF."""

import asyncio
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask


APP_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
OCR_TIMEOUT_SECONDS = 15 * 60
LANGUAGES = {"kor+eng", "kor", "eng", "rus+eng", "rus", "kor+rus"}
OCR_SLOTS = asyncio.Semaphore(2)

app = FastAPI(title="PDF OCR", docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return (APP_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/ocr")
async def ocr(file: UploadFile = File(...), language: str = Form("kor+eng")) -> FileResponse:
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="지원하지 않는 언어 설정입니다.")

    filename = Path(file.filename or "document.pdf").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일을 선택해 주세요.")

    workspace = Path(tempfile.mkdtemp(prefix="pdf-ocr-"))
    input_path = workspace / "input.pdf"
    output_path = workspace / "output.pdf"
    try:
        size = 0
        with input_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="PDF는 100 MB 이하만 처리할 수 있습니다.")
                destination.write(chunk)

        with input_path.open("rb") as source:
            header = source.read(1024)
        if size == 0 or not header.lstrip().startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="올바른 PDF 파일이 아닙니다.")

        command = [
            "ocrmypdf", "--language", language, "--mode", "skip",
            "--rotate-pages", "--deskew", "--output-type", "pdf",
            "--optimize", "1", "--jobs", "2",
            str(input_path), str(output_path),
        ]
        async with OCR_SLOTS:
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=503, detail="OCR 엔진이 설치되지 않았습니다.") from exc
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=OCR_TIMEOUT_SECONDS
                )
            except TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise HTTPException(status_code=504, detail="OCR 처리 시간이 초과됐습니다.") from exc

        if process.returncode != 0 or not output_path.is_file():
            # OCRmyPDF's logs may contain details from private documents; do not send them to browsers.
            error = stderr.decode("utf-8", errors="replace")
            if "encrypted" in error.lower() or "password" in error.lower():
                detail = "암호가 걸린 PDF는 처리할 수 없습니다. 암호를 해제한 뒤 다시 시도해 주세요."
            else:
                detail = "PDF를 처리하지 못했습니다. 파일이 손상되지 않았는지 확인해 주세요."
            raise HTTPException(status_code=422, detail=detail)

        stem = re.sub(r"[\\/\x00-\x1f\x7f]", "", Path(filename).stem).strip(" .")
        download_name = f"{stem or 'document'}-ocr.pdf"
        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=download_name,
            headers={"Cache-Control": "no-store"},
            background=BackgroundTask(shutil.rmtree, workspace, ignore_errors=True),
        )
    except BaseException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    finally:
        await file.close()
