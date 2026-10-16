from __future__ import annotations

import os
import time
import json
from collections.abc import Iterator
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import OpenAlexConfig
from .errors import OpenAlexError, PaginationError


class OpenAlexClient:
    """Small OpenAlex client with retry, cursor safety and injectable transport."""

    def __init__(
        self,
        config: OpenAlexConfig,
        *,
        requester: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self._base_url = config.base_url.rstrip("/")
        self._requester = requester

    def close(self) -> None:
        return None

    def __enter__(self) -> "OpenAlexClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _runtime_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        api_key = os.getenv(self.config.api_key_env)
        if api_key:
            params["api_key"] = api_key
        return params

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_params = dict(params or {})
        request_params.update(self._runtime_params())
        if self._requester is not None:
            payload = self._requester(path, request_params)
            if not isinstance(payload, dict):
                raise OpenAlexError(f"OpenAlex requester returned a non-object for {path}")
            return payload

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                query = urlencode(request_params, doseq=True, safe="|,:/")
                url = self._base_url + path + ("?" + query if query else "")
                request = Request(url, headers={"User-Agent": self.config.user_agent})
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise OpenAlexError(f"OpenAlex returned a non-object for {path}")
                return payload
            except HTTPError as exc:
                last_error = exc
                retryable = exc.code == 429 or exc.code >= 500
                if retryable and attempt < self.config.max_retries:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    delay = float(retry_after) if retry_after else min(2**attempt, 8)
                    time.sleep(delay)
                    continue
                break
            except (URLError, TimeoutError, ValueError, OpenAlexError) as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                break
        raise OpenAlexError(f"OpenAlex request failed for {path}: {last_error}") from last_error

    def iter_cursor_pages(
        self,
        path: str,
        params: dict[str, Any],
        *,
        start_cursor: str | None = "*",
        start_page_number: int = 1,
    ) -> Iterator[tuple[int, dict[str, Any]]]:
        cursor = start_cursor
        seen: set[str] = set()
        page_number = start_page_number
        while cursor is not None:
            if cursor in seen:
                raise PaginationError(f"cursor loop detected at page {page_number}: {cursor!r}")
            seen.add(cursor)
            page_params = dict(params)
            page_params["cursor"] = cursor
            payload = self.get_json(path, page_params)
            yield page_number, payload
            meta = payload.get("meta") or {}
            if "next_cursor" not in meta:
                raise PaginationError(f"missing meta.next_cursor on page {page_number}")
            cursor = meta.get("next_cursor")
            page_number += 1
