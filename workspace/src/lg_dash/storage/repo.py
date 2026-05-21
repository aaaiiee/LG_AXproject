from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime

from lg_dash.models import (
    Brand,
    Category,
    CategoryId,
    NormalizedFact,
    ProductRef,
    RawReview,
    RefreshStatus,
    SourceId,
    SpecPayload,
)


def upsert_brand(conn: sqlite3.Connection, brand: Brand) -> None:
    config = brand.model_dump(mode="json", exclude={"id", "display"})
    conn.execute(
        """
        INSERT INTO brand (id, display, config_json)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          display = excluded.display,
          config_json = excluded.config_json
        """,
        (brand.id, brand.display, json.dumps(config, ensure_ascii=False)),
    )


def upsert_category(conn: sqlite3.Connection, category: Category) -> None:
    conn.execute(
        """
        INSERT INTO category (id, display, aliases_json)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          display = excluded.display,
          aliases_json = excluded.aliases_json
        """,
        (
            category.id.value,
            category.display,
            json.dumps(category.aliases, ensure_ascii=False),
        ),
    )


def list_brands(conn: sqlite3.Connection) -> list[Brand]:
    rows = conn.execute("SELECT id, display, config_json FROM brand ORDER BY id").fetchall()
    out: list[Brand] = []
    for r in rows:
        cfg = json.loads(r["config_json"])
        out.append(Brand(id=r["id"], display=r["display"], **cfg))
    return out


def list_categories(conn: sqlite3.Connection) -> list[Category]:
    rows = conn.execute(
        "SELECT id, display, aliases_json FROM category ORDER BY id"
    ).fetchall()
    return [
        Category(
            id=CategoryId(r["id"]),
            display=r["display"],
            aliases=json.loads(r["aliases_json"]),
        )
        for r in rows
    ]


