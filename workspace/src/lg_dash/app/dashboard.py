from __future__ import annotations

import streamlit as st

from lg_dash.app.views import compare_view, detail_view, list_view, ops_view
from lg_dash.storage import repo
from lg_dash.storage.db import connect, db_path

st.set_page_config(page_title="lg_dash 비교 대시보드", layout="wide")


@st.cache_resource
def _get_conn():
    return connect(db_path())


def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("view", "list")
    ss.setdefault("selected_product_id", None)
    ss.setdefault("brand_ids", [])
    ss.setdefault("category_id", "washer")
    ss.setdefault("search", "")
    ss.setdefault("compare_basket", [])


def _render_sidebar(conn) -> None:
    with st.sidebar:
        st.header("🔎 필터")
        brands = repo.list_brands(conn)
        brand_map = {b.id: b.display for b in brands}
        st.multiselect(
            "🏷 브랜드",
            options=list(brand_map.keys()),
            format_func=lambda x: brand_map.get(x, x),
            key="brand_ids",
        )
        cats = repo.list_categories(conn)
        cat_map = {c.id.value: c.display for c in cats}
        st.radio(
            "📂 카테고리",
            options=list(cat_map.keys()),
            format_func=lambda x: cat_map.get(x, x),
            key="category_id",
            horizontal=True,
        )
        st.text_input("🔎 검색어", key="search", placeholder="모델명·코드")

        st.divider()
        basket_n = len(st.session_state.compare_basket)
        st.caption(f"🛒 비교 카트: {basket_n}개")
        can_compare = 2 <= basket_n <= 4
        if st.button(
            "비교하기",
            disabled=not can_compare,
            help="2~4개 제품을 카트에 담아주세요" if not can_compare else None,
            use_container_width=True,
            type="primary" if can_compare else "secondary",
        ):
            st.session_state.view = "compare"
            st.rerun()
        if basket_n:
            if st.button("카트 비우기", use_container_width=True):
                st.session_state.compare_basket = []
                st.rerun()

        st.divider()
        if st.button("⚙️ 운영 보기", use_container_width=True):
            st.session_state.view = "ops"
            st.rerun()

        st.divider()
        st.caption("⚠️ 사내 한정 — 외부 공유 금지")


def main() -> None:
    _init_state()
    conn = _get_conn()
    _render_sidebar(conn)

    view = st.session_state.view
    if view == "detail":
        detail_view.render(conn, st.session_state.selected_product_id)
    elif view == "compare":
        compare_view.render(conn)
    elif view == "ops":
        ops_view.render(conn)
    else:
        list_view.render(conn)


main()
