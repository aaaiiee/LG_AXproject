from __future__ import annotations

import os
import time
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

import httpx


@runtime_checkable
class HtmlFetcher(Protocol):
    def fetch(self, url: str) -> str: ...


@runtime_checkable
class ImageFetcher(Protocol):
    def fetch_bytes(self, url: str) -> bytes: ...


class HttpImageFetcher:
    def __init__(self, *, timeout: float = 30.0) -> None:
        ua = os.environ.get("CRAWL_USER_AGENT", "LG_Dash/0.0.1 (+internal-use)")
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": ua},
            follow_redirects=True,
        )

    def fetch_bytes(self, url: str) -> bytes:
        response = self.client.get(url)
        response.raise_for_status()
        return response.content

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "HttpImageFetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


_HOST_MIN_DELAY: dict[str, float] = {
    "search.danawa.com": 10.0,
    "prod.danawa.com": 2.0,
    "www.coupang.com": 2.0,
    "www.youtube.com": 2.0,
}
_DEFAULT_DELAY = float(os.environ.get("CRAWL_RATE_LIMIT_PER_HOST", "1.0"))


class HttpFetcher:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        host_min_delays: dict[str, float] | None = None,
    ) -> None:
        ua = user_agent or os.environ.get(
            "CRAWL_USER_AGENT", "LG_Dash/0.0.1 (+internal-use)"
        )
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": ua, "Accept-Language": "ko,en;q=0.9"},
            follow_redirects=follow_redirects,
        )
        self._host_min_delays = dict(_HOST_MIN_DELAY)
        if host_min_delays:
            self._host_min_delays.update(host_min_delays)
        self._last_fetch_at: dict[str, float] = {}

    def fetch(self, url: str) -> str:
        host = urlparse(url).hostname or ""
        self._wait_for_host(host)
        response = self.client.get(url)
        self._last_fetch_at[host] = time.monotonic()
        response.raise_for_status()
        return response.text

    def _wait_for_host(self, host: str) -> None:
        min_delay = self._host_min_delays.get(host, _DEFAULT_DELAY)
        last = self._last_fetch_at.get(host)
        if last is None:
            return
        elapsed = time.monotonic() - last
        if elapsed < min_delay:
            time.sleep(min_delay - elapsed)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "HttpFetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
