#!/usr/bin/env python3
"""Offline {{key}} fill engine (demo / 备胎线).

Architecture: form JSON → replace {{key}} in docx XML → filled.docx + preview.html.

This is a minimal engine compatible with python-docx / lxml-style {{key}}
placeholders. The official 37-template pack + production engine will be
dropped in a later PR from the software package. Do not call this via dsh.

stdlib only (zipfile + xml). Optional: lxml / python-docx if installed.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

MUSTACHE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")
MUSTACHE_SPLIT = re.compile(r"\{\{(.*?)\}\}", re.S)
W_T = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""

DEMO_TEMPLATES = {
    "2.7_设备开箱检验记录.docx": {
        "title": "设备开箱检验记录",
        "lines": [
            "项目名称：{{project_name}}",
            "建设单位：{{owner}}",
            "施工单位：{{contractor}}",
            "合同号：{{contract_no}}",
            "设备名称：{{device_name}}",
            "规格型号：{{device_model}}",
            "开箱日期：{{inspect_date}}",
            "检验人：{{inspector}}",
            "检验结论：{{inspect_result}}",
        ],
    },
    "6.2_竣工验收报告.docx": {
        "title": "竣工验收报告",
        "lines": [
            "项目名称：{{project_name}}",
            "建设单位：{{owner}}",
            "监理单位：{{supervisor}}",
            "施工单位：{{contractor}}",
            "合同号：{{contract_no}}",
            "验收日期：{{accept_date}}",
            "验收结论：{{accept_conclusion}}",
            "建设概况：{{summary}}",
        ],
    },
    "8.1_总封面.docx": {
        "title": "验收资料总封面",
        "lines": [
            "{{volume_title}}",
            "项目名称：{{project_name}}",
            "建设单位：{{owner}}",
            "施工单位：{{contractor}}",
            "阶段：{{phase}}",
            "文号：{{doc_no}}",
            "日期：{{cover_date}}",
        ],
    },
}


def collapse_split_mustache(xml: str) -> str:
    """Join {{ ... }} even when Word split the placeholder across w:t runs."""

    def repl(match: re.Match[str]) -> str:
        inner = re.sub(r"<[^>]+>", "", match.group(1))
        inner = inner.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        return "{{" + inner.strip() + "}}"

    return MUSTACHE_SPLIT.sub(repl, xml)


def fill_xml(xml: str, data: dict) -> tuple[str, list[str]]:
    xml = collapse_split_mustache(xml)

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in data and data[key] is not None:
            return escape(str(data[key]))
        return match.group(0)

    filled = MUSTACHE.sub(repl, xml)
    leftover = sorted(set(MUSTACHE.findall(filled)))
    return filled, leftover


def extract_preview_text(document_xml: str) -> list[str]:
    return [t for t in W_T.findall(document_xml) if t.strip()]


def write_preview_html(path: Path, title: str, lines: list[str], residual: list[str]) -> None:
    body = "".join(f"<p>{html.escape(line)}</p>" for line in lines) or "<p>（空文档）</p>"
    warn = ""
    if residual:
        keys = "、".join("{{" + k + "}}" for k in residual)
        warn = f'<div class="residual">残留占位符：{html.escape(keys)}</div>'
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif; background: #f4efe6; margin: 0; padding: 24px; color: #1c140c; }}
    .paper {{ background: #fff; border: 1px solid #e0d3c0; padding: 36px 40px; max-width: 720px; margin: 0 auto; min-height: 400px; }}
    h1 {{ font-size: 20px; margin: 0 0 18px; }}
    p {{ margin: 8px 0; line-height: 1.6; }}
    .residual {{ background: #fde8e6; color: #8d2c24; padding: 8px 10px; border-radius: 8px; margin-bottom: 16px; }}
  </style>
</head>
<body>
  <div class="paper">
    <h1>{html.escape(title)}</h1>
    {warn}
    {body}
  </div>
</body>
</html>
""",
        encoding="utf-8",
    )


def fill_docx(template: Path, data: dict, out_path: Path, preview_path: Path | None) -> dict:
    leftovers: set[str] = set()
    preview_lines: list[str] = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template, "r") as zin, zipfile.ZipFile(out_path, "w") as zout:
        for info in zin.infolist():
            raw = zin.read(info.filename)
            if info.filename.startswith("word/") and info.filename.endswith(".xml"):
                text = raw.decode("utf-8")
                filled, left = fill_xml(text, data)
                leftovers.update(left)
                raw = filled.encode("utf-8")
                if info.filename.endswith("document.xml"):
                    preview_lines = extract_preview_text(filled)
            zout.writestr(info, raw)
    if preview_path:
        write_preview_html(preview_path, template.stem, preview_lines, sorted(leftovers))
    return {
        "ok": True,
        "residual_keys": sorted(leftovers),
        "filled_path": str(out_path),
        "preview_path": str(preview_path) if preview_path else "",
        "message": "ok" if not leftovers else "residual placeholders remain",
    }


def w_p(text: str, bold: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return (
        f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
    )


def make_docx(path: Path, title: str, lines: list[str]) -> None:
    body = w_p(title, bold=True) + "".join(w_p(line) for line in lines)
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>
  </w:body>
</w:document>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", RELS)
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
        zf.writestr("word/document.xml", document)


def cmd_make_demo(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, spec in DEMO_TEMPLATES.items():
        dest = out_dir / name
        make_docx(dest, spec["title"], spec["lines"])
        written.append(str(dest))
    readme = out_dir / "README.md"
    readme.write_text(
        "# 演示模板（备胎线 v1）\n\n"
        "本目录仅含 3 份 `{{key}}` 演示模板，用于打通「表单 → Python fill_engine → 只读预览」。\n\n"
        "- `2.7_设备开箱检验记录.docx`\n"
        "- `6.2_竣工验收报告.docx`\n"
        "- `8.1_总封面.docx`\n\n"
        "完整 37 套官方模板 + 生产填充引擎将在下一 PR 从软件包导入，不要在本目录假装已齐套。\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "written": written}, ensure_ascii=False))


def cmd_fill(args: argparse.Namespace) -> None:
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    report = fill_docx(
        Path(args.template),
        data,
        Path(args.out),
        Path(args.preview) if args.preview else None,
    )
    print(json.dumps(report, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline {{key}} fill engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fill = sub.add_parser("fill")
    p_fill.add_argument("--template", required=True)
    p_fill.add_argument("--data", required=True)
    p_fill.add_argument("--out", required=True)
    p_fill.add_argument("--preview")

    p_demo = sub.add_parser("make-demo")
    p_demo.add_argument("--out", default="templates")

    args = parser.parse_args()
    if args.cmd == "make-demo":
        cmd_make_demo(Path(args.out))
        return 0
    if args.cmd == "fill":
        cmd_fill(args)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
