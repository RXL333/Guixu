from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from charset_normalizer import from_bytes

from guixu.domain.profiles import Coverage, Evidence, EvidenceLocator, FileProfile, ParseOutcome
from guixu.infrastructure.parsers.common import PARSER_VERSION, stratified_indices


MAX_TEXT_BYTES = 16 * 1024 * 1024


def _decode(path: Path) -> tuple[str, str, list[str]]:
    payload = path.read_bytes()[: MAX_TEXT_BYTES + 1]
    warnings = []
    if len(payload) > MAX_TEXT_BYTES:
        payload = payload[:MAX_TEXT_BYTES]
        warnings.append("TEXT_BYTE_LIMIT")
    match = from_bytes(payload).best()
    if match is None:
        raise UnicodeError("TEXT_DECODE_FAILED")
    return str(match), match.encoding or "unknown", warnings


def parse_text(path: Path, file_id: str, preset: str) -> ParseOutcome:
    del preset
    text, encoding, warnings = _decode(path)
    suffix = path.suffix.lower()
    metadata: dict[str, object] = {"encoding": encoding, "characters": len(text), "format": suffix.lstrip(".")}
    evidence: list[Evidence] = []
    lines = text.splitlines()
    if suffix == ".json":
        parsed = json.loads(text)
        metadata["json_root_type"] = type(parsed).__name__
        if isinstance(parsed, dict):
            metadata["top_level_keys"] = [str(key)[:100] for key in list(parsed)[:50]]
        sample = json.dumps(parsed, ensure_ascii=False, indent=2)[:12_000]
        evidence.append(Evidence(id="json-structure", kind="extracted_text", text=sample, locator=EvidenceLocator(field="json"), quality="high", origin="json"))
    elif suffix in {".csv", ".tsv"}:
        dialect = csv.excel_tab if suffix == ".tsv" else csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        rows = list(csv.reader(io.StringIO(text), dialect))
        metadata.update({"row_count": len(rows), "columns": len(rows[0]) if rows else 0, "delimiter": dialect.delimiter})
        for ordinal in stratified_indices(len(rows), 8):
            evidence.append(Evidence(id=f"row-{ordinal + 1}", kind="extracted_text", text=" | ".join(rows[ordinal])[:12_000], locator=EvidenceLocator(rows=[ordinal + 1]), quality="high", origin="csv"))
    else:
        paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]
        for ordinal in stratified_indices(len(paragraphs), 12):
            evidence.append(Evidence(id=f"paragraph-{ordinal + 1}", kind="extracted_text", text=paragraphs[ordinal][:12_000], locator=EvidenceLocator(paragraph=ordinal + 1), quality="high", origin="text"))
    summary = "\n".join(item.text for item in evidence)[:2000]
    profile = FileProfile(
        file_id=file_id, modality="text", metadata=metadata, content_summary=summary,
        summary_origin="deterministic" if summary else "none", evidence=evidence,
        coverage=Coverage(mode="full" if not warnings else "sampled", truncated=bool(warnings)),
        warnings=warnings, capabilities_used=["charset-normalizer", suffix.lstrip(".") or "text"], parser_version=PARSER_VERSION,
    )
    return ParseOutcome(status="partial" if warnings else "ready", profile=profile)

