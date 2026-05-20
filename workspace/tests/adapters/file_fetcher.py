from __future__ import annotations

from pathlib import Path


class FileFetcher:
    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir
        self._routes: list[tuple[str, str]] = []

    def route(self, url_substring: str, filename: str) -> "FileFetcher":
        self._routes.append((url_substring, filename))
        return self

    def fetch(self, url: str) -> str:
        for pattern, fname in self._routes:
            if pattern in url:
                return (self.fixture_dir / fname).read_text(encoding="utf-8")
        raise FileNotFoundError(f"No fixture registered for url: {url}")

    @classmethod
    def for_danawa(cls, fixture_dir: Path) -> "FileFetcher":
        f = cls(fixture_dir)
        f.route("search.danawa.com/dsearch.php", "search_lg_washer.html")
        f.route("pcode=12345678", "product_12345678.html")
        f.route("pcode=87654321", "product_87654321.html")
        f.route("pcode=11223344", "product_11223344.html")
        return f

    @classmethod
    def for_danawa_live(cls, fixture_dir: Path) -> "FileFetcher":
        f = cls(fixture_dir)
        f.route("search.danawa.com/dsearch.php", "search_lg_washer.html")
        f.route("pcode=76550339", "product_76550339.html")
        return f

    @classmethod
    def for_youtube(cls, fixture_dir: Path) -> "FileFetcher":
        f = cls(fixture_dir)
        f.route("youtube.com/watch?v=VID-LGA-001", "video_VID-LGA-001.html")
        f.route("youtube.com/watch?v=VID-LGA-002", "video_VID-LGA-002.html")
        f.route("youtube.com/results", "search_lg_washer.html")
        return f

    @classmethod
    def for_coupang(cls, fixture_dir: Path) -> "FileFetcher":
        f = cls(fixture_dir)
        f.route("coupang.com/vp/products/2000001", "product_2000001.html")
        f.route("coupang.com/vp/products/2000002", "product_2000002.html")
        f.route("coupang.com/np/search", "search_lg_washer.html")
        return f

    @classmethod
    def for_manufacturer(cls, fixture_dir: Path) -> "FileFetcher":
        f = cls(fixture_dir)
        f.route("lge.co.kr/product/WT-LGA-001", "lg_product_WT-LGA-001.html")
        f.route("lge.co.kr/product/WT-LGA-002", "lg_product_WT-LGA-002.html")
        f.route("lge.co.kr/product/WT-LGA-003", "lg_product_WT-LGA-003.html")
        f.route("lge.co.kr/washing-machines", "lg_washer_catalog.html")
        f.route("samsung.com/sec/washers-and-dryers/washers", "samsung_washer_catalog.html")
        f.route("winia.com/products/washer", "winia_washer_catalog.html")
        return f
