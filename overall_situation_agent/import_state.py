from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ImportState:
    es_index: str
    input_path: str
    source_file: str
    file_size: int
    modified_time_ns: int
    record_count: int
    imported_at: str

    def matches(self, input_path: Path, es_index: str) -> bool:
        resolved = input_path.resolve()
        stat = resolved.stat()
        return (
            self.es_index == es_index
            and self.input_path == str(resolved)
            and self.source_file == resolved.name
            and self.file_size == stat.st_size
            and self.modified_time_ns == stat.st_mtime_ns
        )


@dataclass(frozen=True)
class ImportManifest:
    es_index: str
    input_path: str
    inputs: list[ImportState]
    record_count: int
    imported_at: str

    def matches(self, input_path: Path, es_index: str) -> bool:
        resolved = input_path.resolve()
        return self.es_index == es_index and self.input_path == str(resolved)

    def matches_files(self, input_paths: list[Path], es_index: str) -> bool:
        if self.es_index != es_index or len(self.inputs) != len(input_paths):
            return False
        states_by_path = {state.input_path: state for state in self.inputs}
        for input_path in input_paths:
            resolved = input_path.resolve()
            state = states_by_path.get(str(resolved))
            if not state or not state.matches(resolved, es_index):
                return False
        return True


def build_import_state(input_path: Path, es_index: str, record_count: int) -> ImportState:
    resolved = input_path.resolve()
    stat = resolved.stat()
    return ImportState(
        es_index=es_index,
        input_path=str(resolved),
        source_file=resolved.name,
        file_size=stat.st_size,
        modified_time_ns=stat.st_mtime_ns,
        record_count=record_count,
        imported_at=datetime.now(timezone.utc).isoformat(),
    )


def build_import_manifest(input_path: Path, es_index: str, states: list[ImportState]) -> ImportManifest:
    resolved = input_path.resolve()
    return ImportManifest(
        es_index=es_index,
        input_path=str(resolved),
        inputs=states,
        record_count=sum(state.record_count for state in states),
        imported_at=datetime.now(timezone.utc).isoformat(),
    )


def load_import_state(path: Path) -> ImportState | ImportManifest | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload.get("inputs"), list):
            inputs = [ImportState(**item) for item in payload["inputs"]]
            return ImportManifest(
                es_index=payload["es_index"],
                input_path=payload["input_path"],
                inputs=inputs,
                record_count=int(payload.get("record_count", 0)),
                imported_at=payload.get("imported_at", ""),
            )
        return ImportState(**payload)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def save_import_state(path: Path, state: ImportState | ImportManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
