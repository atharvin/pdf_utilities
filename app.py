import os
import shutil
import sys

# Prevent decouple from raising on missing translation-only env vars
for _k in ("TRANSLATION_PRIVATE_KEY", "TRANSLATION_PRIVATE_KEY_ID",
           "TRANSLATION_EMAIL", "TRANSLATION_CLIENT_ID"):
    os.environ.setdefault(_k, "")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QComboBox,
)
from PyQt6.QtCore import QThread, pyqtSignal

# When running as a PyInstaller bundle, point bundled binaries at the right paths
if getattr(sys, "frozen", False):
    import pytesseract
    _base = sys._MEIPASS
    _binary = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    pytesseract.pytesseract.tesseract_cmd = os.path.join(_base, _binary)
    os.environ["TESSDATA_PREFIX"] = os.path.join(_base, "tessdata")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(_base, "pw_browsers"))

import translation_service.env_config as ec
from translation_service.pdf_utils import (
    is_scanned_pdf,
    merge_files_to_pdf,
    ocr_pdf,
    pdf_chunks_to_folder,
    pdf_pages_to_folder,
)
from translation_service.browser_translate import LANG_OPTIONS, translate_folder


def _tesseract_available() -> bool:
    if getattr(sys, "frozen", False):
        binary = "tesseract.exe" if sys.platform == "win32" else "tesseract"
        return os.path.exists(os.path.join(sys._MEIPASS, binary))
    return bool(shutil.which("tesseract"))


class Worker(QThread):
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn() or "Done.")
        except Exception as e:
            self.failed.emit(str(e))


def _log():
    w = QTextEdit()
    w.setReadOnly(True)
    w.setMinimumHeight(140)
    return w


def _row(*widgets):
    layout = QHBoxLayout()
    for w in widgets:
        layout.addWidget(w)
    return layout


def _browse_open(line, caption="Select file", filt="PDF (*.pdf)"):
    path, _ = QFileDialog.getOpenFileName(None, caption, "", filt)
    if path:
        line.setText(path)


def _browse_folder(line, caption="Select folder"):
    path = QFileDialog.getExistingDirectory(None, caption)
    if path:
        line.setText(path)


def _browse_save(line, caption="Save as", filt="PDF (*.pdf)"):
    path, _ = QFileDialog.getSaveFileName(None, caption, "", filt)
    if path:
        line.setText(path)


class ProcessTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)

        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Input PDF…")
        inp_btn = QPushButton("Browse")
        inp_btn.clicked.connect(lambda: _browse_open(self.input_line))
        lay.addLayout(_row(QLabel("Input PDF:"), self.input_line, inp_btn))

        self.out_line = QLineEdit()
        self.out_line.setPlaceholderText("Output folder (leave blank to auto-create next to input)")
        out_btn = QPushButton("Browse")
        out_btn.clicked.connect(lambda: _browse_folder(self.out_line))
        lay.addLayout(_row(QLabel("Output folder:"), self.out_line, out_btn))

        self.mode = QComboBox()
        self.mode.addItems(["Auto-detect", "Force scanned (images)", "Force unscanned (chunks)"])
        lay.addLayout(_row(QLabel("Mode:"), self.mode))

        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self._run)
        lay.addWidget(run_btn)

        self.log_box = _log()
        lay.addWidget(self.log_box)
        self._worker = None

    def _run(self):
        input_path = self.input_line.text().strip()
        if not input_path:
            self.log_box.append("Select an input PDF first.")
            return

        stem = os.path.splitext(os.path.basename(input_path))[0]
        out_dir = self.out_line.text().strip() or os.path.join(
            os.path.dirname(input_path), f"{stem}_output"
        )
        mode_idx = self.mode.currentIndex()

        def work():
            with open(input_path, "rb") as f:
                pdf_bytes = f.read()
            if mode_idx == 0:
                scanned = is_scanned_pdf(pdf_bytes)
            else:
                scanned = mode_idx == 1
            if scanned:
                paths = pdf_pages_to_folder(pdf_bytes, out_dir, ec.image_dpi)
                return f"Saved {len(paths)} page image(s) to:\n{out_dir}"
            else:
                paths = pdf_chunks_to_folder(pdf_bytes, out_dir)
                return f"Saved {len(paths)} chunk(s) to:\n{out_dir}"

        self._start(work, f"Processing {os.path.basename(input_path)}…")

    def _start(self, fn, msg):
        self.log_box.append(msg)
        self._worker = Worker(fn)
        self._worker.done.connect(lambda m: self.log_box.append(f"✓ {m}"))
        self._worker.failed.connect(lambda e: self.log_box.append(f"✗ Error: {e}"))
        self._worker.start()


class OcrTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)

        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Input PDF…")
        inp_btn = QPushButton("Browse")
        inp_btn.clicked.connect(lambda: _browse_open(self.input_line))
        lay.addLayout(_row(QLabel("Input PDF:"), self.input_line, inp_btn))

        self.out_line = QLineEdit()
        self.out_line.setPlaceholderText("Output PDF (leave blank to auto-name next to input)")
        out_btn = QPushButton("Save as")
        out_btn.clicked.connect(lambda: _browse_save(self.out_line))
        lay.addLayout(_row(QLabel("Output PDF:"), self.out_line, out_btn))

        self.run_btn = QPushButton("Run OCR")
        self.run_btn.clicked.connect(self._run)
        if not _tesseract_available():
            self.run_btn.setEnabled(False)
            self.run_btn.setToolTip("Tesseract is not installed — OCR unavailable")
        lay.addWidget(self.run_btn)

        self.log_box = _log()
        if not _tesseract_available():
            self.log_box.append("Tesseract not found. Install it to use OCR.")
        lay.addWidget(self.log_box)
        self._worker = None

    def _run(self):
        input_path = self.input_line.text().strip()
        if not input_path:
            self.log_box.append("Select an input PDF first.")
            return

        stem = os.path.splitext(os.path.basename(input_path))[0]
        out_path = self.out_line.text().strip() or os.path.join(
            os.path.dirname(input_path), f"{stem}_ocr.pdf"
        )

        def work():
            with open(input_path, "rb") as f:
                pdf_bytes = f.read()
            result = ocr_pdf(pdf_bytes)
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(result)
            return f"Saved to:\n{out_path}"

        self.log_box.append(f"Running OCR on {os.path.basename(input_path)}…")
        self._worker = Worker(work)
        self._worker.done.connect(lambda m: self.log_box.append(f"✓ {m}"))
        self._worker.failed.connect(lambda e: self.log_box.append(f"✗ Error: {e}"))
        self._worker.start()


class MergeTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)

        self.files_line = QLineEdit()
        self.files_line.setPlaceholderText("No files selected…")
        self.files_line.setReadOnly(True)
        files_btn = QPushButton("Select files")
        files_btn.clicked.connect(self._browse_files)
        lay.addLayout(_row(QLabel("Input files:"), self.files_line, files_btn))

        self.out_line = QLineEdit()
        self.out_line.setPlaceholderText("Output PDF…")
        out_btn = QPushButton("Save as")
        out_btn.clicked.connect(lambda: _browse_save(self.out_line))
        lay.addLayout(_row(QLabel("Output PDF:"), self.out_line, out_btn))

        run_btn = QPushButton("Merge")
        run_btn.clicked.connect(self._run)
        lay.addWidget(run_btn)

        self.log_box = _log()
        lay.addWidget(self.log_box)
        self._files = []
        self._worker = None

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select files to merge", "",
            "PDFs and Images (*.pdf *.png *.jpg *.jpeg *.tiff *.tif *.bmp *.webp)",
        )
        if paths:
            self._files = sorted(paths)
            self.files_line.setText(f"{len(paths)} file(s) selected")

    def _run(self):
        if not self._files:
            self.log_box.append("Select files to merge first.")
            return
        out_path = self.out_line.text().strip()
        if not out_path:
            self.log_box.append("Specify an output PDF path.")
            return

        files_snapshot = list(self._files)

        def work():
            file_data = []
            for path in files_snapshot:
                with open(path, "rb") as f:
                    file_data.append((os.path.basename(path), f.read()))
            result = merge_files_to_pdf(file_data)
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(result)
            return f"Saved to:\n{out_path}"

        self.log_box.append(f"Merging {len(files_snapshot)} file(s)…")
        self._worker = Worker(work)
        self._worker.done.connect(lambda m: self.log_box.append(f"✓ {m}"))
        self._worker.failed.connect(lambda e: self.log_box.append(f"✗ Error: {e}"))
        self._worker.start()


class TranslateTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)

        self.in_line = QLineEdit()
        self.in_line.setPlaceholderText("Folder containing documents…")
        in_btn = QPushButton("Browse")
        in_btn.clicked.connect(lambda: _browse_folder(self.in_line))
        lay.addLayout(_row(QLabel("Input folder:"), self.in_line, in_btn))

        self.out_line = QLineEdit()
        self.out_line.setPlaceholderText("Output folder (leave blank to auto-create next to input)")
        out_btn = QPushButton("Browse")
        out_btn.clicked.connect(lambda: _browse_folder(self.out_line))
        lay.addLayout(_row(QLabel("Output folder:"), self.out_line, out_btn))

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANG_OPTIONS)
        lay.addLayout(_row(QLabel("Translate to:"), self.lang_combo))

        run_btn = QPushButton("Translate All")
        run_btn.clicked.connect(self._run)
        lay.addWidget(run_btn)

        self.log_box = _log()
        lay.addWidget(self.log_box)
        self._worker = None

    def _run(self):
        in_dir = self.in_line.text().strip()
        if not in_dir:
            self.log_box.append("Select an input folder first.")
            return

        out_dir = self.out_line.text().strip() or os.path.join(
            os.path.dirname(in_dir), f"{os.path.basename(in_dir)}_translated"
        )
        target_lang = self.lang_combo.currentText()

        def work():
            paths = translate_folder(
                in_dir, out_dir, target_lang,
                progress_cb=lambda msg: self.log_box.append(msg),
            )
            return f"Done. {len(paths)} file(s) saved to:\n{out_dir}"

        self.log_box.append(f"Starting translation to {target_lang}…")
        self._worker = Worker(work)
        self._worker.done.connect(lambda m: self.log_box.append(f"✓ {m}"))
        self._worker.failed.connect(lambda e: self.log_box.append(f"✗ Error: {e}"))
        self._worker.start()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Tools")
        self.resize(720, 480)
        tabs = QTabWidget()
        tabs.addTab(ProcessTab(), "Process PDF")
        tabs.addTab(OcrTab(), "OCR PDF")
        tabs.addTab(MergeTab(), "Merge to PDF")
        tabs.addTab(TranslateTab(), "Translate Folder")
        self.setCentralWidget(tabs)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
