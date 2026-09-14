from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave
from pathlib import Path

from guixu.domain.profiles import Coverage, Evidence, EvidenceLocator, FileProfile, ParseOutcome
from guixu.infrastructure.parsers.common import PARSER_VERSION


def _ffprobe(path: Path) -> dict | None:
    executable = shutil.which("ffprobe")
    if not executable:
        return None
    completed = subprocess.run(
        [executable, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=20, shell=False, check=False,
        env={**os.environ, "PATH": str(Path(executable).parent), "NO_PROXY": "*", "no_proxy": "*"},
    )
    if completed.returncode != 0:
        raise ValueError("FFPROBE_FAILED")
    return json.loads(completed.stdout)


def parse_media(path: Path, file_id: str, modality: str, preset: str) -> ParseOutcome:
    del preset
    warnings = []; metadata: dict[str, object] = {}; evidence = []
    probed = _ffprobe(path)
    if probed is not None:
        format_data = probed.get("format", {})
        duration = float(format_data.get("duration") or 0)
        metadata = {"format_name": format_data.get("format_name"), "duration_sec": duration, "bit_rate": format_data.get("bit_rate"), "streams": [{"codec_type": stream.get("codec_type"), "codec_name": stream.get("codec_name"), "width": stream.get("width"), "height": stream.get("height"), "sample_rate": stream.get("sample_rate")} for stream in probed.get("streams", [])]}
        evidence.append(Evidence(id="media-metadata", kind="metadata", text=f"时长 {duration:.3f} 秒；流 {len(metadata['streams'])} 个", locator=EvidenceLocator(field="format"), quality="high", origin="ffprobe"))
        capabilities = ["ffprobe"]
    elif path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as audio:
            duration = audio.getnframes() / max(audio.getframerate(), 1)
            metadata = {"duration_sec": duration, "channels": audio.getnchannels(), "sample_rate": audio.getframerate(), "sample_width": audio.getsampwidth()}
        evidence.append(Evidence(id="wav-metadata", kind="metadata", text=f"WAV 时长 {duration:.3f} 秒，{metadata['channels']} 声道", locator=EvidenceLocator(field="wav-header"), quality="high", origin="wave"))
        warnings.append("FFPROBE_COMPONENT_MISSING")
        capabilities = ["wave"]
    else:
        duration = None
        warnings.append("FFPROBE_COMPONENT_MISSING")
        capabilities = []
    if modality == "audio":
        warnings.append("ASR_COMPONENT_MISSING")
    else:
        warnings.extend(["FFMPEG_FRAME_EXTRACTION_MISSING", "ASR_COMPONENT_MISSING"])
    profile = FileProfile(file_id=file_id, modality=modality, metadata=metadata, content_summary="", summary_origin="none", evidence=evidence, coverage=Coverage(mode="metadata_only", total_duration_sec=duration), warnings=warnings, capabilities_used=capabilities, parser_version=PARSER_VERSION)
    return ParseOutcome(status="partial", profile=profile)
