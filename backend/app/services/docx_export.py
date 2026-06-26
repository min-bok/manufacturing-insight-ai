from __future__ import annotations

import base64
from io import BytesIO
import re
from typing import Any
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

from app.schemas import ReportDetail


def build_docx(report: ReportDetail) -> bytes:
    images: list[tuple[str, bytes, str]] = []
    body_parts: list[str] = [_paragraph(report.title, style="Title")]

    for block in report.blocks:
        body_parts.append(_paragraph(block.title, style="Heading1"))
        content = block.content
        if block.type in {"answer", "summary", "recommendation", "suggestions", "title"}:
            _append_text_content(body_parts, content)
        elif block.type == "kpi":
            metrics = content.get("metrics") or []
            for metric in metrics:
                body_parts.append(_paragraph(f"{metric.get('label')}: {metric.get('value')}"))
        elif block.type == "chart":
            image_data = str(content.get("imageDataUrl") or "")
            if image_data.startswith("data:image"):
                image_name, image_bytes, ext = _parse_data_url(image_data, len(images) + 1)
                images.append((image_name, image_bytes, ext))
                body_parts.append(_image_paragraph(f"rId{len(images)}"))
            else:
                chart = content.get("chart") or {}
                body_parts.append(_paragraph(str(chart.get("title") or "차트")))
                body_parts.append(_paragraph(f"차트 유형: {chart.get('type', '-')}", style=None))
                body_parts.append(_table_as_text(chart.get("data") or [], limit=8))
        elif block.type == "table":
            body_parts.append(_table_as_text(content.get("rows") or content.get("table") or [], limit=20))
        else:
            _append_text_content(body_parts, content)

    body = "".join(body_parts)
    rels = _document_rels(images)
    content_types = _content_types(images)

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", _root_rels())
        docx.writestr("word/document.xml", _document_xml(body))
        docx.writestr("word/_rels/document.xml.rels", rels)
        docx.writestr("word/styles.xml", _styles_xml())
        for image_name, image_bytes, _ext in images:
            docx.writestr(f"word/media/{image_name}", image_bytes)
    return buffer.getvalue()


def _append_text_content(body_parts: list[str], content: dict[str, Any]) -> None:
    text = content.get("text") or content.get("answer") or content.get("summary")
    if isinstance(text, str):
        for line in text.splitlines():
            if line.strip():
                body_parts.append(_paragraph(line.strip()))
    suggestions = content.get("suggestions")
    if isinstance(suggestions, list):
        for item in suggestions:
            body_parts.append(_paragraph(f"- {item}"))


def _table_as_text(rows: list[dict[str, Any]], limit: int) -> str:
    if not rows:
        return _paragraph("표시할 데이터가 없습니다.")
    lines = []
    keys = list(rows[0].keys())[:8]
    lines.append(" | ".join(keys))
    for row in rows[:limit]:
        lines.append(" | ".join(str(row.get(key, "")) for key in keys))
    return "".join(_paragraph(line) for line in lines)


def _parse_data_url(data_url: str, index: int) -> tuple[str, bytes, str]:
    match = re.match(r"data:image/(png|jpeg|jpg);base64,(.+)", data_url)
    if not match:
        raise ValueError("Unsupported image data URL")
    ext = "jpg" if match.group(1) in {"jpeg", "jpg"} else "png"
    return f"chart-{index}.{ext}", base64.b64decode(match.group(2)), ext


def _paragraph(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    safe = escape(str(text))
    return f"<w:p>{style_xml}<w:r><w:t xml:space=\"preserve\">{safe}</w:t></w:r></w:p>"


def _image_paragraph(rid: str) -> str:
    width = 5486400
    height = 3086100
    return f"""
<w:p><w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{width}" cy="{height}"/><wp:docPr id="1" name="Chart"/><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="0" name="chart"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width}" cy="{height}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>
"""


def _document_xml(body: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>
"""


def _root_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>
"""


def _document_rels(images: list[tuple[str, bytes, str]]) -> str:
    rels = [
        '<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    ]
    for index, (image_name, _bytes, _ext) in enumerate(images, start=1):
        rels.append(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{image_name}"/>'
        )
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">{''.join(rels)}</Relationships>"


def _content_types(images: list[tuple[str, bytes, str]]) -> str:
    defaults = [
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    if any(ext == "png" for _name, _bytes, ext in images):
        defaults.append('<Default Extension="png" ContentType="image/png"/>')
    if any(ext == "jpg" for _name, _bytes, ext in images):
        defaults.append('<Default Extension="jpg" ContentType="image/jpeg"/>')
    overrides = [
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
    ]
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">{''.join(defaults + overrides)}</Types>"


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style></w:styles>
"""
