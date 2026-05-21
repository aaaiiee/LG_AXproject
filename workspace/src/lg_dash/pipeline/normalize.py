from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml
from rapidfuzz import fuzz

from lg_dash.llm.client import LlmClient
from lg_dash.models import (
    AttrDefinition,
    CategoryId,
    MatchedBy,
    NormalizedFact,
    ProductRef,
    SourceId,
    SpecPayload,
)
from lg_dash.storage import repo
from lg_dash.storage.db import connect, db_path, migrate

__all__ = [
    "NormalizedFact",
    "Normalizer",
    "load_attr_dictionary",
    "normalize_and_persist",
]


_BOOL_NEGATIVE = {"없음", "미지원", "지원안함", "x", "n/a", "no", "false", "0"}


def load_attr_dictionary(path: Path) -> list[AttrDefinition]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [AttrDefinition(**item) for item in data["attributes"]]


def _norm(s: str) -> str:
    return "".join(s.split()).lower()


class Normalizer:
    def __init__(
        self,
        attr_defs: list[AttrDefinition],
        fuzzy_threshold: float = 0.85,
        *,
        llm_client: LlmClient | None = None,
        llm_confidence: float = 0.7,
    ) -> None:
        self.attr_defs = attr_defs
        self.threshold = fuzzy_threshold
        self.llm_client = llm_client
        self.llm_confidence = llm_confidence
        self._synonyms_index: dict[str, list[AttrDefinition]] = {}
        for d in attr_defs:
            for syn in d.synonyms:
                self._synonyms_index.setdefault(_norm(syn), []).append(d)

    def normalize(
        self, payload: SpecPayload, category: CategoryId
    ) -> list[NormalizedFact]:
        applicable = [d for d in self.attr_defs if category in d.applies_to]
        applicable_ids = {id(d) for d in applicable}
        facts: list[NormalizedFact] = []
        unmatched: list[tuple[str, str]] = []
        for label, raw_value in payload.attributes.items():
            matched = self._match(label, applicable, applicable_ids)
            if matched is None:
                unmatched.append((label, str(raw_value)))
                continue
            attr_def, confidence, matched_by = matched
            fact = self._extract(
                attr_def, label, str(raw_value), confidence, matched_by
            )
            if fact is not None:
                facts.append(fact)
        if unmatched and self.llm_client is not None:
            facts.extend(self._llm_fallback(unmatched, applicable))
        return facts

    def _llm_fallback(
        self,
        unmatched: list[tuple[str, str]],
        applicable: list[AttrDefinition],
    ) -> list[NormalizedFact]:
        assert self.llm_client is not None
        by_key = {d.canonical_key: d for d in applicable}
        vocab_lines = "\n".join(
            f"- {d.canonical_key} ({d.display_ko}, unit={d.unit})" for d in applicable
        )
        labels_lines = "\n".join(f"- {label!r} = {value!r}" for label, value in unmatched)
        system = (
            "당신은 한국 가전 제품의 스펙 라벨을 표준 canonical_key 사전에 매핑합니다.\n"
            "출력은 JSON 객체만. 매핑 불가 시 null.\n"
            f"사용 가능한 canonical_key:\n{vocab_lines}"
        )
        user = (
            f"다음 라벨을 canonical_key로 매핑하세요:\n{labels_lines}\n\n"
            '응답 형식: {"<label>": "<canonical_key>" 또는 null, ...}'
        )
        response = self.llm_client.complete(system=system, user=user)
        try:
            match = re.search(r"\{.*\}", response.text, re.DOTALL)
            mappings = json.loads(match.group(0)) if match else {}
        except (json.JSONDecodeError, AttributeError):
            return []

        out: list[NormalizedFact] = []
        for label, raw_value in unmatched:
            canonical_key = mappings.get(label)
            if not canonical_key:
                continue
            attr_def = by_key.get(canonical_key)
            if attr_def is None:
                continue
            fact = self._extract(
                attr_def,
                label,
                raw_value,
                self.llm_confidence,
                MatchedBy.LLM,
            )
            if fact is not None:
                out.append(fact)
        return out

    def _match(
        self,
        label: str,
        applicable: list[AttrDefinition],
        applicable_ids: set[int],
    ) -> tuple[AttrDefinition, float, MatchedBy] | None:
        norm_label = _norm(label)
        if norm_label in self._synonyms_index:
            for d in self._synonyms_index[norm_label]:
                if id(d) in applicable_ids:
                    return (d, 1.0, MatchedBy.RULE)
        best: AttrDefinition | None = None
        best_score = 0.0
        for d in applicable:
            for syn in d.synonyms:
                score = fuzz.ratio(norm_label, _norm(syn))
                if score > best_score:
                    best_score = score
                    best = d
        if best is not None and best_score >= self.threshold * 100:
            confidence = min(best_score / 100.0, 0.99)
            return (best, confidence, MatchedBy.FUZZY)
        return None

    def _extract(
        self,
        d: AttrDefinition,
        label: str,
        raw_value: str,
        confidence: float,
        matched_by: MatchedBy,
    ) -> NormalizedFact | None:
        if d.data_type == "number":
            return self._extract_number(d, label, raw_value, confidence, matched_by)
        if d.data_type == "enum":
            return self._extract_enum(d, label, raw_value, confidence, matched_by)
        if d.data_type == "bool":
            return self._extract_bool(d, label, raw_value, confidence, matched_by)
        if d.data_type == "string":
            return self._extract_string(d, label, raw_value, confidence, matched_by)
        return None

    def _extract_number(
        self,
        d: AttrDefinition,
        label: str,
        raw_value: str,
        confidence: float,
        matched_by: MatchedBy,
    ) -> NormalizedFact | None:
        if not d.value_pattern:
            return None
        match = re.search(d.value_pattern, raw_value)
        if match is None:
            return None
        num_str = match.group(1).replace(",", "")
        try:
            value = float(num_str)
        except ValueError:
            return None
        return NormalizedFact(
            canonical_key=d.canonical_key,
            value_num=value,
            value_text=None,
            unit=d.unit,
            source_attr_label=label,
            confidence=confidence,
            matched_by=matched_by,
        )

    def _extract_enum(
        self,
        d: AttrDefinition,
        label: str,
        raw_value: str,
        confidence: float,
        matched_by: MatchedBy,
    ) -> NormalizedFact | None:
        if d.enum_map:
            for key, val in d.enum_map.items():
                if key in raw_value or _norm(key) == _norm(raw_value):
                    return NormalizedFact(
                        canonical_key=d.canonical_key,
                        value_num=float(val),
                        value_text=raw_value,
                        unit=d.unit,
                        source_attr_label=label,
                        confidence=confidence,
                        matched_by=matched_by,
                    )
        if d.value_pattern:
            match = re.search(d.value_pattern, raw_value)
            if match is not None:
                try:
                    return NormalizedFact(
                        canonical_key=d.canonical_key,
                        value_num=float(match.group(1)),
                        value_text=raw_value,
                        unit=d.unit,
                        source_attr_label=label,
                        confidence=confidence,
                        matched_by=matched_by,
                    )
                except (ValueError, IndexError):
                    pass
        return None

    def _extract_bool(
        self,
        d: AttrDefinition,
        label: str,
        raw_value: str,
        confidence: float,
        matched_by: MatchedBy,
    ) -> NormalizedFact | None:
        if not raw_value.strip():
            return None
        value_num = 0.0 if _norm(raw_value) in _BOOL_NEGATIVE else 1.0
        return NormalizedFact(
            canonical_key=d.canonical_key,
            value_num=value_num,
            value_text=raw_value,
            unit="bool",
            source_attr_label=label,
            confidence=confidence,
            matched_by=matched_by,
        )

    def _extract_string(
        self,
        d: AttrDefinition,
        label: str,
        raw_value: str,
        confidence: float,
        matched_by: MatchedBy,
    ) -> NormalizedFact | None:
        if not raw_value.strip():
            return None
        return NormalizedFact(
            canonical_key=d.canonical_key,
            value_num=None,
            value_text=raw_value,
            unit=d.unit,
            source_attr_label=label,
            confidence=confidence,
            matched_by=matched_by,
        )


