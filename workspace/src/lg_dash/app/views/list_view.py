from __future__ import annotations

from pathlib import Path

import streamlit as st

from lg_dash.storage import repo


def _toggle_compare(product_id: int) -> None:
    ss = st.session_state
    basket = ss.compare_basket
    key = f"compare_{product_id}"
    if ss.get(key):
        if product_id not in basket:
            basket.append(product_id)
    else:
        if product_id in basket:
            basket.remove(product_id)


def render(conn) -> None:
    ss = st.session_state
    with st.spinner("로딩 중..."):
        products = repo.list_products_filtered(
            conn,
            brand_ids=ss.brand_ids or None,
            category_id=ss.category_id or None,
            search=ss.search or None,
        )

    st.subheader(f"제품 목록 · {len(products)}개")
    if not products:
        st.info("조건에 맞는 제품이 없습니다. 필터를 조정해보세요.")
        return

    cols_per_row = 3
    for row_start in range(0, len(products), cols_per_row):
        cols = st.columns(cols_per_row)
        for offset, col in enumerate(cols):
            idx = row_start + offset
            if idx >= len(products):
                break
            with col:
                _render_card(products[idx])


def _render_card(p: dict) -> None:
    with st.container(border=True):
        img_path = p.get("primary_image_path")
        if img_path and Path(img_path).exists():
            st.image(img_path, use_container_width=True)
        else:
            st.markdown(
                "<div style='height:160px;display:flex;align-items:center;"
                "justify-content:center;background:#f3f4f6;border-radius:6px;color:#9ca3af;'>"
                "🖼️ 이미지 없음</div>",
                unsafe_allow_html=True,
            )

        st.markdown(f"**{p['model_name']}**")
        st.caption(f"{p['brand_display']} · {p.get('model_code') or '-'}")

        facts = p["facts"]
        spec_bits: list[str] = []
        if "wash_capacity_kg" in facts and facts["wash_capacity_kg"]["value_num"] is not None:
            spec_bits.append(f"세탁 {facts['wash_capacity_kg']['value_num']:g}kg")
        if "dry_capacity_kg" in facts and facts["dry_capacity_kg"]["value_num"] is not None:
            spec_bits.append(f"건조 {facts['dry_capacity_kg']['value_num']:g}kg")
        if "energy_grade" in facts and facts["energy_grade"]["value_num"] is not None:
            spec_bits.append(f"에너지 {int(facts['energy_grade']['value_num'])}등급")
        if "noise_db" in facts and facts["noise_db"]["value_num"] is not None:
            spec_bits.append(f"{facts['noise_db']['value_num']:g}dB")
        if spec_bits:
            st.caption(" · ".join(spec_bits))

        if "price_krw" in facts and facts["price_krw"]["value_num"] is not None:
            st.caption(f"💰 {int(facts['price_krw']['value_num']):,}원")

        if p.get("overall_score") is not None:
            score = p["overall_score"]
            color = "green" if score >= 0.3 else ("red" if score <= -0.3 else "gray")
            st.markdown(f":{color}[**감성 {score:+.2f}**]")
            if p.get("pros"):
                st.caption("✓ " + " · ".join(p["pros"][:2]))
        else:
            st.caption("(리뷰 분석 없음)")

        c_check, c_btn = st.columns([1, 2])
        with c_check:
            pid = p["product_id"]
            key = f"compare_{pid}"
            if key not in st.session_state:
                st.session_state[key] = pid in st.session_state.compare_basket
            st.checkbox(
                "비교",
                key=key,
                on_change=_toggle_compare,
                args=(pid,),
            )
        with c_btn:
            if st.button(
                "상세 →",
                key=f"detail_{p['product_id']}",
                use_container_width=True,
            ):
                st.session_state.selected_product_id = p["product_id"]
                st.session_state.view = "detail"
                st.rerun()
