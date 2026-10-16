from __future__ import annotations

import json
import os
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import OpenCitationsConfig
from .errors import OpenCitationsError


class OpenCitationsClient:
    """Small Index v2 client with authentication, throttling and retries."""

    def __init__(
        self,
        config: OpenCitationsConfig,
        *,
        requester: Callable[[str, dict[str, str]], Any] | None = None,
    ) -> None:
        self.config = config
        self._base_url = config.base_url.rstrip("/")
        self._requester = requester
        self._last_request_at: float | None = None

    def close(self) -> None:
        return None

    def __enter__(self) -> "OpenCitationsClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.config.user_agent,
        }
        api_key = os.getenv(self.config.api_key_env)
        if api_key:
            headers["authorization"] = api_key
        return headers

    def _throttle(self) -> None:
        interval = 60.0 / self.config.requests_per_minute
        if self._last_request_at is not None:
            delay = interval - (time.monotonic() - self._last_request_at)
            if delay > 0:
                time.sleep(delay)
        self._last_request_at = time.monotonic()

    def get_json(self, path: str) -> list[dict[str, Any]]:
        headers = self._headers()
        if self._requester is not None:
            payload = self._requester(path, headers)
            if not isinstance(payload, list) or any(
                not isinstance(item, dict) for item in payload
            ):
                raise OpenCitationsError(
                    f"OpenCitations requester returned invalid JSON for {path}"
                )
            return payload

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                self._throttle()
                request = Request(self._base_url + path, headers=headers)
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, list) or any(
                    not isinstance(item, dict) for item in payload
                ):
                    raise OpenCitationsError(
                        f"OpenCitations returned invalid JSON for {path}"
                    )
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
            except (URLError, TimeoutError, ValueError, OpenCitationsError) as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                break
        raise OpenCitationsError(
            f"OpenCitations request failed for {path}: {last_error}"
        ) from last_error

    @staticmethod
    def _identifier(doi: str) -> str:
        return quote(f"doi:{doi}", safe=":/()")

    def citations(self, doi: str) -> list[dict[str, Any]]:
        return self.get_json(f"/citations/{self._identifier(doi)}")

    def citation_count(self, doi: str) -> list[dict[str, Any]]:
        return self.get_json(f"/citation-count/{self._identifier(doi)}")

    def references(self, doi: str) -> list[dict[str, Any]]:
        return self.get_json(f"/references/{self._identifier(doi)}")

    def reference_count(self, doi: str) -> list[dict[str, Any]]:
        return self.get_json(f"/reference-count/{self._identifier(doi)}")
