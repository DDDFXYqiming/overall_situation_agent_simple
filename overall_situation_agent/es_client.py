from __future__ import annotations

import base64
import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .schema import index_mapping

logger = logging.getLogger(__name__)


class ElasticsearchError(RuntimeError):
    pass


@dataclass
class SimpleResponse:
    body: dict[str, Any]


class SimpleIndicesClient:
    def __init__(self, client: "SimpleElasticsearch"):
        self.client = client

    def exists(self, index: str) -> bool:
        status, _ = self.client.request("HEAD", f"/{index}", allow_404=True)
        return status == 200

    def create(self, index: str, body: dict) -> SimpleResponse:
        _, payload = self.client.request(
            "PUT",
            f"/{index}",
            body=body,
            params={"timeout": "180s", "master_timeout": "180s"},
        )
        return SimpleResponse(payload)

    def delete(self, index: str) -> SimpleResponse:
        _, payload = self.client.request(
            "DELETE",
            f"/{index}",
            params={"timeout": "180s", "master_timeout": "180s", "ignore_unavailable": "true"},
        )
        return SimpleResponse(payload)

    def get_mapping(self, index: str) -> SimpleResponse:
        _, payload = self.client.request("GET", f"/{index}/_mapping")
        return SimpleResponse(payload)

    def put_mapping(self, index: str, body: dict) -> SimpleResponse:
        _, payload = self.client.request(
            "PUT",
            f"/{index}/_mapping",
            body=body,
            params={"timeout": "180s", "master_timeout": "180s"},
        )
        return SimpleResponse(payload)

    def refresh(self, index: str) -> SimpleResponse:
        _, payload = self.client.request("POST", f"/{index}/_refresh")
        return SimpleResponse(payload)

    def put_settings(self, index: str, body: dict) -> SimpleResponse:
        _, payload = self.client.request(
            "PUT",
            f"/{index}/_settings",
            body=body,
            params={"master_timeout": "180s"},
        )
        return SimpleResponse(payload)


