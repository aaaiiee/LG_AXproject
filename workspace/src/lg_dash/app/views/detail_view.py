from __future__ import annotations

from pathlib import Path

import streamlit as st

from lg_dash.storage import repo


def render(conn, product_id: int | None) -> None:
    if not product_id:
        st.info("제품을 선택하세요.")
        if st.button("← 목록으로"):
            st.session_state.view = "list"
            st.rerun()
        return

    with st.spinner("로딩 중..."):
        detail = repo.get_product_detail(conn, product_id)
        images = repo.get_product_images(conn, product_id)
        facts = repo.get_product_spec_facts(conn, product_id)
        summary = repo.get_review_summary(conn, product_id)
        reviews = repo.get_raw_reviews(conn, product_id, limit=20)

    if detail is None:
        st.error("제품을 찾을 수 없습니다.")
        if st.button("← 목록으로"):
            st.session_state.view = "list"
            st.rerun()
        return

    if st.button("← 목록으로"):
        st.session_state.view = "list"
        st.rerun()

    st.title(detail["model_name"])
    st.caption(
        f"{detail['brand_display']} · "
        f"{detail['model_code'] or '-'} · "
        f"카테고리 {detail['category_id']} · "
        f"product_id {detail['product_id']}"
    )

    col_img, col_specs = st.columns([1, 2])
    with col_img:
        primary = next((i for i in images if i["is_primary"]), images[0] if images else None)
        if primary and primary["local_path"] and Path(primary["local_path"]).exists():
            st.image(primary["local_path"], use_container_width=True)
            if len(images) > 1:
                st.caption(f"+{len(images) - 1}개 추가 이미지")
        else:
            st.markdown(
                "<div style='aspect-ratio:1;display:flex;align-items:center;"
                "justify-content:center;background:#f3f4f6;border-radius:8px;color:#9ca3af;'>"
                "🖼️ 이미지 없음</div>",
                unsafe_allow_html=True,
            )

    with col_specs:
        st.subheader("핵심 스펙")
        _render_facts_table(facts)

    if summary:
        st.divider()
        st.subheader(f"📊 리뷰 요약 · {summary['evidence_count']}건 분석")
        score = summary["overall_score"]
        color = "green" if score >= 0.3 else ("red" if score <= -0.3 else "gray")
        st.markdown(f":{color}[### 종합 점수 {score:+.2f}]")
        cp, cc = st.columns(2)
        with cp:
            st.markdown("**✓ 장점**")
            for p in summary["pros"]:
                st.markdown(f"- {p}")
        with cc:
            st.markdown("**✗ 단점**")
            for c in summary["cons"]:
                st.markdown(f"- {c}")
        tags = summary["sentiment_tags"]
        if tags:
            _render_radar(tags, detail["model_name"])
        if summary.get("caveats"):
            st.warning(" · ".join(summary["caveats"]))
        st.caption(f"모델: {summary['model_used']} · 생성: {summary['generated_at']}")
    else:
        st.divider()
        st.info("아직 리뷰 분석 결과가 없습니다. `lg_dash.pipeline.llm_analyze` 실행 후 다시 보세요.")

    st.divider()
    st.subheader(f"💬 원본 리뷰 · {len(reviews)}건")
    if not reviews:
        st.info("리뷰 데이터가 없습니다.")
    else:
        for r in reviews[:10]:
            rating = f"★{r['rating']:.0f}" if r["rating"] is not None else "★?"
            date = r["posted_at"][:10] if r["posted_at"] else "날짜 미상"
            with st.expander(f"[{r['source_id']}] {rating} · {date}"):
                st.write(r["text"])
                if r["url"]:
                    st.caption(f"원본: {r['url']}")


def _render_facts_table(facts: list[dict]) -> None:
    seen: dict[str, dict] = {}
    for f in facts:
        if f["canonical_key"] not in seen:
            seen[f["canonical_key"]] = f
    if not seen:
        st.caption("정규화된 스펙이 없습니다. `lg_dash.pipeline.normalize` 실행이 필요합니다.")
        return
    for key, f in seen.items():
        if f["value_text"] is not None:
            display_val = f["value_text"]
        elif f["value_num"] is not None:
            num = f["value_num"]
            display_val = f"{num:g}" if num != int(num) else f"{int(num)}"
        else:
            display_val = "—"
        unit = f["unit"]
        if unit not in ("bool", "class"):
            display_val = f"{display_val} {unit}"
        elif unit == "bool":
            display_val = "✓" if f["value_num"] == 1.0 else ("✗" if f["value_num"] == 0.0 else display_val)
        badge = " :orange[⚠️]" if f["confidence"] < 0.7 else ""
        help_text = (
            f"canonical_key: {key} · "
            f"source: {f['source_id']} · "
            f"label: {f['source_attr_label']} · "
            f"matched_by: {f['matched_by']} · "
            f"confidence: {f['confidence']:.2f}"
        )
        st.markdown(f"**{key}**: {display_val}{badge}", help=help_text)


def _render_radar(tags: dict[str, float], product_name: str) -> None:
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.caption("plotly 미설치 — 레이더차트 생략")
        return
    keys = list(tags.keys())
    values = list(tags.values())
    fig = go.Figure(
        data=go.Scatterpolar(
            r=values + [values[0]],
            theta=keys + [keys[0]],
            fill="toself",
            name=product_name,
        )
    )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[-1, 1])),
        showlegend=False,
        height=380,
        margin=dict(l=40, r=40, t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