def upsert_product(conn: sqlite3.Connection, ref: ProductRef) -> int:
    row = conn.execute(
        """
        SELECT id FROM product
        WHERE brand_id = ?
          AND COALESCE(model_code, model_name) = COALESCE(?, ?)
        """,
        (ref.brand_id, ref.model_code, ref.model_name),
    ).fetchone()
    if row is not None:
        conn.execute(
            "UPDATE product SET last_refreshed_at = datetime('now') WHERE id = ?",
            (row["id"],),
        )
        return int(row["id"])
    cur = conn.execute(
        """
        INSERT INTO product (brand_id, category_id, model_name, model_code, last_refreshed_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (
            ref.brand_id,
            ref.category_id.value,
            ref.model_name,
            ref.model_code,
        ),
    )
    return int(cur.lastrowid)


def upsert_product_source_ref(
    conn: sqlite3.Connection, product_id: int, ref: ProductRef
) -> None:
    conn.execute(
        """
        INSERT INTO product_source_ref (product_id, source_id, external_id, url, last_fetched_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(product_id, source_id) DO UPDATE SET
          external_id = excluded.external_id,
          url = excluded.url,
          last_fetched_at = datetime('now')
        """,
        (product_id, ref.source_id.value, ref.external_id, ref.url),
    )


def save_spec_raw(
    conn: sqlite3.Connection, product_id: int, payload: SpecPayload
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO spec_raw (product_id, source_id, payload_json, captured_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            product_id,
            payload.product_ref.source_id.value,
            json.dumps(
                {
                    "attributes": payload.attributes,
                    "image_urls": payload.image_urls,
                },
                ensure_ascii=False,
            ),
            payload.captured_at.isoformat(),
        ),
    )


def save_raw_reviews(
    conn: sqlite3.Connection, product_id: int, reviews: Iterable[RawReview]
) -> int:
    inserted = 0
    for r in reviews:
        text_hash = hashlib.sha256(r.text.encode("utf-8")).hexdigest()[:16]
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO raw_review
              (product_id, source_id, author_hash, rating, text, posted_at,
               url, language, text_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                r.product_ref.source_id.value,
                r.author_hash,
                r.rating,
                r.text,
                r.posted_at.isoformat() if r.posted_at else None,
                r.url,
                r.language,
                text_hash,
            ),
        )
        if cur.rowcount > 0:
            inserted += 1
    return inserted


def start_refresh(
    conn: sqlite3.Connection,
    *,
    brands: list[str],
    categories: list[CategoryId],
    product_ids: list[int] | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO refresh_log
          (scope_brands_json, scope_categories_json, scope_product_ids_json, status)
        VALUES (?, ?, ?, ?)
        """,
        (
            json.dumps(brands),
            json.dumps([c.value for c in categories]),
            json.dumps(product_ids or []),
            RefreshStatus.RUNNING.value,
        ),
    )
    return int(cur.lastrowid)


def finalize_refresh(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    items_processed: int = 0,
    error_text: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE refresh_log
        SET status = ?,
            items_processed = ?,
            error_text = ?,
            finished_at = datetime('now')
        WHERE run_id = ?
        """,
        (status, items_processed, error_text, run_id),
    )


def save_review_summary(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    result,
    status: str = "ok",
) -> None:
    conn.execute(
        """
        INSERT INTO review_summary
          (product_id, pros_json, cons_json, sentiment_tags_json,
           overall_score, evidence_count, caveats_json,
           generated_at, model_used, input_hash, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
        ON CONFLICT(product_id) DO UPDATE SET
          pros_json = excluded.pros_json,
          cons_json = excluded.cons_json,
          sentiment_tags_json = excluded.sentiment_tags_json,
          overall_score = excluded.overall_score,
          evidence_count = excluded.evidence_count,
          caveats_json = excluded.caveats_json,
          generated_at = datetime('now'),
          model_used = excluded.model_used,
          input_hash = excluded.input_hash,
          status = excluded.status
        """,
        (
            product_id,
            json.dumps(result.pros, ensure_ascii=False),
            json.dumps(result.cons, ensure_ascii=False),
            json.dumps(result.sentiment_tags, ensure_ascii=False),
            result.overall_score,
            result.evidence_count,
            json.dumps(result.caveats, ensure_ascii=False),
            result.model_used,
            result.input_hash,
            status,
        ),
    )


def save_llm_call_log(
    conn: sqlite3.Connection,
    *,
    product_id: int | None,
    purpose: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    cache_hit: bool = False,
) -> None:
    conn.execute(
        """
        INSERT INTO llm_call_log
          (product_id, purpose, model, input_tokens, output_tokens,
           cost_usd, latency_ms, cache_hit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            purpose,
            model,
            input_tokens,
            output_tokens,
            cost_usd,
            latency_ms,
            1 if cache_hit else 0,
        ),
    )


def cost_per_run(conn: sqlite3.Connection, *, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """
        SELECT r.run_id, r.started_at, r.finished_at, r.status,
               COALESCE(SUM(l.cost_usd), 0.0) AS cost_usd,
               COUNT(l.id) AS calls
        FROM refresh_log r
        LEFT JOIN llm_call_log l
          ON l.created_at >= r.started_at
         AND (r.finished_at IS NULL OR l.created_at <= r.finished_at)
        GROUP BY r.run_id
        ORDER BY r.started_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_product_image(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    source_id: SourceId,
    idx: int,
    original_url: str,
    local_path: str | None = None,
    width: int | None = None,
    height: int | None = None,
    bytes_len: int | None = None,
    is_primary: bool = False,
    status: str = "ok",
) -> None:
    conn.execute(
        """
        INSERT INTO product_image
          (product_id, source_id, idx, original_url, local_path,
           width, height, bytes, is_primary, fetched_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
        ON CONFLICT(product_id, idx) DO UPDATE SET
          source_id = excluded.source_id,
          original_url = excluded.original_url,
          local_path = excluded.local_path,
          width = excluded.width,
          height = excluded.height,
          bytes = excluded.bytes,
          is_primary = excluded.is_primary,
          fetched_at = datetime('now'),
          status = excluded.status
        """,
        (
            product_id,
            source_id.value,
            idx,
            original_url,
            local_path,
            width,
            height,
            bytes_len,
            1 if is_primary else 0,
            status,
        ),
    )


def save_spec_facts(
    conn: sqlite3.Connection,
    product_id: int,
    facts: Iterable[NormalizedFact],
    *,
    source_id: SourceId,
    captured_at: datetime,
) -> int:
    conn.execute(
        "DELETE FROM spec_fact WHERE product_id = ? AND source_id = ?",
        (product_id, source_id.value),
    )
    captured_iso = captured_at.isoformat()
    inserted = 0
    for f in facts:
        conn.execute(
            """
            INSERT INTO spec_fact
              (product_id, canonical_key, value_num, value_text, unit,
               source_id, source_attr_label, confidence, matched_by, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                f.canonical_key,
                f.value_num,
                f.value_text,
                f.unit,
                source_id.value,
                f.source_attr_label,
                f.confidence,
                f.matched_by.value,
                captured_iso,
            ),
        )
        inserted += 1
    return inserted


def list_products_filtered(
    conn: sqlite3.Connection,
    *,
    brand_ids: list[str] | None = None,
    category_id: str | None = None,
    search: str | None = None,
) -> list[dict]:
    sql = [
        "SELECT p.id AS product_id, p.brand_id, b.display AS brand_display,",
        "       p.category_id, p.model_name, p.model_code, p.last_refreshed_at,",
        "       (SELECT local_path FROM product_image",
        "        WHERE product_id=p.id AND is_primary=1 AND status='ok' LIMIT 1)",
        "         AS primary_image_path,",
        "       rs.overall_score, rs.pros_json",
        "FROM product p",
        "JOIN brand b ON p.brand_id = b.id",
        "LEFT JOIN review_summary rs ON rs.product_id = p.id AND rs.status='ok'",
        "WHERE 1=1",
    ]
    params: list = []
    if brand_ids:
        sql.append("AND p.brand_id IN (" + ",".join("?" * len(brand_ids)) + ")")
        params.extend(brand_ids)
    if category_id:
        sql.append("AND p.category_id = ?")
        params.append(category_id)
    if search:
        sql.append("AND (p.model_name LIKE ? OR p.model_code LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])
    sql.append("ORDER BY p.id")
    rows = conn.execute("\n".join(sql), params).fetchall()

    out: list[dict] = []
    for r in rows:
        facts = {}
        for fr in conn.execute(
            """
            SELECT canonical_key, value_num, value_text, unit, confidence
            FROM spec_fact WHERE product_id = ?
            """,
            (r["product_id"],),
        ).fetchall():
            facts[fr["canonical_key"]] = {
                "value_num": fr["value_num"],
                "value_text": fr["value_text"],
                "unit": fr["unit"],
                "confidence": fr["confidence"],
            }
        out.append(
            {
                "product_id": r["product_id"],
                "brand_id": r["brand_id"],
                "brand_display": r["brand_display"],
                "category_id": r["category_id"],
                "model_name": r["model_name"],
                "model_code": r["model_code"],
                "last_refreshed_at": r["last_refreshed_at"],
                "primary_image_path": r["primary_image_path"],
                "overall_score": r["overall_score"],
                "pros": json.loads(r["pros_json"]) if r["pros_json"] else [],
                "facts": facts,
            }
        )
    return out


def get_product_detail(conn: sqlite3.Connection, product_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT p.id, p.brand_id, b.display AS brand_display,
               p.category_id, p.model_name, p.model_code,
               p.first_seen_at, p.last_refreshed_at, p.is_active
        FROM product p JOIN brand b ON p.brand_id = b.id
        WHERE p.id = ?
        """,
        (product_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "product_id": row["id"],
        "brand_id": row["brand_id"],
        "brand_display": row["brand_display"],
        "category_id": row["category_id"],
        "model_name": row["model_name"],
        "model_code": row["model_code"],
        "first_seen_at": row["first_seen_at"],
        "last_refreshed_at": row["last_refreshed_at"],
        "is_active": bool(row["is_active"]),
    }


def get_product_spec_facts(
    conn: sqlite3.Connection, product_id: int
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT canonical_key, value_num, value_text, unit, source_id,
               source_attr_label, confidence, matched_by, captured_at
        FROM spec_fact WHERE product_id = ?
        ORDER BY canonical_key
        """,
        (product_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_product_images(
    conn: sqlite3.Connection, product_id: int, *, ok_only: bool = True
) -> list[dict]:
    base_sql = """
        SELECT id, idx, source_id, original_url, local_path,
               width, height, bytes, is_primary, status
        FROM product_image WHERE product_id = ?
    """
    if ok_only:
        base_sql += " AND status = 'ok'"
    base_sql += " ORDER BY is_primary DESC, idx ASC"
    rows = conn.execute(base_sql, (product_id,)).fetchall()
    return [dict(r) for r in rows]


def get_review_summary(conn: sqlite3.Connection, product_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT pros_json, cons_json, sentiment_tags_json, overall_score,
               evidence_count, caveats_json, generated_at, model_used,
               input_hash, status
        FROM review_summary WHERE product_id = ?
        """,
        (product_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "pros": json.loads(row["pros_json"]),
        "cons": json.loads(row["cons_json"]),
        "sentiment_tags": json.loads(row["sentiment_tags_json"]),
        "overall_score": row["overall_score"],
        "evidence_count": row["evidence_count"],
        "caveats": json.loads(row["caveats_json"]),
        "generated_at": row["generated_at"],
        "model_used": row["model_used"],
        "status": row["status"],
    }


def get_raw_reviews(
    conn: sqlite3.Connection,
    product_id: int,
    *,
    source_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    sql = """
        SELECT id, source_id, author_hash, rating, text, posted_at, url
        FROM raw_review WHERE product_id = ?
    """
    params: list = [product_id]
    if source_id:
        sql += " AND source_id = ?"
        params.append(source_id)
    sql += " ORDER BY posted_at DESC NULLS LAST, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


LOWER_IS_BETTER_KEYS = {"noise_db", "price_krw", "power_consumption_w"}


def build_comparison_matrix(
    conn: sqlite3.Connection, product_ids: list[int]
) -> dict:
    if not product_ids:
        return {"products": [], "rows": []}

    placeholders = ",".join("?" * len(product_ids))
    rows = conn.execute(
        f"""
        SELECT p.id, p.brand_id, b.display AS brand_display,
               p.category_id, p.model_name, p.model_code,
               (SELECT local_path FROM product_image
                WHERE product_id=p.id AND is_primary=1 AND status='ok' LIMIT 1)
                 AS primary_image_path,
               rs.overall_score, rs.sentiment_tags_json, rs.pros_json, rs.cons_json
        FROM product p
        JOIN brand b ON p.brand_id = b.id
        LEFT JOIN review_summary rs ON rs.product_id = p.id AND rs.status='ok'
        WHERE p.id IN ({placeholders})
        """,
        product_ids,
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    products: list[dict] = []
    for pid in product_ids:
        r = by_id.get(pid)
        if r is None:
            continue
        products.append(
            {
                "product_id": r["id"],
                "brand_id": r["brand_id"],
                "brand_display": r["brand_display"],
                "category_id": r["category_id"],
                "model_name": r["model_name"],
                "model_code": r["model_code"],
                "primary_image_path": r["primary_image_path"],
                "overall_score": r["overall_score"],
                "sentiment_tags": json.loads(r["sentiment_tags_json"])
                if r["sentiment_tags_json"]
                else {},
                "pros": json.loads(r["pros_json"]) if r["pros_json"] else [],
                "cons": json.loads(r["cons_json"]) if r["cons_json"] else [],
            }
        )

    fact_rows = conn.execute(
        f"""
        SELECT product_id, canonical_key, value_num, value_text, unit,
               source_id, source_attr_label, confidence
        FROM spec_fact WHERE product_id IN ({placeholders})
        """,
        product_ids,
    ).fetchall()

    best_fact: dict[tuple[int, str], dict] = {}
    for f in fact_rows:
        k = (f["product_id"], f["canonical_key"])
        if k not in best_fact or best_fact[k]["confidence"] < f["confidence"]:
            best_fact[k] = dict(f)

    canonical_keys = sorted({k for (_, k) in best_fact.keys()})

    rows_out: list[dict] = []
    for ck in canonical_keys:
        lower_better = ck in LOWER_IS_BETTER_KEYS
        unit: str | None = None
        cells: list[dict] = []
        for pid in product_ids:
            fact = best_fact.get((pid, ck))
            if fact is not None:
                if unit is None:
                    unit = fact["unit"]
                cells.append(
                    {
                        "product_id": pid,
                        "value_num": fact["value_num"],
                        "value_text": fact["value_text"],
                        "unit": fact["unit"],
                        "confidence": fact["confidence"],
                        "source_id": fact["source_id"],
                        "source_attr_label": fact["source_attr_label"],
                        "rank": "neutral",
                    }
                )
            else:
                cells.append(
                    {
                        "product_id": pid,
                        "value_num": None,
                        "value_text": None,
                        "unit": None,
                        "confidence": None,
                        "source_id": None,
                        "source_attr_label": None,
                        "rank": "missing",
                    }
                )

        numeric = [c for c in cells if c["value_num"] is not None]
        missing_present = any(c["rank"] == "missing" for c in cells)
        if len(numeric) >= 2:
            values = [c["value_num"] for c in numeric]
            if len(set(values)) > 1:
                best_val = min(values) if lower_better else max(values)
                worst_val = max(values) if lower_better else min(values)
                for c in numeric:
                    if c["value_num"] == best_val:
                        c["rank"] = "best"
                    elif c["value_num"] == worst_val:
                        c["rank"] = "worst"
        elif len(numeric) == 1 and missing_present:
            numeric[0]["rank"] = "best"

        rows_out.append(
            {
                "canonical_key": ck,
                "unit": unit,
                "lower_is_better": lower_better,
                "cells": cells,
            }
        )

    return {"products": products, "rows": rows_out}


def save_manual_override(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    canonical_key: str,
    value_num: float | None,
    value_text: str | None,
    unit: str,
    set_by: str = "user",
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO manual_override
          (product_id, canonical_key, value_num, value_text, unit, set_by, set_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)
        ON CONFLICT(product_id, canonical_key) DO UPDATE SET
          value_num = excluded.value_num,
          value_text = excluded.value_text,
          unit = excluded.unit,
          set_by = excluded.set_by,
          set_at = datetime('now'),
          notes = excluded.notes
        """,
        (product_id, canonical_key, value_num, value_text, unit, set_by, notes),
    )


def list_manual_overrides(
    conn: sqlite3.Connection, *, product_id: int
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, product_id, canonical_key, value_num, value_text, unit,
               set_by, set_at, notes
        FROM manual_override
        WHERE product_id = ?
        ORDER BY canonical_key
        """,
        (product_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_manual_override(
    conn: sqlite3.Connection, *, product_id: int, canonical_key: str
) -> None:
    conn.execute(
        "DELETE FROM manual_override WHERE product_id = ? AND canonical_key = ?",
        (product_id, canonical_key),
    )


def count(conn: sqlite3.Connection, table: str) -> int:
    allowed = {
        "brand",
        "category",
        "product",
        "product_source_ref",
        "spec_raw",
        "spec_fact",
        "raw_review",
        "review_summary",
        "product_image",
        "refresh_log",
        "llm_call_log",
        "manual_override",
    }
    if table not in allowed:
        raise ValueError(f"unknown table: {table}")
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"])
