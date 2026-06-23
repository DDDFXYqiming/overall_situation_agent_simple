from __future__ import annotations

import logging
from pathlib import Path

from .es_client import SimpleElasticsearch
from .excel_loader import iter_tagged_feedback

logger = logging.getLogger(__name__)


def _to_bulk_operations(index_name: str, input_name: str, start_offset: int, records: list[dict]) -> list[dict]:
    operations: list[dict] = []
    for idx, record in enumerate(records, start=start_offset):
        operations.append({"index": {"_index": index_name, "_id": record.get("gd_identity") or f"{input_name}-{idx}"}})
        operations.append(record)
    return operations


def _is_retryable_bulk_error(exc: Exception) -> bool:
    text = str(exc)
    return "timed out" in text.lower() or "HTTP 429" in text


def _bulk_import_chunk(
    es: SimpleElasticsearch,
    index_name: str,
    input_name: str,
    records: list[dict],
    start_record_no: int,
    total_records: int,
    min_chunk_size: int = 25,
) -> int:
    chunk_size = len(records)
    end_record_no = start_record_no + chunk_size - 1
    logger.info("Importing records %s-%s / %s (chunk size=%s)", start_record_no, end_record_no, total_records, chunk_size)
    try:
        operations = _to_bulk_operations(index_name, input_name, start_record_no - 1, records)
        response = es.bulk(operations).body
        return int(len(response.get("items", [])))
    except Exception as exc:
        if chunk_size <= min_chunk_size or not _is_retryable_bulk_error(exc):
            raise
        mid = chunk_size // 2
        logger.warning(
            "Chunk %s-%s failed (%s). Splitting into %s and %s records.",
            start_record_no,
            end_record_no,
            exc,
            mid,
            chunk_size - mid,
        )
        left = _bulk_import_chunk(es, index_name, input_name, records[:mid], start_record_no, total_records, min_chunk_size=min_chunk_size)
        right = _bulk_import_chunk(
            es,
            index_name,
            input_name,
            records[mid:],
            start_record_no + mid,
            total_records,
            min_chunk_size=min_chunk_size,
        )
        return left + right


def import_excel_to_es(
    es: SimpleElasticsearch,
    index_name: str,
    input_path: Path,
    batch_size: int = 500,
) -> int:
    total_records, record_iter = iter_tagged_feedback(input_path)
    logger.info("Prepared %s records from %s for streaming import", total_records, input_path)
    success = 0
    es.optimize_for_bulk(index_name)
    try:
        chunk: list[dict] = []
        chunk_start = 1
        for record_no, record in enumerate(record_iter, start=1):
            chunk.append(record)
            if len(chunk) < batch_size:
                continue
            success += _bulk_import_chunk(
                es,
                index_name,
                input_path.name,
                chunk,
                start_record_no=chunk_start,
                total_records=total_records,
            )
            chunk = []
            chunk_start = record_no + 1

        if chunk:
            success += _bulk_import_chunk(
                es,
                index_name,
                input_path.name,
                chunk,
                start_record_no=chunk_start,
                total_records=total_records,
            )
    finally:
        es.finish_bulk(index_name)
    logger.info("Import completed for %s: indexed=%s", index_name, success)
    return success
