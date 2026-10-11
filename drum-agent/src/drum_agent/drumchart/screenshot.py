"""Screenshots and PDFs of rendered chart pages (Playwright Chromium).

Used to LOOK at a chart (vision check) and to export print-ready PDFs.
If Playwright's bundled browser is missing it falls back to $CHROMIUM or
/opt/pw-browsers/chromium-*/chrome-linux/chrome.
"""

import glob
import os


def _exe():
    if os.environ.get("CHROMIUM"):
        return os.environ["CHROMIUM"]
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome", "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell"):
        c = sorted(glob.glob(pat))
        if c:
            return c[-1]
    return None


def screenshot(html_path: str, png_path: str, width: int = 1300, dark: bool = False, full: bool = True,
               scale: float = 1.0, max_height: int = 0, selector: str = ""):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        kw = {}
        try:
            browser = p.chromium.launch()
        except Exception:
            exe = _exe()
            if not exe:
                raise
            browser = p.chromium.launch(executable_path=exe)
        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=scale,
                                color_scheme="dark" if dark else "light")
        page.goto("file://" + os.path.abspath(html_path))
        page.wait_for_timeout(700)
        if selector:
            page.locator(selector).first.screenshot(path=png_path)
        elif max_height:
            h = min(max_height, page.evaluate("document.body.scrollHeight"))
            page.set_viewport_size({"width": width, "height": h})
            page.screenshot(path=png_path, full_page=False)
        else:
            page.screenshot(path=png_path, full_page=full)
        browser.close()


def pdf(html_path: str, pdf_path: str, paper: str = "letter"):
    """Print the chart (4 bars per line, light theme) to a PDF."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(executable_path=_exe())
        page = browser.new_page(color_scheme="light")
        page.goto("file://" + os.path.abspath(html_path))
        page.wait_for_timeout(600)
        page.pdf(path=pdf_path, format="A4" if paper.lower() == "a4" else "Letter", print_background=True,
                 margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
        browser.close()
