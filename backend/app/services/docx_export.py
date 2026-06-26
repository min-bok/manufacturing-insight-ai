from __future__ import annotations

import base64
from io import BytesIO
import re
from typing import Any
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

# A4 (11906 twips) with 1440-twip margins → usable content width
_CONTENT_W = 9026          # twips
_EMU_PER_TWIP = 635
_CELL_PAD = 80             # twips, left/right padding per cell side


def build_docx(report: Any) -> bytes:
    images: list[tuple[str, bytes, str]] = []
    rows = _group_into_rows(list(report.blocks))
    body_parts: list[str] = [_p(report.title, style="Title")]

    for row in rows:
        if len(row) == 1:
            _render_block(body_parts, images, row[0], _CONTENT_W)
        else:
            col_widths = _col_widths(row)
            body_parts.append(_word_table(images, row, col_widths))

    body = "".join(body_parts)

    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _content_types(images))
        z.writestr("_rels/.rels", _root_rels())
        z.writestr("word/document.xml", _document_xml(body))
        z.writestr("word/_rels/document.xml.rels", _document_rels(images))
        z.writestr("word/styles.xml", _styles_xml())
        for name, data, _ in images:
            z.writestr(f"word/media/{name}", data)
    return buf.getvalue()


# ── Row grouping ──────────────────────────────────────────────────────────────

def _group_into_rows(blocks: list[Any]) -> list[list[Any]]:
    """Group blocks by content.layout.rowId, preserving insertion order."""
    buckets: dict[str, list[tuple[int, Any]]] = {}
    order: list[str] = []
    for block in blocks:
        layout = block.content.get("layout") or {}
        row_id = layout.get("rowId") if isinstance(layout, dict) else None
        seq = layout.get("order", 0) if isinstance(layout, dict) else 0
        key = row_id or f"_solo_{id(block)}"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append((seq, block))
    return [[b for _, b in sorted(v)] for k in order for v in [buckets[k]]]


def _col_widths(row: list[Any]) -> list[int]:
    """Return column widths in twips from layout.width percentages."""
    pcts: list[float | None] = []
    for block in row:
        layout = block.content.get("layout") or {}
        pcts.append(layout.get("width") if isinstance(layout, dict) else None)
    if all(p is not None for p in pcts):
        total = sum(pcts)  # type: ignore[arg-type]
        return [max(1, int(_CONTENT_W * p / total)) for p in pcts]  # type: ignore[operator]
    base = _CONTENT_W // len(row)
    return [base] * len(row)


# ── Block rendering ───────────────────────────────────────────────────────────

def _render_block(parts: list[str], images: list, block: Any, col_w: int) -> None:
    parts.append(_p(block.title, style="Heading1"))
    c, t = block.content, block.type
    if t in {"answer", "summary", "recommendation", "suggestions", "title"}:
        _append_text(parts, c)
    elif t == "kpi":
        for m in (c.get("metrics") or []):
            parts.append(_p(f"{m.get('label')}: {m.get('value')}"))
    elif t == "chart":
        _render_chart(parts, images, c, col_w)
    elif t == "table":
        parts.append(_rows_as_text(c.get("rows") or c.get("table") or [], limit=20))
    else:
        _append_text(parts, c)
    # Word requires at least one <w:p> per table cell — guarantee it
    if not parts or not parts[-1].startswith("<w:p"):
        parts.append(_p(""))


def _render_chart(parts: list[str], images: list, content: dict, col_w: int) -> None:
    img_data = str(content.get("imageDataUrl") or "")
    if img_data.startswith("data:image"):
        name, data, ext = _parse_data_url(img_data, len(images) + 1)
        images.append((name, data, ext))
        rid = f"rId{len(images)}"
        w_emu = int((col_w - 2 * _CELL_PAD) * _EMU_PER_TWIP)
        h_emu = int(w_emu * 9 / 16)
        parts.append(_image_para(rid, w_emu, h_emu, len(images)))
    else:
        chart = content.get("chart") or {}
        parts.append(_p(str(chart.get("title") or "차트")))
        if chart.get("data"):
            parts.append(_rows_as_text(chart["data"], limit=8))


def _append_text(parts: list[str], content: dict[str, Any]) -> None:
    text = content.get("text") or content.get("answer") or content.get("summary")
    if isinstance(text, str):
        for line in text.splitlines():
            if line.strip():
                parts.append(_p(line.strip()))
    suggestions = content.get("suggestions")
    if isinstance(suggestions, list):
        for item in suggestions:
            parts.append(_p(f"• {item}"))


def _rows_as_text(rows: list[dict[str, Any]], limit: int) -> str:
    if not rows:
        return _p("표시할 데이터가 없습니다.")
    keys = list(rows[0].keys())[:8]
    lines = [" | ".join(keys)] + [
        " | ".join(str(row.get(k, "")) for k in keys) for row in rows[:limit]
    ]
    return "".join(_p(line) for line in lines)


