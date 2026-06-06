from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "六年级上册数学沪教版同步教学_逐字稿合集_修订版.txt"
TARGET = ROOT / "六年级上册数学沪教版同步教学_逐字稿合集_修订版.pdf"
SONGTI_FONT = Path("/System/Library/Fonts/Supplemental/Songti.ttc")


def register_songti() -> str:
    if not SONGTI_FONT.exists():
        raise FileNotFoundError(f"未找到宋体字体文件: {SONGTI_FONT}")
    font_name = "SongtiSC"
    pdfmetrics.registerFont(TTFont(font_name, str(SONGTI_FONT), subfontIndex=6))
    return font_name


class TranscriptDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)
        self._heading_count = 0

    def beforeDocument(self):
        self._heading_count = 0

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return

        style_name = flowable.style.name
        if style_name == "ChapterHeading":
            self._heading_count += 1
            key = f"chapter-{self._heading_count}"
            text = flowable.getPlainText()
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=0, closed=False)
            self.notify("TOCEntry", (0, text, self.page, key))


def draw_page(canvas, doc, font_name: str) -> None:
    canvas.saveState()
    page_w, _ = A4
    canvas.setFont(font_name, 9)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawCentredString(page_w / 2, 1.1 * cm, str(canvas.getPageNumber()))
    canvas.restoreState()


def parse_source() -> tuple[str, list[tuple[str, list[str]]]]:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    title = "六年级上册数学沪教版同步教学逐字稿（修订版）"
    chapters: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_paragraphs: list[str] = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            continue
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            if current_title is not None:
                chapters.append((current_title, current_paragraphs))
            current_title = heading.group(1).strip()
            current_paragraphs = []
            continue
        if current_title is not None:
            current_paragraphs.append(line)

    if current_title is not None:
        chapters.append((current_title, current_paragraphs))
    return title, chapters


def make_styles(font_name: str):
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=24,
            leading=34,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#222222"),
            spaceAfter=18,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="TocTitle",
            parent=styles["Heading1"],
            fontName=font_name,
            fontSize=18,
            leading=26,
            textColor=colors.HexColor("#222222"),
            spaceAfter=16,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="ChapterHeading",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=16,
            leading=24,
            textColor=colors.HexColor("#111111"),
            spaceBefore=8,
            spaceAfter=12,
            keepWithNext=True,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodySongti",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=11,
            leading=18,
            firstLineIndent=22,
            spaceAfter=7,
            textColor=colors.HexColor("#222222"),
            wordWrap="CJK",
        )
    )
    return styles


def build_pdf() -> None:
    font_name = register_songti()
    title, chapters = parse_source()
    styles = make_styles(font_name)

    frame = Frame(2.0 * cm, 1.8 * cm, 17.0 * cm, 25.5 * cm, id="normal")
    doc = TranscriptDocTemplate(
        str(TARGET),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="content", frames=[frame], onPage=lambda c, d: draw_page(c, d, font_name)),
        ]
    )

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            name="TOCLevel0",
            fontName=font_name,
            fontSize=11,
            leading=18,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=2,
            wordWrap="CJK",
        )
    ]

    story = [
        NextPageTemplate("content"),
        Spacer(1, 3.0 * cm),
        Paragraph(title, styles["CoverTitle"]),
        Paragraph("目录可点击跳转到对应章节，侧边栏书签也按章节生成。", styles["BodySongti"]),
        PageBreak(),
        Paragraph("目录", styles["TocTitle"]),
        toc,
        PageBreak(),
    ]

    for chapter_title, paragraphs in chapters:
        story.append(Paragraph(chapter_title, styles["ChapterHeading"]))
        for paragraph in paragraphs:
            story.append(Paragraph(paragraph, styles["BodySongti"]))
        story.append(PageBreak())

    if isinstance(story[-1], PageBreak):
        story.pop()

    doc.multiBuild(story)
    print(TARGET)


if __name__ == "__main__":
    build_pdf()
