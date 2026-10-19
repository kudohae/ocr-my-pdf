from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import main


class FakeProcess:
    returncode = 0

    async def communicate(self):
        return b"", b""


async def fake_ocr(*command, **_kwargs):
    Path(command[-1]).write_bytes(b"%PDF-1.4\nOCR result")
    return FakeProcess()


def test_home_and_invalid_uploads():
    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200
        assert "PDF OCR" in client.get("/").text
        assert client.post("/ocr", files={"file": ("wrong.txt", b"%PDF-1.4")}).status_code == 400
        assert client.post("/ocr", files={"file": ("wrong.pdf", b"not a PDF")}).status_code == 400
        assert client.post(
            "/ocr", data={"language": "invalid"}, files={"file": ("file.pdf", b"%PDF-1.4")}
        ).status_code == 400


def test_ocr_download_and_cleanup(tmp_path):
    with patch.object(main.tempfile, "mkdtemp", return_value=str(tmp_path / "job")), \
         patch.object(main.asyncio, "create_subprocess_exec", side_effect=fake_ocr):
        (tmp_path / "job").mkdir()
        with TestClient(main.app) as client:
            response = client.post(
                "/ocr", files={"file": ("문서.pdf", b"%PDF-1.4\nscan")}
            )
        assert response.status_code == 200
        assert response.content == b"%PDF-1.4\nOCR result"
        assert response.headers["content-type"] == "application/pdf"
        assert not (tmp_path / "job").exists()


def test_upload_limit(tmp_path):
    with patch.object(main, "MAX_UPLOAD_BYTES", 5), \
         patch.object(main.tempfile, "mkdtemp", return_value=str(tmp_path / "large")):
        (tmp_path / "large").mkdir()
        with TestClient(main.app) as client:
            response = client.post("/ocr", files={"file": ("large.pdf", b"%PDF-1.4")})
        assert response.status_code == 413
        assert not (tmp_path / "large").exists()


@pytest.mark.parametrize("language", ["rus+eng", "kor+rus"])
def test_russian_language_is_passed_to_ocrmypdf(tmp_path, language):
    commands = []

    async def recording_ocr(*command, **kwargs):
        commands.append(command)
        return await fake_ocr(*command, **kwargs)

    with patch.object(main.tempfile, "mkdtemp", return_value=str(tmp_path / "rus")), \
         patch.object(main.asyncio, "create_subprocess_exec", side_effect=recording_ocr):
        (tmp_path / "rus").mkdir()
        with TestClient(main.app) as client:
            response = client.post(
                "/ocr", data={"language": language}, files={"file": ("документ.pdf", b"%PDF-1.4\nscan")}
            )
        assert response.status_code == 200
        assert commands[0][1:3] == ("--language", language)