class SimpleElasticsearch:
    """Small HTTP client for the Elasticsearch APIs used by this project."""

    def __init__(self, settings: Settings):
        self.base_url = settings.es_url.rstrip("/")
        self.username = settings.es_username
        self.password = settings.es_password
        self.indices = SimpleIndicesClient(self)

    def request(
        self,
        method: str,
        path: str,
        body: dict | str | None = None,
        allow_404: bool = False,
        content_type: str = "application/json",
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 60,
    ) -> tuple[int, dict[str, Any]]:
        query_string = ""
        if params:
            query_string = "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.base_url}{path}{query_string}"
        data: bytes | None = None
        if isinstance(body, dict):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            data = body.encode("utf-8")

        headers = {"Content-Type": content_type}
        if self.username and self.password:
            token = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                return response.status, payload
        except urllib.error.HTTPError as exc:
            if allow_404 and exc.code == 404:
                return 404, {}
            raw = exc.read().decode("utf-8", errors="replace")
            raise ElasticsearchError(f"{method} {path} failed: HTTP {exc.code} {raw}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ElasticsearchError(f"{method} {path} timed out after {timeout_seconds}s") from exc
        except urllib.error.URLError as exc:
            raise ElasticsearchError(f"Cannot connect to Elasticsearch at {self.base_url}: {exc}") from exc

    def search(self, index: str, body: dict) -> SimpleResponse:
        _, payload = self.request("POST", f"/{index}/_search", body=body)
        return SimpleResponse(payload)

    def msearch(self, index: str, bodies: list[dict[str, Any]]) -> list[SimpleResponse]:
        if not bodies:
            return []
        lines: list[str] = []
        for body in bodies:
            lines.append(json.dumps({"index": index}, ensure_ascii=False))
            lines.append(json.dumps(body, ensure_ascii=False))
        payload = "\n".join(lines) + "\n"
        _, response = self.request(
            "POST",
            "/_msearch",
            body=payload,
            content_type="application/x-ndjson",
            timeout_seconds=300,
        )
        responses = response.get("responses", [])
        if len(responses) != len(bodies):
            raise ElasticsearchError(f"_msearch returned {len(responses)} responses for {len(bodies)} requests")
        wrapped: list[SimpleResponse] = []
        for item in responses:
            if item.get("error"):
                raise ElasticsearchError(f"_msearch item failed: {json.dumps(item['error'], ensure_ascii=False)}")
            wrapped.append(SimpleResponse(item))
        return wrapped

    def bulk(self, operations: list[dict[str, Any]]) -> SimpleResponse:
        lines = [json.dumps(operation, ensure_ascii=False) for operation in operations]
        payload = "\n".join(lines) + "\n"
        _, response = self.request(
            "POST",
            "/_bulk",
            body=payload,
            content_type="application/x-ndjson",
            timeout_seconds=300,
        )
        if response.get("errors"):
            error_items = response.get("items", [])
            first_error = None
            for item in error_items:
                for action in ("index", "create", "update"):
                    op = item.get(action)
                    if op and op.get("error"):
                        first_error = op["error"]
                        break
                if first_error:
                    break
            detail = f"first_error={json.dumps(first_error, ensure_ascii=False)}" if first_error else "unknown"
            raise ElasticsearchError(f"Bulk import completed with item errors. {detail}")
        return SimpleResponse(response)

    def cluster_health(self, wait_for_status: str | None = None, timeout: str = "120s") -> SimpleResponse:
        params: dict[str, Any] = {"timeout": timeout}
        if wait_for_status:
            params["wait_for_status"] = wait_for_status
        _, payload = self.request("GET", "/_cluster/health", params=params)
        return SimpleResponse(payload)

    def pending_tasks(self) -> SimpleResponse:
        _, payload = self.request("GET", "/_cluster/pending_tasks")
        return SimpleResponse(payload)

    def count(self, index: str) -> SimpleResponse:
        _, payload = self.request("GET", f"/{index}/_count")
        return SimpleResponse(payload)

    def delete_by_query(self, index: str, query: dict | None = None) -> SimpleResponse:
        body = query or {"query": {"match_all": {}}}
        _, payload = self.request(
            "POST",
            f"/{index}/_delete_by_query",
            body=body,
            params={
                "conflicts": "proceed",
                "refresh": "true",
                "wait_for_completion": "true",
                "timeout": "300s",
                "slices": "auto",
            },
            timeout_seconds=300,
        )
        return SimpleResponse(payload)

    def optimize_for_bulk(self, index: str) -> None:
        if not self.indices.exists(index=index):
            return
        self.indices.put_settings(index=index, body={"index": {"refresh_interval": "-1"}})

    def finish_bulk(self, index: str) -> None:
        if not self.indices.exists(index=index):
            return
        self.indices.put_settings(index=index, body={"index": {"refresh_interval": "1s"}})
        self.indices.refresh(index=index)


def create_es_client(settings: Settings) -> SimpleElasticsearch:
    return SimpleElasticsearch(settings)


def wait_for_cluster_ready(es: SimpleElasticsearch, timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            health = es.cluster_health(wait_for_status="yellow", timeout="30s").body
            status = health.get("status")
            if status in {"yellow", "green"}:
                logger.info("Elasticsearch cluster ready: status=%s pending_tasks=%s", status, health.get("number_of_pending_tasks"))
                return
        except ElasticsearchError as exc:
            last_error = exc
        time.sleep(2)
    raise ElasticsearchError(f"Elasticsearch cluster not ready within {timeout_seconds}s: {last_error}")


def ensure_cluster_import_ready(es: SimpleElasticsearch, index_name: str) -> None:
    health = es.cluster_health(timeout="30s").body
    pending_count = int(health.get("number_of_pending_tasks", 0) or 0)
    max_wait_ms = int(health.get("task_max_waiting_in_queue_millis", 0) or 0)
    if pending_count == 0 and max_wait_ms < 60_000:
        return

    tasks = es.pending_tasks().body.get("tasks", [])
    blocking_delete = None
    for task in tasks:
        source = str(task.get("source", ""))
        if index_name in source and "delete-index" in source:
            blocking_delete = task
            break

    if blocking_delete is not None:
        time_in_queue = blocking_delete.get("time_in_queue") or f"{blocking_delete.get('time_in_queue_millis', 0)}ms"
        raise ElasticsearchError(
            f"Elasticsearch 当前存在针对索引 [{index_name}] 的挂起 delete-index 任务（已排队 {time_in_queue}）。"
            " 这会显著拖慢 bulk 导入，请先重启本地 Elasticsearch 后再重试。"
        )

    if pending_count > 8 or max_wait_ms > 300_000:
        logger.warning(
            "Elasticsearch pending tasks are elevated before import: pending=%s max_wait_ms=%s",
            pending_count,
            max_wait_ms,
        )


def _is_cluster_event_timeout(exc: ElasticsearchError) -> bool:
    text = str(exc)
    return "HTTP 429" in text and "process_cluster_event_timeout_exception" in text


def _wait_for_pending_delete_clear(es: SimpleElasticsearch, index_name: str, timeout_seconds: int = 120) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if not es.indices.exists(index=index_name):
                return True
            tasks = es.pending_tasks().body.get("tasks", [])
            has_delete = any(index_name in str(task.get("source", "")) and "delete-index" in str(task.get("source", "")) for task in tasks)
            if not has_delete:
                return False
        except ElasticsearchError:
            pass
        time.sleep(3)
    return not es.indices.exists(index=index_name)


def _delete_index_with_retry(es: SimpleElasticsearch, index_name: str, attempts: int = 4) -> bool:
    for attempt in range(1, attempts + 1):
        if not es.indices.exists(index=index_name):
            return True
        try:
            logger.info("Deleting index %s (attempt %s/%s)", index_name, attempt, attempts)
            es.indices.delete(index=index_name)
            return True
        except ElasticsearchError as exc:
            if _is_cluster_event_timeout(exc):
                logger.warning("Delete index timed out for %s on attempt %s: %s", index_name, attempt, exc)
                if _wait_for_pending_delete_clear(es, index_name, timeout_seconds=45):
                    return True
                time.sleep(min(5 * attempt, 15))
                continue
            raise
    return not es.indices.exists(index=index_name)


def _clear_index_documents(es: SimpleElasticsearch, index_name: str) -> None:
    if not es.indices.exists(index=index_name):
        return
    count = es.count(index_name).body.get("count", 0)
    if count == 0:
        return
    logger.warning("Falling back to delete_by_query for index %s; current docs=%s", index_name, count)
    es.delete_by_query(index_name)
    es.indices.refresh(index=index_name)


def _ensure_index_mapping(es: SimpleElasticsearch, index_name: str) -> None:
    desired_properties = index_mapping()["mappings"]["properties"]
    current = es.indices.get_mapping(index=index_name).body
    current_properties = (
        current.get(index_name, {})
        .get("mappings", {})
        .get("properties", {})
    )
    missing = {
        field: mapping
        for field, mapping in desired_properties.items()
        if field not in current_properties
    }
    if missing:
        logger.info("Adding %s missing mapping fields to %s", len(missing), index_name)
        es.indices.put_mapping(index=index_name, body={"properties": missing})


def ensure_index(es: SimpleElasticsearch, index_name: str, recreate: bool = False) -> None:
    wait_for_cluster_ready(es)
    ensure_cluster_import_ready(es, index_name)
    if recreate and es.indices.exists(index=index_name):
        current_count = es.count(index_name).body.get("count", 0)
        logger.info("Recreating index %s; existing docs=%s", index_name, current_count)
        if not _delete_index_with_retry(es, index_name):
            logger.warning("Could not delete index %s cleanly; clearing documents and preserving mapping", index_name)
            _clear_index_documents(es, index_name)

    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name, body=index_mapping())
    else:
        _ensure_index_mapping(es, index_name)
