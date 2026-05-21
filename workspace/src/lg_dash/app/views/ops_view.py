from __future__ import annotations

import streamlit as st

from lg_dash.storage import repo


def render(conn) -> None:
    if st.button("← 목록으로", key="ops_back"):
        st.session_state.view = "list"
        st.rerun()

    st.title("⚙️ 운영 대시보드")

    _render_overview(conn)
    st.divider()
    _render_refresh_log(conn)
    st.divider()
    _render_llm_log(conn)
    st.divider()
    _render_confidence(conn)
    st.divider()
    _render_manual_override(conn)


def _render_overview(conn) -> None:
    st.subheader("개요")
    cols = st.columns(5)
    cols[0].metric("제품", repo.count(conn, "product"))
    cols[1].metric("정규화 스펙", repo.count(conn, "spec_fact"))
    cols[2].metric("리뷰", repo.count(conn, "raw_review"))
    cols[3].metric("리뷰 요약", repo.count(conn, "review_summary"))
    cols[4].metric("이미지", repo.count(conn, "product_image"))


def _render_refresh_log(conn) -> None:
    st.subheader("최근 새로고침 이력")
    rows = conn.execute(
        """
        SELECT run_id, started_at, finished_at, status,
               items_processed, scope_brands_json, scope_categories_json,
               error_text
        FROM refresh_log
        ORDER BY run_id DESC
        LIMIT 50
        """
    ).fetchall()
    if not rows:
        st.info("새로고침 이력이 없습니다.")
        return
    data = [
        {
            "run_id": r["run_id"],
            "started": r["started_at"],
            "finished": r["finished_at"] or "—",
            "status": r["status"],
            "items": r["items_processed"],
            "brands": r["scope_brands_json"],
            "categories": r["scope_categories_json"],
            "error": (r["error_text"] or "")[:60],
        }
        for r in rows
    ]
    st.dataframe(data, use_container_width=True, hide_index=True)


