"""Exercise the installed OCR engine with generated scanned PDFs."""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SAMPLES = [
    ("eng", "HELLO OCR 123", "HELLO OCR"),
    ("rus", "ПРИВЕТ МИР 123", "ПРИВЕТ МИР"),
]

font = ImageFont.truetype(
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 72
)

for language, text, expected in SAMPLES:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "scan.pdf"
        result = root / "result.pdf"
        sidecar = root / "result.txt"

        image = Image.new("RGB", (1500, 400), "white")
        draw = ImageDraw.Draw(image)
        draw.text((70, 120), text, fill="black", font=font)
        image.save(source, "PDF", resolution=300)

        subprocess.run(
            [
                "ocrmypdf", "--language", language, "--mode", "skip",
                "--rotate-pages", "--deskew", "--output-type", "pdf",
                "--optimize", "1", "--jobs", "2", "--sidecar", str(sidecar),
                str(source), str(result),
            ],
            check=True,
            timeout=120,
        )
        assert result.is_file() and result.stat().st_size > 0
        recognized = sidecar.read_text(encoding="utf-8").upper()
        assert expected in recognized, (language, recognized)
