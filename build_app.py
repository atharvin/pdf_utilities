"""PyInstaller build helper — handles the SOURCE:DEST vs SOURCE;DEST separator
difference between Linux/macOS and Windows automatically."""
import glob
import os
import subprocess
import sys

import playwright

sep = ";" if sys.platform == "win32" else ":"
tesseract_bin = os.environ["TESSERACT_BIN"]
pw_driver = os.path.join(os.path.dirname(playwright.__file__), "driver")

cmd = [
    "pyinstaller", "--onefile", "--windowed", "--name", "PDFTools",
    "--add-binary", f"{tesseract_bin}{sep}.",
    "--add-data", f"tessdata{sep}tessdata",
    "--add-data", f"{pw_driver}{sep}playwright/driver",
    "--hidden-import=translation_service.pdf_utils",
    "--hidden-import=translation_service.env_config",
    "--hidden-import=translation_service.logger_utils",
    "--hidden-import=playwright",
]

# On Windows, bundle all DLLs from the entire Tesseract directory tree
if sys.platform == "win32":
    tesseract_dir = os.path.dirname(tesseract_bin)
    for dll in glob.glob(os.path.join(tesseract_dir, "**", "*.dll"), recursive=True):
        cmd.extend(["--add-binary", f"{dll}{sep}."])

cmd.append("app.py")

subprocess.run(cmd, check=True)
