"""
ui/tabs/help_tab.py
[XREF: help-tab] The shared Help tab body: an "About" card (project, version,
date, blurb) above a styled, read-only render of the app's User Guide
markdown. The guide is passed in as a FILE PATH (help_file) so the tab has no
hard dependency on the app registry; HelpTab.for_app() remains a convenience
for apps registered in ui.common.app_info.

Rendering follows the mdgv approach — convert Markdown to an HTML fragment,
then wrap it in an HTML document with a CSS stylesheet and setHtml() — because
QTextBrowser.setMarkdown() ignores most styling. Colors come from the active
theme palette; call refresh() after a theme change.
"""
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QTextCursor, QTextDocument
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextBrowser, QFrame

from ui import theme
from ui.widgets.section import Section
from ui.common import app_info


def _markdown_to_fragment(md_text: str) -> str:
    doc = QTextDocument()
    try:
        doc.setMarkdown(md_text, QTextDocument.MarkdownDialectGitHub)
    except (AttributeError, TypeError):
        doc.setMarkdown(md_text)
    html = doc.toHtml()
    m = re.search(r"<body[^>]*>(.*)</body>", html, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else html


def _read_markdown(path) -> str:
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return (f"# Help\n\n_User guide not found at_ `{p}`.\n\n> {e}\n")


class HelpTab(QWidget):
    """Help tab: About card + rendered User Guide.

    Args:
        help_file: path to the markdown user guide (the field the tab renders)
        title:     app title for the About card
        blurb:     one-line description for the About card
        version/updated: metadata line (defaults to project-wide values)
    """

    def __init__(self, help_file, title: str, blurb: str = "",
                 version: str = app_info.VERSION,
                 updated: str = app_info.UPDATED, parent=None):
        super().__init__(parent)
        self._help_file = Path(help_file)
        self._title = title
        self._blurb = blurb
        self._version = version
        self._updated = updated
        self._markdown = _read_markdown(self._help_file)
        self._build_ui()
        # Re-render with the new palette whenever any theme is applied
        # (auto-disconnected when this widget is destroyed).
        theme.signals.changed.connect(self._on_theme_changed)

    @classmethod
    def for_app(cls, app_key: str, parent=None) -> "HelpTab":
        """Build from the ui.common.app_info registry (existing apps)."""
        info = app_info.APPS[app_key]
        return cls(app_info.guide_path(app_key), info.title, info.blurb,
                   parent=parent)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        about = Section("About")
        title = QLabel(f"<b>{app_info.PROJECT}</b> &mdash; {self._title}")
        title.setTextFormat(Qt.RichText)
        about.add_widget(title)

        blurb = QLabel(self._blurb)
        blurb.setWordWrap(True)
        about.add_widget(blurb)

        meta = QLabel(f"Version {self._version}   ·   Updated {self._updated}")
        meta.setObjectName("mutedLabel")
        about.add_widget(meta)

        guide_ref = QLabel(f"User Guide: {self._help_file.name}")
        guide_ref.setObjectName("mutedLabel")
        about.add_widget(guide_ref)
        root.addWidget(about)

        self._browser = QTextBrowser()
        self._browser.setReadOnly(True)
        self._browser.setOpenLinks(False)
        self._browser.setOpenExternalLinks(False)
        self._browser.anchorClicked.connect(QDesktopServices.openUrl)
        self._browser.setFrameShape(QFrame.NoFrame)
        self._browser.document().setDocumentMargin(18)
        root.addWidget(self._browser, 1)

        self.refresh()

    def _on_theme_changed(self, _selection: str):
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        """(Re)render the guide against the current theme palette."""
        self._browser.setHtml(self._wrapped_html())
        self._browser.moveCursor(QTextCursor.Start)

    def _wrapped_html(self) -> str:
        fragment = _markdown_to_fragment(self._markdown)
        return (f"<!doctype html><html><head><meta charset='utf-8'>"
                f"<style>{self._css()}</style></head><body>{fragment}</body></html>")

    def _css(self) -> str:
        p = theme.active_palette()
        bg = p.get("bg_secondary", "#252526")
        text = p.get("text_primary", "#E0E0E0")
        muted = p.get("text_muted", "#9A9A9A")
        heading = p.get("accent_primary", "#4FA3FF")
        border = p.get("border_primary", "#3C3C3C")
        code_fg = p.get("status_active", p.get("data_read", "#2ECC71"))
        code_bg = p.get("bg_tertiary", "#2D2D30")
        pre_bg = p.get("bg_primary", "#1E1E1E")
        link = p.get("accent_primary", "#4FA3FF")
        th_bg = p.get("bg_tertiary", "#2D2D30")
        quote_border = p.get("status_warning", heading)
        strong = heading
        return f"""
        body {{ color: {text}; background-color: {bg}; }}
        h1, h2, h3, h4 {{ color: {heading}; font-weight: 700; margin-top: 16px; margin-bottom: 6px; }}
        h1 {{ font-size: x-large; }}
        h2 {{ font-size: large; border-bottom: 1px solid {border}; padding-bottom: 4px; }}
        h3 {{ font-size: medium; }}
        p {{ margin-top: 6px; margin-bottom: 10px; }}
        a {{ color: {link}; text-decoration: none; }}
        strong, b {{ color: {strong}; font-weight: 700; }}
        em, i {{ color: {text}; }}
        code {{ color: {code_fg}; background-color: {code_bg}; }}
        pre {{ color: {text}; background-color: {pre_bg}; border: 1px solid {border};
               padding: 10px; white-space: pre-wrap; }}
        blockquote {{ color: {muted}; border-left: 3px solid {quote_border};
                      padding-left: 10px; margin-left: 4px; }}
        ul, ol {{ margin-top: 4px; margin-bottom: 10px; }}
        table {{ border-collapse: collapse; margin-top: 10px; margin-bottom: 14px; }}
        th {{ background-color: {th_bg}; color: {heading}; font-weight: 700;
              border: 1px solid {border}; padding: 5px 9px; }}
        td {{ border: 1px solid {border}; padding: 5px 9px; }}
        hr {{ border: none; background-color: {border}; height: 1px; }}
        """
