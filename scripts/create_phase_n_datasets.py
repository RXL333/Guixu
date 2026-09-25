from __future__ import annotations

import hashlib
import json
import math
import struct
import wave
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "test-workspaces" / "phase-n-datasets"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(manifest: list[dict[str, object]], dataset: str, path: Path, **metadata: object) -> None:
    manifest.append({
        "dataset": dataset,
        "relative_path": path.relative_to(OUTPUT).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        **metadata,
    })


def image_fixture(path: Path, category: str, index: int, variant: int = 0) -> None:
    palette = {
        "人物": (68, 120, 170), "风景": (56, 142, 92), "建筑": (115, 120, 132),
        "夜景": (22, 35, 74), "美食": (184, 106, 52), "截图": (225, 230, 238),
        "文档照片": (214, 205, 178), "难以判断": (122, 94, 140),
    }
    color = palette[category]
    image = Image.new("RGB", (640, 420), color)
    draw = ImageDraw.Draw(image)
    if category == "人物":
        draw.ellipse((250, 80, 390, 220), fill=(230, 190, 155))
        draw.rectangle((215, 215, 425, 390), fill=(35 + variant * 4, 70, 125))
    elif category == "风景":
        draw.polygon(((0, 330), (180, 110), (320, 330)), fill=(72, 92, 110))
        draw.polygon(((220, 330), (440, 90), (640, 330)), fill=(92, 112, 125))
        draw.rectangle((0, 330, 640, 420), fill=(35, 115, 158))
    elif category == "建筑":
        draw.rectangle((165, 80, 475, 400), fill=(190, 194, 200))
        for row in range(4):
            for col in range(4):
                x, y = 195 + col * 68, 110 + row * 64
                draw.rectangle((x, y, x + 35, y + 40), fill=(55, 89, 122))
    elif category == "夜景":
        for star in range(20):
            x = (star * 97 + index * 13) % 620 + 10
            y = (star * 53 + variant * 7) % 220 + 10
            draw.ellipse((x, y, x + 4, y + 4), fill=(250, 235, 150))
        draw.rectangle((0, 300, 640, 420), fill=(10, 15, 30))
    elif category == "美食":
        draw.ellipse((150, 70, 490, 390), fill=(240, 235, 220))
        draw.ellipse((205, 125, 435, 350), fill=(205, 85, 50))
        draw.ellipse((280, 180, 355, 255), fill=(245, 210, 70))
    elif category == "截图":
        draw.rectangle((55, 45, 585, 375), fill=(250, 250, 252), outline=(80, 100, 130), width=4)
        for line in range(7):
            draw.rectangle((90, 85 + line * 38, 510 - line * 11, 101 + line * 38), fill=(130, 150, 180))
    elif category == "文档照片":
        draw.polygon(((135, 40), (535, 70), (500, 390), (105, 350)), fill=(248, 246, 235))
        for line in range(9):
            draw.line((165, 105 + line * 25, 465, 125 + line * 24), fill=(80, 80, 75), width=3)
    else:
        for shape in range(18):
            x = (shape * 71 + index * 19) % 580
            y = (shape * 43 + variant * 11) % 360
            draw.rectangle((x, y, x + 45, y + 35), outline=(220, 210, 230), width=3)
    draw.text((18, 388), f"Guixu synthetic {category} {index:03d}", fill=(255, 255, 255), font=ImageFont.load_default())
    image.save(path, quality=92)


def build_dataset_a(manifest: list[dict[str, object]]) -> None:
    target = OUTPUT / "dataset-a-images"
    target.mkdir(parents=True)
    categories = ("人物", "风景", "建筑", "夜景", "美食", "截图", "文档照片", "难以判断")
    for index in range(120):
        category = categories[index % len(categories)]
        path = target / f"image-{index + 1:03d}-{category}.jpg"
        image_fixture(path, category, index + 1, index % 5)
        record(manifest, "A", path, expected_topic=category, kind="image", duplicate_of=None)
    # Exact duplicates and near-similar images are explicit cases, not accidental collisions.
    for index in range(8):
        source = target / f"image-{index + 1:03d}-{categories[index % len(categories)]}.jpg"
        duplicate = target / f"duplicate-{index + 1:02d}.jpg"
        duplicate.write_bytes(source.read_bytes())
        record(manifest, "A", duplicate, expected_topic=categories[index % len(categories)],
               kind="image", duplicate_of=source.name)


