#!/usr/bin/env python3
"""Prepare one overview and bounded, high-resolution row-band views per PDF page."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

try:
    import fitz
    from PIL import Image
except ImportError as exc:
    raise SystemExit("需要 PyMuPDF、Pillow: pip install pymupdf pillow") from exc

MAX_PAGES_PER_PDF = 50
MAX_IMAGE_SIDE = 2200
DETAIL_DPI = 300
MAX_DATA_PARTITIONS = 3
MAX_VIEWS_PER_PAGE = 1 + MAX_DATA_PARTITIONS
CONTENT_THRESHOLD = 6
CONTENT_GAP_PX = 20
PARTITION_OVERLAP = 0.08
PREPROCESS_VERSION = 3
DESKEW_MIN_ANGLE = 0.35
DESKEW_MAX_ANGLE = 2.0
DESKEW_STEP = 0.1
DESKEW_MIN_SCORE_GAIN = 0.01


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _preprocess_config() -> dict:
    return {
        "version": PREPROCESS_VERSION,
        "detail_dpi": DETAIL_DPI,
        "max_image_side": MAX_IMAGE_SIDE,
        "max_data_partitions": MAX_DATA_PARTITIONS,
        "content_threshold": CONTENT_THRESHOLD,
        "content_gap_px": CONTENT_GAP_PX,
        "partition_overlap": PARTITION_OVERLAP,
        "deskew": {
            "algorithm": "bounded_horizontal_projection_v1",
            "minimum_angle_degrees": DESKEW_MIN_ANGLE,
            "maximum_angle_degrees": DESKEW_MAX_ANGLE,
            "step_degrees": DESKEW_STEP,
            "minimum_score_gain": DESKEW_MIN_SCORE_GAIN,
        },
    }


def _preprocess_config_sha256() -> str:
    raw = json.dumps(_preprocess_config(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _write_runtime_record(workdir: Path, event: dict) -> None:
    path = workdir / ".attendance-runtime.json"
    records = {"schema_version": 1, "events": []}
    if path.exists():
        records = json.loads(path.read_text(encoding="utf-8"))
        if records.get("schema_version") != 1 or not isinstance(records.get("events"), list):
            raise ValueError(".attendance-runtime.json 格式无效")
    records["events"].append(event)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=workdir, prefix=".runtime-", suffix=".tmp", delete=False) as tmp:
            temp_path = Path(tmp.name)
            tmp.write(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _cached_result(inputs: list[Path], workdir: Path, started_ns: int) -> dict | None:
    manifest_path = workdir / "attendance-manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest.get("documents")
    expected_sources = [path.expanduser().resolve() for path in inputs]
    if not isinstance(documents, list) or [Path(doc.get("source", "")).resolve() for doc in documents] != expected_sources:
        raise ValueError("当前任务已存在不同的 PDF 清单；不支持追加或替换上传")
    if manifest.get("preprocess_version") != PREPROCESS_VERSION:
        raise ValueError("当前任务图片使用旧预处理版本；为避免混用视图，请在新任务工作目录中预处理")
    if manifest.get("view_schema_version") != PREPROCESS_VERSION:
        raise ValueError("当前任务视图结构版本不匹配；请在新任务工作目录中预处理")
    if (manifest.get("preprocess_config_sha256") != _preprocess_config_sha256()
            or manifest.get("preprocess_config") != _preprocess_config()):
        raise ValueError("当前任务预处理参数已变化；为避免复用旧视图，请在新任务工作目录中预处理")
    for document in documents:
        if document.get("source_sha256") != _sha256(Path(document["source"])):
            raise ValueError("原始 PDF 已变化；请在新任务中重新预处理")
        for page in document.get("pages", []):
            for view in page.get("views", []):
                image = Path(view.get("image", ""))
                resolved_image = image.resolve()
                if (image.is_symlink() or not resolved_image.is_relative_to(workdir.resolve())
                        or not resolved_image.is_file() or _sha256(resolved_image) != view.get("image_sha256")):
                    raise ValueError(f"缓存视图缺失或摘要不一致: {view.get('view_id')}")
    total_pages = sum(len(document.get("pages", [])) for document in documents)
    total_views = sum(len(page.get("views", [])) for document in documents for page in document.get("pages", []))
    elapsed_ms = round((time.perf_counter_ns() - started_ns) / 1_000_000, 3)
    _write_runtime_record(workdir, {
        "stage": "pdf_prepare",
        "elapsed_ms": elapsed_ms,
        "clock": "time.perf_counter_ns",
        "pdf_count": len(documents),
        "page_count": total_pages,
        "rendered_page_images": 0,
        "reused_page_images": total_pages,
        "rendered_view_images": 0,
        "reused_view_images": total_views,
        "overview_view_count": 0,
        "row_partition_view_count": 0,
        "preprocess_status": "cached_manifest_reused",
    })
    return {
        "manifest": str(manifest_path.resolve()),
        "total_pages": total_pages,
        "documents": documents,
        "preprocess_elapsed_ms": elapsed_ms,
        "rendered_page_images": 0,
        "reused_page_images": total_pages,
        "rendered_view_images": 0,
        "reused_view_images": total_views,
        "cached": True,
    }


def _alignment_score(image: Image.Image, angle: float) -> float:
    width = 480
    height = max(1, round(image.height * width / image.width))
    gray = image.convert("L").resize((width, height), Image.Resampling.BILINEAR)
    rotated = gray.rotate(angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=255)
    pixels = rotated.point(lambda value: 0 if value < 180 else 255).tobytes()
    x0, x1 = int(width * 0.04), int(width * 0.96)
    y0, y1 = int(height * 0.05), int(height * 0.95)
    row_width = x1 - x0
    score = 0
    for y in range(y0, y1):
        count = pixels[y * width + x0:y * width + x1].count(0)
        score += count * count
    return score / max(1, (y1 - y0) * row_width * row_width)


def _deskew(image: Image.Image) -> tuple[Image.Image, dict]:
    source_size = list(image.size)
    try:
        angles = [round(step * DESKEW_STEP, 1) for step in range(
            round(-DESKEW_MAX_ANGLE / DESKEW_STEP),
            round(DESKEW_MAX_ANGLE / DESKEW_STEP) + 1,
        )]
        scores = [(angle, _alignment_score(image, angle)) for angle in angles]
        best_angle, best_score = max(scores, key=lambda item: item[1])
        zero_score = next(score for angle, score in scores if angle == 0)
        gain = (best_score - zero_score) / zero_score if zero_score else 0.0
        at_limit = abs(best_angle) >= DESKEW_MAX_ANGLE
        above_minimum = abs(best_angle) >= DESKEW_MIN_ANGLE
        reliable = above_minimum and zero_score > 0 and gain >= DESKEW_MIN_SCORE_GAIN and not at_limit
        if abs(best_angle) < DESKEW_MIN_ANGLE:
            reason = "angle_below_threshold"
        elif at_limit:
            reason = "angle_exceeds_safe_limit"
        elif not reliable:
            reason = "low_detection_confidence"
        else:
            reason = None
        if not reliable:
            return image, {
                "detected_angle_degrees": best_angle,
                "correction_angle_degrees": 0.0,
                "applied": False,
                "confidence": round(max(0.0, min(1.0, gain)), 4),
                "reason": reason,
                "source_size": source_size,
                "output_size": source_size,
                "algorithm": "bounded_horizontal_projection_v1",
            }
        corrected = image.rotate(best_angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
        return corrected, {
            "detected_angle_degrees": best_angle,
            "correction_angle_degrees": best_angle,
            "applied": True,
            "confidence": round(max(0.0, min(1.0, gain)), 4),
            "reason": None,
            "source_size": source_size,
            "output_size": list(corrected.size),
            "algorithm": "bounded_horizontal_projection_v1",
        }
    except Exception as exc:
        return image, {
            "detected_angle_degrees": None,
            "correction_angle_degrees": 0.0,
            "applied": False,
            "confidence": 0.0,
            "reason": f"correction_failed:{type(exc).__name__}",
            "source_size": source_size,
            "output_size": source_size,
            "algorithm": "bounded_horizontal_projection_v1",
        }


def _content_bounds(image: Image.Image) -> tuple[int, int] | None:
    """Find the dominant vertical ink band without OCR or row-content interpretation."""
    gray = image.convert("L")
    thumb_width = 256
    thumb = gray.resize((thumb_width, image.height), Image.Resampling.BILINEAR)
    binary = thumb.point(lambda value: 1 if value < 235 else 0)
    data = binary.tobytes()
    active = []
    for y in range(image.height):
        if sum(data[y * thumb_width:(y + 1) * thumb_width]) >= CONTENT_THRESHOLD:
            active.append(y)
    if not active:
        return None

    groups: list[list[int]] = []
    for y in active:
        if not groups or y > groups[-1][-1] + CONTENT_GAP_PX:
            groups.append([y])
        else:
            groups[-1].append(y)
    minimum_cluster = max(40, int(image.height * 0.02))
    relevant = [group for group in groups if len(group) >= minimum_cluster]
    if not relevant:
        relevant = [max(groups, key=len)]
    padding = max(12, int(image.height * 0.012))
    return max(0, min(group[0] for group in relevant) - padding), min(
        image.height, max(group[-1] for group in relevant) + 1 + padding
    )


def _partition_count(content_span: int, page_height: int) -> int:
    density = content_span / page_height
    return max(1, min(MAX_DATA_PARTITIONS, round(density * MAX_DATA_PARTITIONS)))


def _make_views(
    page_image: Image.Image,
    page_path: Path,
    document_id: str,
    page_number: int,
    source_sha256: str,
) -> tuple[list[dict], bool]:
    bounds = _content_bounds(page_image)
    limited = bounds is None
    if bounds is None:
        bounds = (0, page_image.height)
    content_start, content_end = bounds
    span = content_end - content_start
    count = _partition_count(span, page_image.height)
    views = [{
        "document_id": document_id,
        "page": page_number,
        "view_id": f"{document_id}-p{page_number:03d}-overview",
        "view_type": "overview",
        "image": str(page_path.resolve()),
        "image_sha256": _sha256(page_path),
        "source_sha256": source_sha256,
        "region": {"x0": 0, "y0": 0, "x1": page_image.width, "y1": page_image.height},
        "normalized_region": {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0},
        "expected_row_range": None,
        "recognition_role": "layout_only_no_business_fact_extraction",
    }]
    for index in range(count):
        core_start = content_start + round(span * index / count)
        core_end = content_start + round(span * (index + 1) / count)
        overlap = max(1, round(span * PARTITION_OVERLAP))
        crop_start = max(0, core_start - overlap)
        crop_end = min(page_image.height, core_end + overlap)
        view_path = page_path.with_name(f"page-{page_number}-rows-{index + 1:02d}.png")
        if view_path.exists():
            raise ValueError(f"发现无清单绑定的既有视图，拒绝覆盖: {view_path}")
        page_image.crop((0, crop_start, page_image.width, crop_end)).save(view_path, format="PNG", optimize=True)
        views.append({
            "document_id": document_id,
            "page": page_number,
            "view_id": f"{document_id}-p{page_number:03d}-rows-{index + 1:02d}",
            "view_type": "row_partition",
            "image": str(view_path.resolve()),
            "image_sha256": _sha256(view_path),
            "source_sha256": source_sha256,
            "region": {"x0": 0, "y0": crop_start, "x1": page_image.width, "y1": crop_end},
            "normalized_region": {
                "x0": 0.0,
                "y0": round(crop_start / page_image.height, 6),
                "x1": 1.0,
                "y1": round(crop_end / page_image.height, 6),
            },
            "core_region": {"x0": 0, "y0": core_start, "x1": page_image.width, "y1": core_end},
            "core_normalized_region": {
                "x0": 0.0,
                "y0": round(core_start / page_image.height, 6),
                "x1": 1.0,
                "y1": round(core_end / page_image.height, 6),
            },
            "expected_row_range": None,
            "row_range_status": "not_inferred_without_ocr",
            "recognition_role": "primary_rows_by_printed_row_index",
        })
    ids = [view["view_id"] for view in views]
    if len(ids) != len(set(ids)) or len(views) > MAX_VIEWS_PER_PAGE:
        raise ValueError("生成的视图 ID 重复或超过单页上限")
    return views, limited


def prepare(inputs: list[Path], workdir: Path) -> dict:
    started_ns = time.perf_counter_ns()
    if not inputs:
        raise ValueError("至少需要一份 PDF")
    workdir = workdir.expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    cached = _cached_result(inputs, workdir, started_ns)
    if cached is not None:
        return cached

    folder = workdir / ".attendance-pages"
    if folder.exists() and any(folder.rglob("page-*.png")):
        raise ValueError("发现未绑定清单的旧页面图片，拒绝覆盖；请使用新的任务工作目录")
    folder.mkdir(parents=True, exist_ok=True)
    documents, rendered_pages, rendered_views = [], 0, 0
    overview_count = partition_count_total = 0
    deskewed_page_count = 0
    for idx, raw in enumerate(inputs, 1):
        source = raw.expanduser().resolve()
        if not source.is_file() or source.suffix.lower() != ".pdf":
            raise ValueError(f"不是可读取的 PDF: {source}")
        source_hash = _sha256(source)
        with fitz.open(source) as pdf:
            if not 1 <= len(pdf) <= MAX_PAGES_PER_PDF:
                raise ValueError(f"PDF 页数超出允许范围: {source}")
            page_dir = folder / f"doc-{idx}"
            page_dir.mkdir(parents=True, exist_ok=True)
            pages = []
            for page_idx, page in enumerate(pdf, 1):
                overview_path = page_dir / f"page-{page_idx}.png"
                detail_pix = page.get_pixmap(dpi=DETAIL_DPI, alpha=False)
                detail = Image.frombytes("RGB", (detail_pix.width, detail_pix.height), detail_pix.samples)
                detail, deskew = _deskew(detail)
                overview = detail.copy()
                overview.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
                overview.save(overview_path, format="PNG", optimize=True)
                deskewed_page_count += int(deskew["applied"])
                document_id = f"doc-{idx}"
                result_path = page_dir / f"page-{page_idx}.json"
                views, limited = _make_views(detail, overview_path, document_id, page_idx, source_hash)
                rendered_pages += 1
                overview_count += 1
                rendered_views += len(views) - 1
                partition_count_total += len(views) - 1
                pages.append({
                    "page": page_idx,
                    "image": str(overview_path.resolve()),
                    "result": str(result_path.resolve()),
                    "source_sha256": source_hash,
                    "detail_width": detail.width,
                    "detail_height": detail.height,
                    "deskew": deskew,
                    "view_status": "LIMITED" if limited else "READY",
                    "views": views,
                })
            documents.append({"document_id": f"doc-{idx}", "source": str(source), "source_sha256": source_hash, "pages": pages})
    manifest = {
        "schema_version": 1,
        "view_schema_version": PREPROCESS_VERSION,
        "preprocess_version": PREPROCESS_VERSION,
        "preprocess_config_sha256": _preprocess_config_sha256(),
        "preprocess_config": _preprocess_config(),
        "deskew_policy": {
            "algorithm": "bounded_horizontal_projection_v1",
            "minimum_angle_degrees": DESKEW_MIN_ANGLE,
            "maximum_angle_degrees": DESKEW_MAX_ANGLE,
            "minimum_score_gain": DESKEW_MIN_SCORE_GAIN,
        },
        "documents": documents,
    }
    manifest_path = workdir / "attendance-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total_pages = sum(len(document["pages"]) for document in documents)
    elapsed_ms = round((time.perf_counter_ns() - started_ns) / 1_000_000, 3)
    _write_runtime_record(workdir, {
        "stage": "pdf_prepare",
        "elapsed_ms": elapsed_ms,
        "clock": "time.perf_counter_ns",
        "pdf_count": len(documents),
        "page_count": total_pages,
        "rendered_page_images": rendered_pages,
        "reused_page_images": 0,
        "rendered_view_images": rendered_views,
        "reused_view_images": 0,
        "overview_view_count": overview_count,
        "row_partition_view_count": partition_count_total,
        "deskewed_page_count": deskewed_page_count,
        "preprocess_status": "generated",
    })
    return {
        "manifest": str(manifest_path.resolve()),
        "total_pages": total_pages,
        "documents": documents,
        "preprocess_elapsed_ms": elapsed_ms,
        "rendered_page_images": rendered_pages,
        "reused_page_images": 0,
        "rendered_view_images": rendered_views,
        "reused_view_images": 0,
        "overview_view_count": overview_count,
        "row_partition_view_count": partition_count_total,
        "deskewed_page_count": deskewed_page_count,
        "cached": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, nargs="+", type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps({"ok": True, **prepare(args.input, args.workdir)}, ensure_ascii=False))
    except Exception as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
