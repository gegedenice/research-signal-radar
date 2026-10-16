from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .errors import InvariantError


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class RunStore:
    def __init__(self, root: Path):
        self.root = root

    def path(self, relative: str | Path) -> Path:
        return self.root / relative

    def _atomic_bytes(self, path: Path, data: bytes, *, overwrite: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            raise InvariantError(f"refusing to overwrite immutable run artifact: {path}")
        temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    def write_json(self, relative: str | Path, value: Any, *, overwrite: bool = False) -> Path:
        path = self.path(relative)
        payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        self._atomic_bytes(path, payload, overwrite=overwrite)
        return path

    def write_json_gz(self, relative: str | Path, value: Any, *, overwrite: bool = False) -> Path:
        path = self.path(relative)
        payload = gzip.compress(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            mtime=0,
        )
        self._atomic_bytes(path, payload, overwrite=overwrite)
        return path

    def write_jsonl_gz(
        self,
        relative: str | Path,
        records: Iterable[dict[str, Any]],
        *,
        overwrite: bool = False,
    ) -> Path:
        lines = b"".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            for record in records
        )
        path = self.path(relative)
        self._atomic_bytes(path, gzip.compress(lines, mtime=0), overwrite=overwrite)
        return path

    def write_text(
        self,
        relative: str | Path,
        value: str,
        *,
        overwrite: bool = False,
    ) -> Path:
        payload = value.encode("utf-8")
        if not payload.endswith(b"\n"):
            payload += b"\n"
        path = self.path(relative)
        self._atomic_bytes(path, payload, overwrite=overwrite)
        return path

    def read_json(self, relative: str | Path) -> Any:
        return json.loads(self.path(relative).read_text(encoding="utf-8"))

    def read_json_gz(self, relative: str | Path) -> Any:
        with gzip.open(self.path(relative), "rt", encoding="utf-8") as handle:
            return json.load(handle)

    def read_jsonl_gz(self, relative: str | Path) -> list[dict[str, Any]]:
        with gzip.open(self.path(relative), "rt", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
