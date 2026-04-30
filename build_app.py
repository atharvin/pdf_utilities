"""PyInstaller build helper — handles the SOURCE:DEST vs SOURCE;DEST separator
difference between Linux/macOS and Windows automatically."""
import os
import subprocess
import sys

sep = ";" if sys.platform == "win32" else ":"
tesseract_bin = os.environ["TESSERACT_BIN"]

subprocess.run(
    [
        "pyinstaller", "--onefile", "--windowed", "--name", "PDFTools",
        "--add-binary", f"{tesseract_bin}{sep}.",
        "--add-data", f"tessdata{sep}tessdata",
        "--hidden-import=translation_service.pdf_utils",
        "--hidden-import=translation_service.env_config",
        "--hidden-import=translation_service.logger_utils",
        "app.py",
    ],
    check=True,
)
