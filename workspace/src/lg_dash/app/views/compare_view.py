from __future__ import annotations

from pathlib import Path

import streamlit as st

from lg_dash.storage import repo

_RANK_COLOR = {
    "best": "green",
    "worst": "red",
    "neutral": "gray",
    "missing": "gray",
}


def render(conn) -> None:
    basket = list(st.session_state.compare_basket)
    if st.button("← 목록으로", key="compare_back"):
        st.session_state.view = "list"
        st.rerun()

    st.title("📊 제품 비교")

    if not basket:
        st.info("비교할 제품이 없습니다. 목록에서 2~4개를 선택하세요.")
        return
    if len(basket) < 2:
        st.warning("최소 2개 이상을 선택해야 의미있는 비교가 됩니다.")
    if len(basket) > 4:
        st.warning(f"4개까지 비교 가능. 처음 4개만 표시합니다 (선택 {len(basket)}개).")
        basket = basket[:4]

    with st.spinner("비교 데이터 준비 중..."):
        matrix = repo.build_comparison_matrix(conn, basket)

    if not matrix["products"]:
        st.error("선택한 제품을 찾을 수 없습니다.")
        return

    _render_product_header(matrix["products"])
    st.divider()
    _render_matrix(matrix)
    st.divider()
    _render_radar_overlay(matrix["products"])


def _render_product_header(products: list[dict]) -> None:
    cols = st.columns(len(products))
    for col, p in zip(cols, products):
        with col:
            img = p.get("primary_image_path")
            if img and Path(img).exists():
                st.image(img, use_container_width=True)
            else:
                st.markdown(
                    "<div style='height:120px;display:flex;align-items:center;"
                    "justify-content:center;background:#f3f4f6;border-radius:6px;color:#9ca3af;'>"
                    "🖼️</div>",
                    unsafe_allow_html=True,
                )
            st.markdown(f"**{p['model_name']}**")
            st.caption(f"{p['brand_display']} · {p.get('model_code') or '-'}")
            if p.get("overall_score") is not None:
                score = p["overall_score"]
                color = "green" if score >= 0.3 else ("red" if score <= -0.3 else "gray")
                st.markdown(f":{color}[감성 {score:+.2f}]")


def _render_matrix(matrix: dict) -> None:
    products = matrix["products"]
    rows = matrix["rows"]
    if not rows:
        st.caption("정규화된 스펙이 없습니다.")
        return

    st.subheader("스펙 비교")
    header_cols = st.columns([2] + [3] * len(products))
    header_cols[0].markdown("**canonical_key**")
    for col, p in zip(header_cols[1:], products):
        col.markdown(f"**{p['model_name'][:18]}**")

    for row in rows:
        cols = st.columns([2] + [3] * len(products))
        unit = row["unit"] or ""
        unit_suffix = "" if unit in ("bool", "class") else f" ({unit})"
        lower_hint = " ▼" if row["lower_is_better"] else ""
        cols[0].markdown(f"`{row['canonical_key']}`{unit_suffix}{lower_hint}")
        for col, cell in zip(cols[1:], row["cells"]):
            _render_cell(col, cell, row["canonical_key"])


def _render_cell(col, cell: dict, canonical_key: str) -> None:
    rank = cell["rank"]
    color = _RANK_COLOR.get(rank, "gray")

    if rank == "missing":
        col.markdown(":gray[—]")
        return

    if cell["value_num"] is not None:
        num = cell["value_num"]
        unit = cell["unit"] or ""
        if unit == "bool":
            display = "✓" if num == 1.0 else "✗"
        elif unit == "class":
            display = f"{int(num)}등급"
        elif unit == "krw":
            display = f"{int(num):,}원"
        elif num == int(num):
            display = f"{int(num)} {unit}"
        else:
            display = f"{num:g} {unit}"
    elif cell["value_text"]:
        display = cell["value_text"]
    else:
        display = "—"

    badge = " ⚠️" if (cell["confidence"] or 1.0) < 0.7 else ""
    help_text = (
        f"source: {cell['source_id']} · "
        f"label: {cell['source_attr_label']} · "
        f"confidence: {cell['confidence']:.2f}"
        if cell["source_id"]
        else None
    )
    rendered = f":{color}[**{display}**{badge}]"
    if help_text:
        col.markdown(rendered, help=help_text)
    else:
        col.markdown(rendered)


def _render_radar_overlay(products: list[dict]) -> None:
    try:
        import plotly.graph_objects as go
    except ImportError:
        return

    with_tags = [p for p in products if p.get("sentiment_tags")]
    if not with_tags:
        st.caption("감성 분석 결과가 있는 제품이 없습니다. `lg_dash.pipeline.llm_analyze --all` 먼저 실행하세요.")
        return

    st.subheader("감성 태그 오버레이")
    all_keys: list[str] = []
    seen: set[str] = set()
    for p in with_tags:
        for k in p["sentiment_tags"].keys():
            if k not in seen:
                seen.add(k)
                all_keys.append(k)

    fig = go.Figure()
    for p in with_tags:
        tags = p["sentiment_tags"]
        values = [tags.get(k, 0.0) for k in all_keys]
        fig.add_trace(
            go.Scatterpolar(
                r=values + [values[0]],
                theta=all_keys + [all_keys[0]],
                fill="toself",
                name=p["model_name"][:24],
                opacity=0.5,
            )
        )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[-1, 1])),
        showlegend=True,
        height=480,
        margin=dict(l=40, r=40, t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