def _render_llm_log(conn) -> None:
    st.subheader("LLM 호출 누적")
    total = conn.execute(
        """
        SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS total_cost,
               COALESCE(SUM(input_tokens), 0) AS in_tokens,
               COALESCE(SUM(output_tokens), 0) AS out_tokens,
               COALESCE(SUM(cache_hit), 0) AS cache_hits
        FROM llm_call_log
        """
    ).fetchone()
    cols = st.columns(5)
    cols[0].metric("호출 수", total["n"])
    cols[1].metric("누적 비용 (USD)", f"${total['total_cost']:.4f}")
    cols[2].metric("입력 토큰", f"{total['in_tokens']:,}")
    cols[3].metric("출력 토큰", f"{total['out_tokens']:,}")
    cols[4].metric("캐시 히트", total["cache_hits"])

    by_purpose = conn.execute(
        """
        SELECT purpose, COUNT(*) AS calls,
               ROUND(SUM(cost_usd), 4) AS cost_usd,
               SUM(input_tokens) AS in_tokens,
               SUM(output_tokens) AS out_tokens,
               SUM(cache_hit) AS cache_hits
        FROM llm_call_log
        GROUP BY purpose
        """
    ).fetchall()
    if by_purpose:
        st.caption("Purpose별 합계")
        st.dataframe(
            [dict(r) for r in by_purpose],
            use_container_width=True,
            hide_index=True,
        )

    runs = repo.cost_per_run(conn)
    if runs:
        st.caption("Run별 비용 (최근 20건)")
        over_threshold = [r for r in runs if r["cost_usd"] > 1.0]
        if over_threshold:
            st.warning(
                f"⚠️ 단일 새로고침 비용이 $1를 초과한 run {len(over_threshold)}건. "
                "범위를 줄이거나 LLM 폴백을 제한하세요."
            )
        st.dataframe(
            [
                {
                    "run_id": r["run_id"],
                    "started": r["started_at"],
                    "finished": r["finished_at"] or "—",
                    "status": r["status"],
                    "cost_usd": round(r["cost_usd"], 4),
                    "calls": r["calls"],
                }
                for r in runs
            ],
            use_container_width=True,
            hide_index=True,
        )

    recent = conn.execute(
        """
        SELECT id, created_at, product_id, model, purpose,
               input_tokens, output_tokens,
               ROUND(cost_usd, 5) AS cost_usd, latency_ms, cache_hit
        FROM llm_call_log
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()
    if recent:
        st.caption("최근 호출 20건")
        st.dataframe(
            [dict(r) for r in recent],
            use_container_width=True,
            hide_index=True,
        )


def _render_confidence(conn) -> None:
    st.subheader("스펙 정규화 신뢰도")
    rows = conn.execute(
        """
        SELECT
          SUM(CASE WHEN confidence >= 0.95 THEN 1 ELSE 0 END) AS very_high,
          SUM(CASE WHEN confidence >= 0.7 AND confidence < 0.95 THEN 1 ELSE 0 END) AS high,
          SUM(CASE WHEN confidence >= 0.5 AND confidence < 0.7 THEN 1 ELSE 0 END) AS medium,
          SUM(CASE WHEN confidence < 0.5 THEN 1 ELSE 0 END) AS low,
          COUNT(*) AS total
        FROM spec_fact
        """
    ).fetchone()
    if rows["total"] == 0:
        st.info("정규화된 스펙이 없습니다.")
        return
    total = rows["total"]
    cols = st.columns(4)
    cols[0].metric("≥ 0.95", rows["very_high"], f"{rows['very_high'] / total:.1%}")
    cols[1].metric("0.7~0.95", rows["high"], f"{rows['high'] / total:.1%}")
    cols[2].metric("0.5~0.7", rows["medium"], f"{rows['medium'] / total:.1%}")
    cols[3].metric("< 0.5", rows["low"], f"{rows['low'] / total:.1%}")

    low_conf = conn.execute(
        """
        SELECT product_id, canonical_key, source_id, source_attr_label,
               value_num, value_text, ROUND(confidence, 2) AS confidence,
               matched_by
        FROM spec_fact WHERE confidence < 0.7
        ORDER BY confidence ASC LIMIT 50
        """
    ).fetchall()
    if low_conf:
        st.caption("⚠️ 낮은 신뢰도 (50건까지)")
        st.dataframe(
            [dict(r) for r in low_conf],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("모든 스펙이 confidence ≥ 0.7. 🎉")


def _render_manual_override(conn) -> None:
    st.subheader("✍️ 수동 오버라이드 편집")
    st.caption(
        "잘못 매칭된 spec_fact를 수동 수정합니다. "
        "다음 번 `pipeline.normalize` 실행 시 매뉴얼 값이 자동 매칭을 덮어씁니다."
    )
    products = conn.execute(
        """
        SELECT p.id, p.brand_id, p.model_name, p.model_code
        FROM product p ORDER BY p.id
        """
    ).fetchall()
    if not products:
        st.info("제품이 없습니다. 먼저 크롤+정규화를 실행하세요.")
        return

    product_options = {
        f"#{r['id']} · {r['brand_id']} · {r['model_name'][:40]}": r["id"]
        for r in products
    }
    label = st.selectbox("제품 선택", list(product_options.keys()), key="override_product")
    product_id = product_options[label]

    st.markdown("**기존 오버라이드**")
    existing = conn.execute(
        """
        SELECT canonical_key, value_num, value_text, unit, set_by, set_at, notes
        FROM manual_override WHERE product_id = ?
        ORDER BY canonical_key
        """,
        (product_id,),
    ).fetchall()
    if existing:
        st.dataframe(
            [dict(r) for r in existing],
            use_container_width=True,
            hide_index=True,
        )
        delete_key = st.selectbox(
            "삭제할 canonical_key 선택",
            [r["canonical_key"] for r in existing],
            key="override_delete_key",
        )
        if st.button("선택 항목 삭제", key="override_delete_btn"):
            conn.execute(
                "DELETE FROM manual_override WHERE product_id=? AND canonical_key=?",
                (product_id, delete_key),
            )
            st.success(f"삭제됨: {delete_key}")
            st.rerun()
    else:
        st.caption("등록된 오버라이드 없음")

    st.divider()
    st.markdown("**오버라이드 추가/수정**")
    low_conf_keys = [
        r["canonical_key"]
        for r in conn.execute(
            """
            SELECT DISTINCT canonical_key FROM spec_fact
            WHERE product_id = ? AND confidence < 0.7
            ORDER BY canonical_key
            """,
            (product_id,),
        ).fetchall()
    ]
    if low_conf_keys:
        st.caption(f"⚠️ 낮은 신뢰도 후보: {', '.join(low_conf_keys)}")

    with st.form(key=f"override_form_{product_id}"):
        canonical_key = st.text_input(
            "canonical_key",
            placeholder="예: wash_capacity_kg",
            key="override_form_key",
        )
        col_num, col_text, col_unit = st.columns(3)
        with col_num:
            value_num_str = st.text_input(
                "value_num (숫자)",
                placeholder="예: 24.0",
                key="override_form_num",
            )
        with col_text:
            value_text = st.text_input(
                "value_text (선택)",
                placeholder="예: 트루스팀",
                key="override_form_text",
            )
        with col_unit:
            unit = st.text_input(
                "unit",
                placeholder="kg, rpm, dB, bool, …",
                key="override_form_unit",
            )
        notes = st.text_input(
            "비고 (선택)",
            placeholder="예: 다나와 텍스트 파싱 미스",
            key="override_form_notes",
        )
        submitted = st.form_submit_button("저장", type="primary")
    if submitted:
        if not canonical_key or not unit:
            st.error("canonical_key와 unit은 필수입니다.")
        else:
            try:
                value_num = float(value_num_str) if value_num_str.strip() else None
            except ValueError:
                st.error("value_num은 숫자여야 합니다.")
                return
            from lg_dash.storage import repo

            repo.save_manual_override(
                conn,
                product_id=product_id,
                canonical_key=canonical_key.strip(),
                value_num=value_num,
                value_text=value_text.strip() or None,
                unit=unit.strip(),
                set_by="ops_user",
                notes=notes.strip() or None,
            )
            st.success(f"저장됨: {canonical_key}")
            st.rerun()