def normalize_and_persist(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    normalizer: Normalizer,
) -> dict[str, int]:
    migrate(conn)
    row = conn.execute(
        "SELECT category_id FROM product WHERE id = ?", (product_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"product not found: {product_id}")
    category = CategoryId(row["category_id"])

    raws = conn.execute(
        """
        SELECT source_id, payload_json, captured_at
        FROM spec_raw
        WHERE product_id = ?
        ORDER BY captured_at DESC
        """,
        (product_id,),
    ).fetchall()

    counts: dict[str, int] = {}
    for raw in raws:
        source = SourceId(raw["source_id"])
        if source.value in counts:
            continue
        payload_data = json.loads(raw["payload_json"])
        attrs = payload_data.get("attributes", {})
        captured_at = datetime.fromisoformat(raw["captured_at"])
        stub_payload = SpecPayload(
            product_ref=ProductRef(
                source_id=source,
                brand_id="",
                category_id=category,
                external_id="",
                url="",
                model_name="",
            ),
            attributes=attrs,
            captured_at=captured_at,
        )
        facts = normalizer.normalize(stub_payload, category)
        n = repo.save_spec_facts(
            conn,
            product_id,
            facts,
            source_id=source,
            captured_at=captured_at,
        )
        counts[source.value] = n

    overrides = repo.list_manual_overrides(conn, product_id=product_id)
    if overrides:
        applied = _apply_manual_overrides(conn, product_id, overrides)
        if applied:
            counts["manual"] = applied
    return counts


def _apply_manual_overrides(
    conn,
    product_id: int,
    overrides: list[dict],
) -> int:
    applied = 0
    for o in overrides:
        conn.execute(
            "DELETE FROM spec_fact WHERE product_id = ? AND canonical_key = ?",
            (product_id, o["canonical_key"]),
        )
        conn.execute(
            """
            INSERT INTO spec_fact
              (product_id, canonical_key, value_num, value_text, unit,
               source_id, source_attr_label, confidence, matched_by, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                product_id,
                o["canonical_key"],
                o["value_num"],
                o["value_text"],
                o["unit"],
                SourceId.MANUAL.value,
                "(manual override)",
                1.0,
                MatchedBy.MANUAL.value,
            ),
        )
        applied += 1
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize spec_raw payloads into spec_fact via rule + fuzzy matching"
    )
    parser.add_argument("--product-id", type=int, help="single product id")
    parser.add_argument("--all", action="store_true", help="normalize all products")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="dir containing attr_dictionary.yaml",
    )
    args = parser.parse_args()
    if not (args.all or args.product_id):
        parser.error("either --product-id or --all is required")

    normalizer = Normalizer(load_attr_dictionary(args.config_dir / "attr_dictionary.yaml"))
    conn = connect(db_path())
    try:
        if args.all:
            ids = [r["id"] for r in conn.execute("SELECT id FROM product ORDER BY id")]
        else:
            ids = [args.product_id]
        for pid in ids:
            summary = normalize_and_persist(conn, product_id=pid, normalizer=normalizer)
            total = sum(summary.values())
            print(f"product_id={pid} facts={total} by_source={summary}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