# ── Word table (multi-column rows) ────────────────────────────────────────────

def _word_table(images: list, row: list[Any], col_widths: list[int]) -> str:
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in col_widths)

    cells: list[str] = []
    for i, block in enumerate(row):
        cell_parts: list[str] = []
        _render_block(cell_parts, images, block, col_widths[i])
        pad = _CELL_PAD
        cells.append(
            f"<w:tc>"
            f"<w:tcPr>"
            f'<w:tcW w:w="{col_widths[i]}" w:type="dxa"/>'
            f"<w:tcMar>"
            f'<w:top w:w="0" w:type="dxa"/>'
            f'<w:left w:w="{pad}" w:type="dxa"/>'
            f'<w:bottom w:w="0" w:type="dxa"/>'
            f'<w:right w:w="{pad}" w:type="dxa"/>'
            f"</w:tcMar>"
            f"</w:tcPr>"
            + "".join(cell_parts)
            + "</w:tc>"
        )

    no_border = "".join(
        f'<w:{s} w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        for s in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    total_w = sum(col_widths)
    return (
        f"<w:tbl>"
        f"<w:tblPr>"
        f'<w:tblW w:w="{total_w}" w:type="dxa"/>'
        f'<w:tblLayout w:type="fixed"/>'
        f"<w:tblBorders>{no_border}</w:tblBorders>"
        f"</w:tblPr>"
        f"<w:tblGrid>{grid}</w:tblGrid>"
        f"<w:tr>{''.join(cells)}</w:tr>"
        f"</w:tbl>"
    )


# ── XML primitives ────────────────────────────────────────────────────────────

def _p(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{style_xml}<w:r><w:t xml:space="preserve">{escape(str(text))}</w:t></w:r></w:p>'


def _image_para(rid: str, width_emu: int, height_emu: int, doc_pr_id: int) -> str:
    return (
        f"<w:p><w:r><w:drawing>"
        f'<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
        f' distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{width_emu}" cy="{height_emu}"/>'
        f'<wp:docPr id="{doc_pr_id}" name="Chart{doc_pr_id}"/>'
        f'<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f'<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f"<pic:nvPicPr><pic:cNvPr id=\"0\" name=\"chart\"/><pic:cNvPicPr/></pic:nvPicPr>"
        f"<pic:blipFill>"
        f'<a:blip r:embed="{rid}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        f"<a:stretch><a:fillRect/></a:stretch>"
        f"</pic:blipFill>"
        f"<pic:spPr>"
        f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{width_emu}" cy="{height_emu}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f"</pic:spPr>"
        f"</pic:pic></a:graphicData></a:graphic>"
        f"</wp:inline></w:drawing></w:r></w:p>"
    )


def _parse_data_url(data_url: str, index: int) -> tuple[str, bytes, str]:
    match = re.match(r"data:image/(png|jpeg|jpg);base64,(.+)", data_url)
    if not match:
        raise ValueError("Unsupported image data URL")
    ext = "jpg" if match.group(1) in {"jpeg", "jpg"} else "png"
    return f"chart-{index}.{ext}", base64.b64decode(match.group(2)), ext


def _document_xml(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{body}"
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        "</w:sectPr>"
        "</w:body></w:document>"
    )


def _root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/>'
        "</Relationships>"
    )


def _document_rels(images: list[tuple[str, bytes, str]]) -> str:
    rels = [
        '<Relationship Id="styles"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"'
        ' Target="styles.xml"/>'
    ]
    for i, (name, _, _) in enumerate(images, 1):
        rels.append(
            f'<Relationship Id="rId{i}"'
            f' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"'
            f' Target="media/{name}"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(rels)
        + "</Relationships>"
    )


def _content_types(images: list[tuple[str, bytes, str]]) -> str:
    defaults = [
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    if any(ext == "png" for _, _, ext in images):
        defaults.append('<Default Extension="png" ContentType="image/png"/>')
    if any(ext == "jpg" for _, _, ext in images):
        defaults.append('<Default Extension="jpg" ContentType="image/jpeg"/>')
    overrides = [
        '<Override PartName="/word/document.xml"'
        ' ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
        '<Override PartName="/word/styles.xml"'
        ' ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + "".join(defaults + overrides)
        + "</Types>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        "<w:name w:val=\"Normal\"/>"
        "</w:style>"
        '<w:style w:type="paragraph" w:styleId="Title">'
        "<w:name w:val=\"Title\"/>"
        "<w:rPr><w:b/><w:sz w:val=\"36\"/></w:rPr>"
        "</w:style>"
        '<w:style w:type="paragraph" w:styleId="Heading1">'
        "<w:name w:val=\"heading 1\"/>"
        "<w:rPr><w:b/><w:sz w:val=\"26\"/></w:rPr>"
        "</w:style>"
        "</w:styles>"
    )
