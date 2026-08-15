"""Deterministic structured-data chunking before semantic prose chunking."""

from __future__ import annotations
import csv
import json
from io import StringIO
from langchain_core.documents import Document
from app.memory.token_counter import TokenCounter


def analyze_structure(text: str) -> dict:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (list, dict)):
            return {"structured": True, "format": "json", "data": parsed}
    except (ValueError, TypeError):
        pass
    lines = [line for line in text.splitlines() if line.strip()]
    try:
        rows = list(csv.reader(StringIO(text)))
        width = len(rows[0]) if rows else 0
        if (
            width >= 2
            and len(rows) > 2
            and sum(len(row) == width for row in rows) / len(rows) >= 0.8
        ):
            return {
                "structured": True,
                "format": "tabular",
                "headers": rows[0],
                "rows": rows[1:],
            }
    except csv.Error:
        pass
    if len(lines) >= 3 and any(line.lstrip().startswith("#") for line in lines):
        return {"structured": True, "format": "headed_text"}
    return {"structured": False, "format": "unstructured"}


def _token_windows(
    text: str, metadata: dict, strategy: str, token_size: int = 500, overlap: int = 75
):
    """Deterministic tokenizer windows; never calls an embedding model."""
    return [
        Document(
            page_content=window,
            metadata={
                **metadata,
                "chunking_strategy": strategy,
                "token_overlap": overlap,
            },
        )
        for window in TokenCounter().windows(text, token_size, overlap)
        if window.strip()
    ]


def structured_chunks(
    text: str, metadata: dict, max_rows: int = 25, overlap_rows: int = 2
):
    analysis = analyze_structure(text)
    if not analysis["structured"]:
        return None
    if analysis["format"] == "tabular":
        headers, rows, chunks, start = analysis["headers"], analysis["rows"], [], 0
        while start < len(rows):
            group = rows[start : start + max_rows]
            content = (
                " | ".join(headers) + "\n" + "\n".join(" | ".join(row) for row in group)
            )
            chunks.extend(
                _token_windows(
                    content, {**metadata, "headers": headers}, "structured_token_window"
                )
            )
            start += max_rows - overlap_rows
        return chunks
    if analysis["format"] == "json":
        records = (
            analysis["data"]
            if isinstance(analysis["data"], list)
            else [analysis["data"]]
        )
        chunks = []
        for record in records:
            chunks.extend(
                _token_windows(
                    json.dumps(record, ensure_ascii=False),
                    metadata,
                    "json_token_window",
                )
            )
        return chunks
    sections, current = [], []
    for line in text.splitlines():
        if line.lstrip().startswith("#") and current:
            sections.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        sections.append("\n".join(current))
    chunks = []
    for section in sections:
        chunks.extend(_token_windows(section, metadata, "heading_token_window"))
    return chunks
