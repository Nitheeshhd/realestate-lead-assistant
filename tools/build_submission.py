#!/usr/bin/env python3
"""Render TDD.md to a PDF using an installed Chromium browser and package the two deliverables."""

import html
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
INLINE_TOKEN = re.compile(r"(!?\[[^\]]*\]\([^)]+\)|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)")
TABLE_RULE = re.compile(r"\|?[\s:|-]+\|?")


def inline(text):
    parts = []
    for token in INLINE_TOKEN.split(text):
        if not token:
            continue
        if token.startswith("!["):
            match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", token)
            alt, src = match.groups()
            parts.append(f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">')
        elif token.startswith("["):
            match = re.fullmatch(r"\[([^\]]*)\]\(([^)]+)\)", token)
            label, href = match.groups()
            parts.append(f'<a href="{html.escape(href, quote=True)}">{inline(label)}</a>')
        elif token.startswith("`"):
            parts.append(f"<code>{html.escape(token[1:-1])}</code>")
        elif token.startswith("**"):
            parts.append(f"<strong>{inline(token[2:-2])}</strong>")
        elif token.startswith("*"):
            parts.append(f"<em>{inline(token[1:-1])}</em>")
        else:
            parts.append(html.escape(token))
    return "".join(parts)


def render_markdown(text):
    lines = text.splitlines()
    out = []
    paragraph = []
    list_tag = None
    index = 0

    def flush_paragraph():
        if paragraph:
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            flush_paragraph()
            close_list()
            code = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index])
                index += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
        elif line.startswith("|"):
            flush_paragraph()
            close_list()
            rows = []
            while index < len(lines) and lines[index].startswith("|"):
                row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not TABLE_RULE.fullmatch(lines[index].strip()) or "-" not in lines[index]:
                    rows.append(row)
                index += 1
            if rows:
                out.append("<table><thead><tr>")
                out.extend(f"<th>{inline(cell)}</th>" for cell in rows[0])
                out.append("</tr></thead>")
                if len(rows) > 1:
                    out.append("<tbody>")
                    for row in rows[1:]:
                        out.append("<tr>")
                        out.extend(f"<td>{inline(cell)}</td>" for cell in row)
                        out.append("</tr>")
                    out.append("</tbody>")
                out.append("</table>")
            continue
        elif line.startswith("#"):
            flush_paragraph()
            close_list()
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if match:
                level, title = len(match.group(1)), match.group(2)
                out.append(f"<h{level}>{inline(title)}</h{level}>")
        elif re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            flush_paragraph()
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            needed = "ol" if ordered else "ul"
            if list_tag != needed:
                close_list()
                list_tag = needed
                out.append(f"<{list_tag}>")
            item = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line)
            out.append(f"<li>{inline(item)}</li>")
        else:
            close_list()
            if line.strip():
                paragraph.append(line.strip())
            else:
                flush_paragraph()
        index += 1

    flush_paragraph()
    close_list()
    return "\n".join(out)


def browser_executable():
    configured = os.environ.get("BROWSER_BIN")
    if configured:
        return configured
    candidates = ("msedge", "google-chrome", "chromium", "chromium-browser")
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    if os.name == "nt":
        for candidate in (
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        ):
            if candidate.exists():
                return str(candidate)
    raise RuntimeError("Install Microsoft Edge or Chromium, or set BROWSER_BIN to its executable path.")


def main():
    tdd = (ROOT / "TDD.md").read_text(encoding="utf-8")
    body = render_markdown(tdd)
    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8">
<base href="{ROOT.as_uri()}/">
<style>
@page {{ size: A4; margin: 18mm 16mm; }}
body {{ color:#17231b; font:10pt/1.48 Arial,sans-serif; }}
h1 {{ font-size:22pt; color:#0b1510; border-bottom:2px solid #2dbe4e; padding-bottom:7pt; }}
h2 {{ font-size:15pt; margin-top:20pt; color:#0b1510; page-break-after:avoid; }}
h3 {{ font-size:12pt; page-break-after:avoid; }}
p,li {{ orphans:3; widows:3; }}
table {{ border-collapse:collapse; width:100%; margin:9pt 0 14pt; font-size:8.5pt; page-break-inside:auto; }}
thead {{ display:table-header-group; }}
th {{ background:#e5eee7; text-align:left; }}
th,td {{ border:1px solid #cbd8cf; padding:5pt; vertical-align:top; }}
tr {{ page-break-inside:avoid; }}
pre {{ white-space:pre-wrap; background:#f2f6f3; padding:8pt; font:8pt/1.35 Consolas,monospace; }}
code {{ font:8.5pt Consolas,monospace; background:#f2f6f3; }}
img {{ display:block; max-width:100%; max-height:220mm; object-fit:contain; margin:8pt auto 14pt; page-break-inside:avoid; }}
a {{ color:#126b30; }}
hr {{ border:0; border-top:1px solid #cbd8cf; }}
</style></head><body>{body}</body></html>"""

    pdf_path = ROOT / "TDD.pdf"
    zip_path = ROOT / "submission.zip"
    with tempfile.TemporaryDirectory(prefix="aangan-doc-") as temp:
        html_path = Path(temp) / "TDD.html"
        profile = Path(temp) / "browser-profile"
        html_path.write_text(html_doc, encoding="utf-8")
        command = [
            browser_executable(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}", html_path.as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode or not pdf_path.exists():
            raise RuntimeError(f"Browser PDF rendering failed: {result.stderr or result.stdout}")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(pdf_path, "TDD.pdf")
        archive.write(ROOT / "deployment.md", "deployment.md")
    size = zip_path.stat().st_size
    if size >= 25 * 1024 * 1024:
        zip_path.unlink()
        raise RuntimeError(f"submission.zip is {size} bytes; it must be smaller than 25 MB.")
    print(f"Created {pdf_path} ({pdf_path.stat().st_size:,} bytes)")
    print(f"Created {zip_path} ({size:,} bytes); contents: TDD.pdf, deployment.md")


if __name__ == "__main__":
    main()
