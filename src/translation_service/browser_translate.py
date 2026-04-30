import os
from collections.abc import Callable

from playwright.sync_api import sync_playwright

from translation_service.logger_utils import logger

LANG_OPTIONS = [
    "English",
    "Korean",
    "Thai",
    "French",
    "Japanese",
    "Chinese (Simplified)",
    "Spanish",
    "German",
    "Arabic",
    "Hindi",
]

_LANG_CODES = {
    "English": "en",
    "Korean": "ko",
    "Thai": "th",
    "French": "fr",
    "Japanese": "ja",
    "Chinese (Simplified)": "zh-CN",
    "Spanish": "es",
    "German": "de",
    "Arabic": "ar",
    "Hindi": "hi",
}

_SUPPORTED_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".txt", ".rtf"}


def translate_folder(
    input_dir: str,
    output_dir: str,
    target_lang: str,
    progress_cb: Callable[[str], None] | None = None,
) -> list[str]:
    """Opens a browser and translates every supported document in input_dir via
    Google Translate, saving results to output_dir. Returns saved file paths."""
    os.makedirs(output_dir, exist_ok=True)
    lang_code = _LANG_CODES.get(target_lang, "en")

    files = [
        f for f in sorted(os.listdir(input_dir))
        if os.path.splitext(f)[1].lower() in _SUPPORTED_EXTS
    ]
    if not files:
        raise ValueError(f"No supported documents found in {input_dir}")

    logger.info(f"Translating {len(files)} file(s) to {target_lang} ({lang_code})")
    translated: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        for i, filename in enumerate(files):
            file_path = os.path.join(input_dir, filename)
            msg = f"({i + 1}/{len(files)}) {filename}"
            logger.info(f"Translating {msg}")
            if progress_cb:
                progress_cb(f"Translating {msg}…")

            try:
                url = f"https://translate.google.com/?op=docs&sl=auto&tl={lang_code}"
                page.goto(url, wait_until="domcontentloaded")

                # Upload the document (first input = docs, second = images)
                page.locator('input[type="file"]').first.set_input_files(file_path)

                # Click Translate
                translate_btn = page.get_by_role("button", name="Translate")
                translate_btn.wait_for(state="visible", timeout=30_000)
                translate_btn.click()

                # Wait for translation and download
                download_btn = page.get_by_role("button", name="Download translation")
                download_btn.wait_for(state="visible", timeout=180_000)

                with page.expect_download(timeout=60_000) as dl_info:
                    download_btn.click()

                dl = dl_info.value
                out_name = dl.suggested_filename or f"translated_{filename}"
                out_path = os.path.join(output_dir, out_name)
                dl.save_as(out_path)
                translated.append(out_path)
                logger.info(f"Saved: {out_path}")
                if progress_cb:
                    progress_cb(f"✓ Saved: {out_name}")

            except Exception as e:
                logger.error(f"Failed to translate {filename}: {e}")
                if progress_cb:
                    progress_cb(f"✗ Failed {filename}: {e}")

        browser.close()

    return translated
