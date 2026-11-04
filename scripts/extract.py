#!/usr/bin/env python3
"""把 PDF / Word / 网页 / Markdown / 纯文本统一抽成纯文本 JSON。

用法：
    python scripts/extract.py <文件路径或URL> [-o out.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MIN_CHARS = 100
SHORT_CHARS = 300


def normalize(text: str) -> str:
    """清理排版噪声：合并空白、去掉孤立的页码行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t　]+", " ", text)
    # 去掉只有页码/数字的行
    text = re.sub(r"\n\s*\d{1,4}\s*\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(path: Path) -> tuple[str, str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")

    title = ""
    meta_title = (reader.metadata or {}).get("/Title") if reader.metadata else None
    if meta_title:
        title = str(meta_title).strip()

    text = "\n".join(pages)
    if not title:
        # 用正文第一行非空且不太长的行当标题
        for line in text.splitlines():
            line = line.strip()
            if 3 <= len(line) <= 60:
                title = line
                break
    return title, text


def extract_docx(path: Path) -> tuple[str, str]:
    import docx

    doc = docx.Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    text = "\n".join(parts)

    title = ""
    for p in doc.paragraphs:
        if p.text.strip():
            title = p.text.strip()
            break
    return title, text


def extract_url(url: str) -> tuple[str, str]:
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # 优先正文容器，其次全文
    node = None
    for selector in ("article", "main", "#content", ".content", ".article", "div.post"):
        node = soup.select_one(selector)
        if node and len(node.get_text(strip=True)) > MIN_CHARS:
            break
    if node is None:
        node = soup.body or soup

    text = node.get_text(separator="\n")
    return title, text


def extract_file(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix in (".docx", ".doc"):
        return extract_docx(path)
    if suffix in (".md", ".markdown", ".txt", ".text", ""):
        raw = path.read_text(encoding="utf-8", errors="replace")
        title = ""
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
            if line:
                title = line[:60]
                break
        return title, raw
    raise ValueError(f"不支持的文件类型: {suffix}")


def extract(source: str) -> dict:
    is_url = bool(re.match(r"^https?://", source, re.I))
    if is_url:
        title, text = extract_url(source)
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {source}")
        title, text = extract_file(path)

    text = normalize(text)
    char_count = len(re.sub(r"\s", "", text))

    warnings = []
    if char_count < MIN_CHARS:
        warnings.append(
            f"正文只有 {char_count} 字。若为扫描版 PDF，需要先 OCR；"
            "否则请确认文件是否正确。"
        )
    elif char_count < SHORT_CHARS:
        warnings.append(f"正文只有 {char_count} 字，内容偏少，小品可能展开不足。")

    return {
        "title": title or Path(source).stem,
        "source": source,
        "char_count": char_count,
        "warnings": warnings,
        "text": text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="抽取 PDF/Word/网页/文本 为纯文本 JSON")
    parser.add_argument("source", help="文件路径或 http(s) URL")
    parser.add_argument("-o", "--out", help="输出 JSON 路径（默认打印到 stdout）")
    parser.add_argument("--text-only", action="store_true", help="只输出正文，便于人工检查")
    args = parser.parse_args()

    try:
        result = extract(args.source)
    except Exception as exc:
        print(f"提取失败: {exc}", file=sys.stderr)
        return 1

    for w in result["warnings"]:
        print(f"[警告] {w}", file=sys.stderr)

    if args.text_only:
        print(result["text"])
        return 0

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(f"已写入 {args.out}（{result['char_count']} 字）", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
