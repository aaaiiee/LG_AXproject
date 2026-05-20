from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from lg_dash.adapters.fetcher import HtmlFetcher
from lg_dash.models import (
    Brand,
    Category,
    ProductRef,
    RawReview,
    SourceId,
    SpecPayload,
)

BASE_SEARCH = "https://search.danawa.com/dsearch.php"
BASE_PRODUCT = "https://prod.danawa.com/info/"

_MODEL_CODE_RE = re.compile(r"(?<![A-Z])([A-Z]{1,3}\d{2,}[A-Z]{2,6})(?![A-Z])")
_DATE_FMTS = ("%Y.%m.%d", "%Y-%m-%d")

_DANAWA_SECTION_HEADER_RE = re.compile(r"\[[^\]]*\]")
_DANAWA_WASH_DRY_RE = re.compile(
    r"세탁\s*(\d+(?:\.\d+)?)\s*kg(?:\s*[,/]\s*건조\s*(\d+(?:\.\d+)?)\s*kg)?",
    re.IGNORECASE,
)
_DANAWA_BOOL_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("스팀", "스팀"),
    ("트루스팀", "스팀"),
    ("ThinQ", "WiFi"),
    ("씽큐", "WiFi"),
    ("SmartThings", "WiFi"),
    ("스마트싱스", "WiFi"),
    ("와이파이", "WiFi"),
    ("WiFi", "WiFi"),
    ("원격제어", "WiFi"),
    ("스마트홈", "WiFi"),
    ("DD모터", "인버터모터"),
    ("인버터", "인버터모터"),
)


def _parse_danawa_spec_text(text: str) -> dict[str, str]:
    cleaned = _DANAWA_SECTION_HEADER_RE.sub(" ", text)
    attrs: dict[str, str] = {}
    for raw_token in cleaned.split("/"):
        token = raw_token.strip()
        if not token:
            continue
        m = _DANAWA_WASH_DRY_RE.search(token)
        if m:
            attrs.setdefault("세탁용량", f"{m.group(1)}kg")
            if m.group(2):
                attrs.setdefault("건조용량", f"{m.group(2)}kg")
            continue
        if ":" in token:
            label, _, value = token.partition(":")
            label = re.sub(r"\(.*?\)", "", label).strip()
            value = value.strip()
            if label and value:
                attrs.setdefault(label, value)
                continue
        for keyword, label in _DANAWA_BOOL_KEYWORDS:
            if keyword in token:
                attrs.setdefault(label, token)
                break
    return attrs


class DanawaAdapter:
    source_id: str = SourceId.DANAWA.value

    def __init__(self, fetcher: HtmlFetcher) -> None:
        self.fetcher = fetcher

    def search_url(self, brand: Brand, category: Category) -> str:
        keyword = brand.search_keywords.get(category.display, brand.display)
        return f"{BASE_SEARCH}?query={quote_plus(keyword)}"

    def product_url(self, pcode: str) -> str:
        return f"{BASE_PRODUCT}?pcode={pcode}"

    def discover(self, brand: Brand, category: Category) -> list[ProductRef]:
        html = self.fetcher.fetch(self.search_url(brand, category))
        soup = BeautifulSoup(html, "lxml")
        refs: list[ProductRef] = []
        for item in soup.select("li.prod_item"):
            pcode = self._extract_pcode(item)
            link = (
                item.select_one("p.prod_name a")
                or item.select_one("a.prod_name")
            )
            if not pcode or not link:
                continue
            model_name = link.get_text(strip=True)
            if not model_name:
                continue
            refs.append(
                ProductRef(
                    source_id=SourceId.DANAWA,
                    brand_id=brand.id,
                    category_id=category.id,
                    external_id=pcode,
                    url=self.product_url(pcode),
                    model_name=model_name,
                    model_code=self._extract_model_code(model_name),
                )
            )
        return refs

    @staticmethod
    def _extract_pcode(item) -> str | None:
        data_pcode = item.get("data-pcode")
        if data_pcode:
            return str(data_pcode)
        item_id = item.get("id") or ""
        m = re.match(r"productItem(\d+)$", item_id)
        if m:
            return m.group(1)
        anchor = item.find("a", href=re.compile(r"pcode=\d+"))
        if anchor is not None:
            m = re.search(r"pcode=(\d+)", anchor["href"])
            if m:
                return m.group(1)
        return None

    def fetch_specs(self, ref: ProductRef) -> SpecPayload:
        html = self.fetcher.fetch(ref.url)
        soup = BeautifulSoup(html, "lxml")
        attributes: dict[str, str] = {}
        table = soup.select_one("table.spec_tbl")
        if table is not None:
            for row in table.select("tr"):
                th = row.select_one("th")
                td = row.select_one("td")
                if th and td:
                    attributes[th.get_text(strip=True)] = td.get_text(strip=True)
        items = soup.select_one("dl.spec_set div.spec_list div.items")
        if items is not None:
            text = items.get_text(separator=" ", strip=True)
            for k, v in _parse_danawa_spec_text(text).items():
                attributes.setdefault(k, v)
        return SpecPayload(
            product_ref=ref,
            attributes=attributes,
            captured_at=datetime.now(),
        )

    def fetch_reviews(
        self, ref: ProductRef, since: datetime | None = None
    ) -> Iterator[RawReview]:
        html = self.fetcher.fetch(ref.url)
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select(".review_item"):
            text_el = item.select_one(".text")
            if text_el is None:
                continue
            text = text_el.get_text(strip=True)
            if not text:
                continue
            rating = self._parse_rating(item)
            posted_at = self._parse_date(item)
            if since is not None and posted_at is not None and posted_at < since:
                continue
            yield RawReview(
                product_ref=ref,
                rating=rating,
                text=text,
                posted_at=posted_at,
            )

    @staticmethod
    def _extract_model_code(model_name: str) -> str | None:
        match = _MODEL_CODE_RE.search(model_name)
        return match.group(1) if match else None

    @staticmethod
    def _parse_rating(item: object) -> float | None:
        rating_el = item.select_one(".rating")  # type: ignore[attr-defined]
        if rating_el is None:
            return None
        score = rating_el.get("data-score")
        if score is None:
            return None
        try:
            return float(score)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_date(item: object) -> datetime | None:
        date_el = item.select_one(".date")  # type: ignore[attr-defined]
        if date_el is None:
            return None
        raw = date_el.get_text(strip=True)
        for fmt in _DATE_FMTS:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None