def build_dataset_b(manifest: list[dict[str, object]]) -> None:
    target = OUTPUT / "dataset-b-study"
    target.mkdir(parents=True)
    courses = ("计算机网络", "数据结构", "高等数学", "建筑设计")
    kinds = ("课件", "实验", "作业", "笔记")
    for course_index, course in enumerate(courses, start=1):
        for kind_index, kind in enumerate(kinds, start=1):
            stem = f"{course}-{kind}"
            txt = target / f"{stem}.txt"
            txt.write_text(f"课程：{course}\n资料类型：{kind}\n这是归序 1.0 的合成验收材料。\n", encoding="utf-8")
            record(manifest, "B", txt, expected_course=course, expected_kind=kind, kind="text")
            md = target / f"{stem}.md"
            md.write_text(f"# {course} {kind}\n\n- 合成资料\n- 不包含个人信息\n", encoding="utf-8")
            record(manifest, "B", md, expected_course=course, expected_kind=kind, kind="markdown")

        document = Document()
        document.add_heading(f"{course} 课程笔记", 1)
        document.add_paragraph("本文件为 Guixu 1.0 验收自动生成的课程笔记。")
        docx = target / f"{course}-笔记.docx"
        document.save(docx)
        record(manifest, "B", docx, expected_course=course, expected_kind="笔记", kind="docx")

        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = f"{course} 课件"
        slide.placeholders[1].text = "Guixu 1.0 synthetic acceptance material"
        pptx = target / f"{course}-课件.pptx"
        deck.save(pptx)
        record(manifest, "B", pptx, expected_course=course, expected_kind="课件", kind="pptx")

        pdf = target / f"{course}-作业.pdf"
        pdf_canvas = canvas.Canvas(str(pdf))
        pdf_canvas.drawString(72, 760, f"{course} homework / synthetic acceptance material")
        pdf_canvas.save()
        record(manifest, "B", pdf, expected_course=course, expected_kind="作业", kind="pdf")

        image = target / f"{course}-实验照片.jpg"
        image_fixture(image, "文档照片", course_index + 200)
        record(manifest, "B", image, expected_course=course, expected_kind="实验", kind="image")


def build_dataset_c(manifest: list[dict[str, object]]) -> None:
    target = OUTPUT / "dataset-c-multimodal"
    target.mkdir(parents=True)
    image = target / "旅行照片.jpg"
    image_fixture(image, "风景", 301)
    record(manifest, "C", image, expected_topic="旅行", kind="image")

    text_path = target / "会议记录.txt"
    text_path.write_text("项目会议记录。讨论里程碑、风险和后续行动。", encoding="utf-8")
    record(manifest, "C", text_path, expected_topic="工作", kind="text")

    pdf = target / "研究报告.pdf"
    pdf_canvas = canvas.Canvas(str(pdf))
    pdf_canvas.drawString(72, 760, "Synthetic research report for Guixu acceptance")
    pdf_canvas.save()
    record(manifest, "C", pdf, expected_topic="学习", kind="pdf")

    doc = Document()
    doc.add_heading("项目计划", 1)
    doc.add_paragraph("合成 Office 文件，不包含用户数据。")
    docx = target / "项目计划.docx"
    doc.save(docx)
    record(manifest, "C", docx, expected_topic="工作", kind="docx")

    book = Workbook()
    sheet = book.active
    sheet.append(["任务", "状态"])
    sheet.append(["验收", "进行中"])
    xlsx = target / "任务清单.xlsx"
    book.save(xlsx)
    record(manifest, "C", xlsx, expected_topic="工作", kind="xlsx")

    wav_path = target / "纯音调.wav"
    with wave.open(str(wav_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        frames = bytearray()
        for sample in range(8000):
            value = int(4500 * math.sin(2 * math.pi * 220 * sample / 8000))
            frames.extend(struct.pack("<h", value))
        audio.writeframes(bytes(frames))
    record(manifest, "C", wav_path, expected_topic="unknown", kind="audio", expected_support="partial_metadata")

    # A deterministic placeholder documents current video behavior without
    # pretending that an invalid container is supported.
    video_note = target / "VIDEO_FIXTURE_README.txt"
    video_note.write_text(
        "Video runtime acceptance requires a generated MP4 and available ffmpeg/ffprobe. "
        "The current 1.0 package does not bundle those components.\n",
        encoding="utf-8",
    )
    record(manifest, "C", video_note, expected_topic="limitation", kind="video_fixture_note",
           expected_support="partial_or_unavailable")


def build_dataset_d(manifest: list[dict[str, object]]) -> None:
    target = OUTPUT / "dataset-d-pressure"
    target.mkdir(parents=True)
    for count in (500, 1000, 5000):
        directory = target / str(count)
        directory.mkdir()
        for index in range(count):
            path = directory / f"fixture-{index:05d}.txt"
            path.write_text(f"Guixu pressure fixture {count}/{index}\n", encoding="utf-8")
        sentinel = directory / "manifest-sentinel.json"
        sentinel.write_text(json.dumps({"file_count_excluding_sentinel": count}), encoding="utf-8")
        record(manifest, "D", sentinel, expected_count=count, kind="pressure_manifest")


def main() -> None:
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty dataset root: {OUTPUT}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    build_dataset_a(manifest)
    build_dataset_b(manifest)
    build_dataset_c(manifest)
    build_dataset_d(manifest)
    document = {
        "schema_version": 1,
        "generated_by": "scripts/create_phase_n_datasets.py",
        "license": "CC0-1.0; entirely synthetic; no user or third-party content",
        "datasets": {
            "A": "128 synthetic image files covering eight topics, duplicates and similar variants",
            "B": "56 synthetic study files across four courses and four material kinds",
            "C": "safe multimodal parser fixtures; audio/video are accepted only at current partial capability",
            "D": "500/1000/5000 small-file pressure directories",
        },
        "record_count": len(manifest),
        "records": manifest,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "LICENSE.txt").write_text(
        "All files in this directory are generated synthetic fixtures dedicated under CC0-1.0.\n",
        encoding="utf-8",
    )
    print(json.dumps({"root": str(OUTPUT), "records": len(manifest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
