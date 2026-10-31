from __future__ import annotations

from datetime import datetime
from contextlib import closing
import io
import json
import os
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from lotto.core import Draw, backtest, generate, match, parse_numbers, stats
from lotto import purchases
from lotto.browser_store import sync as sync_browser_purchases
from lotto.refresh_ui import auto_results
from lotto.storage import (CSV_FIELDS, connect, export_draws, load_draws, read_csv,
                           recommendation_rows, save_draws, save_recommendations)

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="로또 랩 · 6/45", page_icon="🍀", layout="wide")
st.markdown("""<style>
.block-container {max-width:1200px; padding-top:2rem; padding-bottom:3rem;}
h1 {letter-spacing:-1.5px;} h2,h3 {letter-spacing:-.6px;}
[data-testid="stMetric"] {background:white; padding:20px; border:1px solid #e2e8ed; border-radius:16px;}
.hero {padding:26px 30px; border-radius:20px; background:#123b3b; color:#effdfa; margin-bottom:24px;}
.hero .eyebrow {font-size:12px; color:#9ad9cd; letter-spacing:2px; font-weight:700;}
.hero h2 {color:white; margin:8px 0; font-size:29px;}
.hero p {color:#c1ded9; margin:0; font-size:15px; line-height:1.7;}
.ball {display:inline-flex; width:42px; height:42px; border-radius:50%; align-items:center; justify-content:center; color:#fff; font-weight:750; margin:5px 5px 5px 0; font-size:17px;}
.ticket {background:white; border:1px solid #e2e8ed; border-radius:15px; padding:14px 20px; margin-bottom:10px;}
.ticket-label {font-size:12px; color:#657c87; font-weight:600; margin-bottom:4px;}
.muted {color:#637883; font-size:13px;}
div[data-testid="stSidebar"] {border-right:1px solid #dfe8eb;}
</style>""", unsafe_allow_html=True)


def balls(numbers):
    colors = ["#c49120", "#3c88bd", "#d76662", "#6e7b89", "#59966e"]
    return "".join(f'<span class="ball" style="background:{colors[(n - 1) // 10]}">{n}</span>' for n in numbers)


def csv_bytes(frame):
    return frame.to_csv(index=False).encode("utf-8-sig")


def chart(fig):
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=20, b=10), font=dict(color="#29434e"))
    st.plotly_chart(fig, width="stretch")


def database_path():
    explicit = os.environ.get("LOTTO_DB_PATH")
    if explicit:
        return explicit
    if os.environ.get("LOTTO_LOCAL_MODE") == "1":
        return str(ROOT / "data/lotto.sqlite3")
    if "workspace" not in st.session_state:
        st.session_state.workspace = tempfile.TemporaryDirectory(prefix="lotto-session-")
    return str(Path(st.session_state.workspace.name) / "lotto.sqlite3")


def main():
    path = database_path()
    with closing(connect(path)) as db:
        purchases.setup(db)
        snapshot = ROOT / "data/official_history.csv"
        if not os.environ.get("LOTTO_DB_PATH") and not load_draws(db) and snapshot.exists():
            try:
                save_draws(db, read_csv(snapshot.read_bytes()))
                with db:
                    db.execute("UPDATE draws SET source=?", ("공식 결과 수집 CSV · 동봉본",))
            except (ValueError, UnicodeError) as exc:
                st.error(f"동봉 데이터를 읽지 못했습니다: {exc}")
        if not os.environ.get("LOTTO_DB_PATH") and os.environ.get("LOTTO_LOCAL_MODE") != "1":
            sync_browser_purchases(db, st.session_state.workspace.name)
        auto_results(path)
        draws = load_draws(db)
        latest = draws[-1] if draws else None
        with st.sidebar:
            st.title("🍀 로또 랩")
            st.caption("LOTTO LAB / 6·45")
            if not os.environ.get("LOTTO_DB_PATH") and os.environ.get("LOTTO_LOCAL_MODE") != "1":
                st.caption("구매 이력은 이 브라우저에 자동 저장됩니다. 다른 기기에서는 JSON 백업을 가져오세요. 추천만 한 기록은 임시 보관됩니다.")
            page = st.radio("메뉴", ["대시보드", "통계 분석", "번호 추천", "구매 이력", "추천 기록 · 결과", "과거 검증", "AJ 연구", "데이터 관리"], label_visibility="collapsed", key="page")
            st.divider()
            st.caption("데이터 반영 현황")
            st.write(f"**{latest.round}회까지 · {len(draws):,}개 회차**" if latest else "등록된 당첨 이력이 없습니다.")
            if latest:
                st.caption(f"마지막 추첨일 {latest.date}")
            st.caption("각 조합의 1등 확률은 동일합니다.\n통계는 과거 기록이며 예측 확률이 아닙니다.")
            st.link_button("동행복권 공식 결과 ↗", "https://www.dhlottery.co.kr/lt645/result")

        if page == "대시보드":
            st.markdown('<div class="hero"><div class="eyebrow">LOTTO LAB · PERSONAL ANALYTICS</div><h2>기록을 살펴보고, 나의 조합을 만드세요.</h2><p>당첨 이력 분석부터 번호 생성과 결과 확인까지.<br>추천에 적용한 기준을 직접 확인할 수 있습니다.</p></div>', unsafe_allow_html=True)
            a, b, c = st.columns(3)
            a.metric("등록된 당첨 이력", f"{len(draws):,}회")
            b.metric("마지막 등록 회차", f"{latest.round}회" if latest else "—")
            c.metric("저장한 추천 조합", f"{db.execute('SELECT count(*) FROM recommendations').fetchone()[0]:,}게임")
            st.write("")
            if latest:
                st.subheader(f"마지막 등록 결과 · {latest.round}회")
                st.caption(f"{latest.date} 추첨 · 출처: {latest.source} · 실시간 최신 여부는 데이터 관리에서 확인하세요.")
                st.markdown(balls(latest.numbers) + '<span class="muted"> ＋ 보너스 </span>' + balls([latest.bonus]), unsafe_allow_html=True)
                st.subheader("최근 10회 번호별 출현")
                f = stats(draws[-10:])["frequency"]
                chart(px.bar(x=list(f), y=list(f.values()), labels={"x": "번호", "y": "출현 횟수"}, color_discrete_sequence=["#0f766e"]))
            else:
                st.info("데이터 관리에서 공식 결과를 가져오거나 CSV를 등록하세요. 당첨 이력이 없어도 무작위·조건 지정 추천을 사용할 수 있습니다.")
                st.subheader("사용 순서")
                for col, title, body in zip(st.columns(3), ["01 · 데이터 준비", "02 · 나의 조합", "03 · 결과 확인"], ["회차별 결과를 가져와 통계를 확인합니다.", "조건을 정하고 추천 번호를 저장합니다.", "추첨 결과를 등록하면 자동으로 대조합니다."]):
                    with col:
                        with st.container(border=True):
                            st.markdown(f"**{title}**")
                            st.write(body)

        elif page == "통계 분석":
            st.title("통계 분석")
            st.caption("본번호 6개 기준으로 계산합니다. 보너스번호는 제외됩니다.")
            if not draws:
                st.info("데이터 관리에서 당첨 이력을 먼저 등록하세요.")
                return
            period = st.selectbox("분석 구간", ["최근 10회", "최근 50회", "최근 100회", "전체"])
            selection = draws if period == "전체" else draws[-int(period.split()[1][:-1]):]
            s = stats(selection)
            st.caption(f"실제 분석: {selection[0].round}~{selection[-1].round}회 · 등록된 {len(selection)}개 회차")
            missing = [n for n in range(selection[0].round, selection[-1].round + 1) if n not in {d.round for d in selection}]
            if missing:
                st.warning(f"선택 구간에 {len(missing)}개 회차가 누락되었습니다. 출현 횟수와 경과 회차 해석에 유의하세요.")
            frame = pd.DataFrame({"번호": range(1, 46), "출현 횟수": s["frequency"].values(), "마지막 출현 후 경과 회차": s["gap"].values()})
            st.subheader("번호별 출현 횟수")
            chart(px.bar(frame, x="번호", y="출현 횟수", color_discrete_sequence=["#0f766e"]))
            st.caption("경과 회차가 비어 있는 번호는 선택한 구간에서 출현하지 않았습니다. 다음 회차 출현 가능성을 뜻하지 않습니다.")
            st.dataframe(frame, hide_index=True, width="stretch")
            a, b = st.columns(2)
            with a:
                st.subheader("홀수 개수 분포")
                chart(px.bar(x=list(range(7)), y=[s["odd"][i] for i in range(7)], labels={"x": "홀수 개수", "y": "회차 수"}, color_discrete_sequence=["#3c88bd"]))
            with b:
                st.subheader("번호 합계 분포")
                chart(px.histogram(x=s["sums"], nbins=20, labels={"x": "번호 합계", "y": "회차 수"}, color_discrete_sequence=["#0f766e"]))
            a, b = st.columns(2)
            with a:
                st.subheader("구간별 번호 출현")
                chart(px.bar(x=["1~10", "11~20", "21~30", "31~40", "41~45"], y=[s["zones"][i] for i in range(5)], labels={"x": "구간", "y": "출현 횟수"}, color_discrete_sequence=["#59966e"]))
                st.caption("41~45 구간은 다른 구간보다 번호 수가 적습니다.")
            with b:
                st.subheader("연속번호 쌍 개수")
                chart(px.bar(x=list(range(6)), y=[s["consecutive"][i] for i in range(6)], labels={"x": "연속 쌍 수", "y": "회차 수"}, color_discrete_sequence=["#c49120"]))
            st.subheader("함께 나온 번호 · 상위 10쌍")
            st.dataframe(pd.DataFrame([{"번호 쌍": f"{a}, {b}", "함께 출현한 횟수": v} for (a, b), v in s["pairs"].most_common(10)]), hide_index=True)
            if s["repeats"]:
                st.caption(f"직전 회차와 겹친 본번호: 평균 {sum(s['repeats']) / len(s['repeats']):.2f}개 (연속 회차만 비교)")
            st.download_button("통계 CSV 저장", csv_bytes(frame), "lotto_statistics.csv", "text/csv")

        elif page == "번호 추천":
            st.title("나의 번호 조합")
            st.caption("추천 방식과 조건을 선택하세요. 점수와 가중치는 당첨 확률이 아닙니다.")
            modes = {"균등 무작위": "random", "조건 지정": "condition", "통계 가중 · 실험": "weighted"}
            with st.form("generate_form"):
                a, b, c = st.columns(3)
                label = a.selectbox("추천 방식", list(modes))
                count = b.number_input("게임 수", 1, 100, 5)
                target = c.number_input("대상 회차", min_value=1, value=latest.round + 1 if latest else 1)
                a, b = st.columns(2)
                include_text = a.text_input("포함할 번호", placeholder="예: 3, 17")
                exclude_text = b.text_input("제외할 번호", placeholder="예: 8, 22")
                a, b, c = st.columns(3)
                odd_label = a.selectbox("홀수 개수", ["제한 없음", *map(str, range(7))])
                sums = b.slider("번호 합계 범위", 21, 255, (21, 255))
                overlap = c.slider("게임 간 겹치는 번호 상한", 0, 6, 6)
                window = st.selectbox("가중치 분석 구간", [10, 50, 100, 300], index=2)
                apply_purchases = st.checkbox("구매 이력 반영 · 이미 구매한 조합 제외", value=True)
                purchase_overlap = st.slider("이전 구매 조합과 겹치는 번호 상한", 0, 5, 5)
                submitted = st.form_submit_button("번호 생성", type="primary", width="stretch")
            st.caption("기본 설정의 균등 무작위는 모든 조합을 같은 확률로 생성합니다. 조건을 추가하면 해당 조건 안에서 추출합니다. 통계 가중은 과거 출현 횟수 + 1을 이용한 실험입니다.")
            if submitted:
                try:
                    history = [d for d in draws if d.round < target][-window:]
                    settings = {"include": parse_numbers(include_text), "exclude": parse_numbers(exclude_text), "odd_count": None if odd_label == "제한 없음" else int(odd_label), "sum_min": sums[0], "sum_max": sums[1], "max_overlap": overlap}
                    purchased = purchases.history_for_generation(db, target) if apply_purchases else []
                    tickets = generate(count, mode=modes[label], draws=history, purchased=purchased, history_overlap=purchase_overlap, **settings)
                    settings.update({"purchase_history_applied": apply_purchases, "purchase_history_count": len(purchased), "purchase_history_overlap": purchase_overlap})
                    settings.update({"window": window, "history_start": history[0].round if history else None, "history_end": history[-1].round if history else None, "data_latest_round": latest.round if latest else 0})
                    st.session_state.generated = {"tickets": tickets, "target": target, "mode": label, "settings": settings, "saved": False}
                except ValueError as exc:
                    st.session_state.pop("generated", None)
                    st.error(str(exc))
            generated = st.session_state.get("generated")
            if generated:
                st.subheader(f"{generated['target']}회 추천 · {generated['mode']}")
                if generated["target"] <= (latest.round if latest else 0):
                    st.warning("과거 회차를 대상으로 만든 연습 조합입니다. 실제 사전 추천 성과로 해석하지 마세요.")
                for i, ticket in enumerate(generated["tickets"], 1):
                    st.markdown(f'<div class="ticket"><div class="ticket-label">GAME {i:02d} · 합계 {sum(ticket)} · 홀수 {sum(n % 2 for n in ticket)}개</div>{balls(ticket)}</div>', unsafe_allow_html=True)
                with st.expander("적용한 기준과 번호별 기록"):
                    st.json(generated["settings"])
                    history = [d for d in draws if d.round < generated["target"]][-generated["settings"]["window"]:]
                    frequency = stats(history)["frequency"]
                    nums = sorted({n for t in generated["tickets"] for n in t})
                    st.dataframe(pd.DataFrame({"번호": nums, "분석 구간 출현 횟수": [frequency[n] for n in nums]}), hide_index=True)
                    st.caption(f"대상 회차 이전의 등록 데이터 {len(history)}개를 사용합니다. 자주 나온 번호의 다음 회차 확률이 높다는 의미는 아닙니다.")
                a, b = st.columns(2)
                if a.button("추천 기록에 저장", disabled=generated["saved"], type="primary"):
                    save_recommendations(db, generated["target"], generated["mode"], generated["tickets"], generated["settings"])
                    generated["saved"] = True
                    st.rerun()
                b.download_button("추천 번호 CSV", csv_bytes(pd.DataFrame([{"대상 회차": generated["target"], **{f"n{i}": n for i, n in enumerate(t, 1)}} for t in generated["tickets"]])), "recommendations.csv", "text/csv")
                if generated["saved"]:
                    st.success("추천 기록에 저장했습니다.")
                with st.expander("실제로 구매한 게임 기록하기"):
                    chosen = st.multiselect("구매 완료한 게임 선택", list(range(1, len(generated["tickets"]) + 1)), key="purchased_game_selection")
                    bought = st.checkbox("위 게임을 실제로 구매했습니다", key="purchase_confirmed")
                    if st.button("구매 이력에 등록", disabled=not bought or not chosen):
                        from uuid import uuid4
                        generated.setdefault("purchase_ids", {})
                        for i in chosen:
                            purchase_id = generated["purchase_ids"].setdefault(str(i), str(uuid4()))
                            purchases.add(db, generated["target"], generated["tickets"][i - 1], purchase_id=purchase_id)
                        st.session_state.purchase_notice = "구매 이력에 등록했습니다."
                        st.rerun()
                st.caption("구매 이력 반영은 중복 조절 기능이며, 과거 구매나 당첨이 다음 회차 확률을 바꾸지는 않습니다.")

        elif page == "구매 이력":
            st.title("구매 이력과 추첨 결과")
            st.caption("본인이 구매한 게임을 기록합니다. 실제 복권 구매나 구매 취소를 실행하지 않습니다.")
            if st.session_state.get("purchase_notice"):
                st.success(st.session_state.pop("purchase_notice"))
            rows = purchases.report(db)
            active = [r for r in rows if r["상태"] == "구매 완료"]
            a, b, c = st.columns(3)
            a.metric("구매 게임 수", sum(r["수량"] for r in active))
            b.metric("기록한 구매 금액", f"{sum(r['구매액'] for r in active):,}원")
            c.metric("결과 미등록", sum(r["수량"] for r in active if r["일치"] is None))
            if rows:
                frame = pd.DataFrame(rows)
                st.dataframe(frame.drop(columns=["ID"]), hide_index=True, width="stretch")
                st.download_button("구매·결과 CSV", csv_bytes(frame), "purchases_results.csv", "text/csv")
                with st.expander("잘못 등록한 구매 기록 정정"):
                    choices = {r["ID"]: f"{r['회차']}회 · {r['번호']} · {r['수량']}게임" for r in active}
                    if choices:
                        selected = st.selectbox("정정할 기록", list(choices), format_func=choices.get)
                        if st.button("잘못된 구매 등록 취소"):
                            purchases.void(db, selected)
                            st.rerun()
            else:
                st.info("등록된 구매 이력이 없습니다. 번호 추천 화면에서 게임을 선택하거나 아래에서 직접 등록하세요.")
            with st.form("purchase_manual"):
                st.subheader("구매 번호 직접 등록")
                a, b = st.columns(2)
                target_round = a.number_input("구매 대상 회차", min_value=1, value=latest.round + 1 if latest else 1)
                copies = b.number_input("동일 조합 구매 수량", 1, 100, 1)
                text = st.text_input("구매한 번호 6개", placeholder="예: 3, 5, 8, 10, 25, 27")
                confirmed = st.checkbox("위 번호를 실제로 구매했습니다")
                submit = st.form_submit_button("구매 완료 기록")
            if submit:
                try:
                    if not confirmed:
                        raise ValueError("실제 구매 여부를 확인해 주세요.")
                    purchases.add(db, target_round, parse_numbers(text), copies)
                    st.session_state.purchase_notice = "구매 완료 기록을 저장했습니다."
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            with st.expander("구매 이력 백업 · 다른 기기로 이동", expanded=True):
                st.download_button("구매 이력 JSON 백업", purchases.backup(db), "lotto_purchase_backup.json", "application/json")
                uploaded = st.file_uploader("구매 이력 JSON 복원", type=["json"], key="purchase_backup")
                if uploaded and st.button("구매 이력 가져오기"):
                    try:
                        count = purchases.restore(db, uploaded.getvalue())
                        st.session_state.purchase_notice = f"{count}개 구매 기록을 가져왔습니다. 동일 ID는 중복 등록하지 않습니다."
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            st.caption("웹 기록은 브라우저 데이터 삭제·시크릿 모드 종료 시 사라질 수 있습니다. 정기적으로 JSON 백업을 보관하세요. 등수는 현재 등록된 추첨 결과로 재계산하며 당첨금·수익률은 추정하지 않습니다.")

        elif page == "추천 기록 · 결과":
            st.title("추천 기록과 결과")
            records = recommendation_rows(db)
            if records:
                frame = pd.DataFrame(records)
                st.dataframe(frame.drop(columns=["설정"]), hide_index=True, width="stretch")
                st.download_button("전체 기록 CSV", csv_bytes(frame), "recommendation_history.csv", "text/csv")
            else:
                st.info("번호 추천에서 조합을 만든 뒤 기록에 저장하세요.")
            st.subheader("내 번호 직접 확인")
            if not draws:
                st.caption("당첨 이력을 등록하면 직접 번호를 대조할 수 있습니다.")
                return
            with st.form("check_form"):
                check_round = st.selectbox("확인할 회차", [d.round for d in reversed(draws)])
                check_text = st.text_input("확인할 번호 6개", placeholder="1, 2, 3, 4, 5, 6")
                check = st.form_submit_button("당첨 확인")
            if check:
                try:
                    draw = next(d for d in draws if d.round == check_round)
                    hits, rank = match(parse_numbers(check_text), draw)
                    st.success(f"본번호 {hits}개 일치 · {str(rank) + '등' if rank else '미당첨'}")
                    st.markdown(balls(draw.numbers) + '<span class="muted"> ＋ </span>' + balls([draw.bonus]), unsafe_allow_html=True)
                except ValueError as exc:
                    st.error(str(exc))

        elif page == "과거 검증":
            st.title("과거 데이터로 비교하기")
            st.write("각 회차 이전 데이터로 다음 회차 조합을 만들고, 같은 수의 무작위 추천과 비교합니다.")
            st.info("탐색용 비교입니다. 가중 방식은 고정된 ‘출현 횟수 + 1’을 사용합니다. 여러 설정을 시도한 뒤 좋은 결과만 고르면 성능이 과장될 수 있습니다.")
            if len(draws) < 11:
                st.warning("연속된 당첨 이력을 최소 11개 등록하세요.")
                return
            with st.form("backtest_form"):
                a, b, c = st.columns(3)
                warmup = a.number_input("최초 학습 회차 수", 10, len(draws) - 1, min(30, len(draws) - 1))
                games = b.number_input("회차당 게임 수", 1, 20, 5)
                window = c.number_input("가중치 계산 구간", 10, 500, 100)
                run = st.form_submit_button("비교 실행", type="primary")
            if run:
                try:
                    with st.spinner("회차 순서대로 비교 중입니다…"):
                        rows = backtest(draws, warmup=warmup, games=games, window=window)
                    st.session_state.backtest_result = {"rows": rows, "settings": f"학습 {warmup}회 · 회차당 {games}게임 · 구간 {window}회 · 고정 시드 42 · 데이터 {draws[0].round}~{draws[-1].round}회"}
                except ValueError as exc:
                    st.session_state.pop("backtest_result", None)
                    st.error(str(exc))
            result = st.session_state.get("backtest_result")
            if result:
                frame = pd.DataFrame(result["rows"])
                st.caption(result["settings"])
                frame["방식"] = frame["방식"].map({"random": "균등 무작위", "weighted": "통계 가중"})
                summary = []
                for label, group in frame.groupby("방식"):
                    summary.append({"방식": label, "게임 수": len(group), "평균 일치 개수": group["일치"].mean(), **{f"{r}등 횟수": int((group["등수"] == r).sum()) for r in range(1, 6)}})
                st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")
                per_round = frame.groupby(["회차", "방식"], as_index=False)["일치"].mean()
                chart(px.line(per_round, x="회차", y="일치", color="방식", labels={"일치": "회차별 평균 일치 개수"}, color_discrete_sequence=["#3c88bd", "#0f766e"]))
                st.caption("그래프의 회차별 변동과 전체 평균을 함께 보세요. 1등의 희소성과 표본 변동 때문에 이 결과만으로 예측력을 입증할 수 없습니다. 이 화면은 신뢰구간이나 수익률을 추정하지 않습니다.")
                st.download_button("상세 비교 CSV", csv_bytes(frame), "backtest.csv", "text/csv")

        elif page == "AJ 연구":
            st.title("AJ 연구 · 100회 구간 검증")
            st.write("가설: 번호 쌍 관계의 변화가 단순 빈도보다 다음 회차에 관한 정보를 더 제공하는가?")
            folder = ROOT / "research/results/AJ-R1"
            if not (folder / "summary.json").exists():
                st.info("첫 실험 결과를 준비하고 있습니다.")
                return
            summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            blocks = pd.read_csv(folder / "blocks_100.csv")
            st.caption("공식 1~1248회 · 최초 200회 학습 · 201~1248회 평가 · 회차당 10게임 · 각 예측에는 직전 200회만 사용")
            st.info("회고적 탐색 실험입니다. 이미 공개된 과거 자료이며 미래 예측력이 입증되었다는 의미는 아닙니다.")
            a, b, c = st.columns(3)
            a.metric("AJ-R1 평균 일치", f"{summary['means']['AJ-R1']:.4f}")
            b.metric("빈도 기준 대비 차이", f"{summary['primary_delta']:+.4f}")
            c.metric("공정 모의자료 대조 p값", f"{summary['one_sided_fair_null_p']:.3f}" if summary['one_sided_fair_null_p'] is not None else "미계산")
            if summary["primary_delta"] > 0 and summary["one_sided_fair_null_p"] is not None and summary["one_sided_fair_null_p"] < 0.05:
                st.write("이번 탐색에서 공정·독립 추첨 가정과의 차이를 관찰했습니다. 모형 변경 없이 미래 회차에서 별도 재현이 필요합니다.")
            else:
                st.write("AJ-R1이 빈도 기준보다 우수하다는 근거를 확인하지 못했습니다. 좋은 구간만 고르거나 이 결과를 보고 같은 모델의 설정을 바꾸지 않습니다.")
            st.caption("주지표는 게임당 본번호 일치 개수의 회차별 평균입니다. 10게임을 독립 표본 10개로 취급하지 않습니다. p값은 예측 성공 확률이 아닙니다.")
            blocks["구간"] = blocks.apply(lambda r:f"{int(r['구간 시작'])}~{int(r['구간끝'])}" + (" (48회)" if r["회차수"] < 100 else ""),axis=1)
            chart(px.line(blocks,x="구간",y="평균일치",color="방식",markers=True,color_discrete_map={"무작위":"#788b96","빈도 기준":"#3c88bd","AJ-R1":"#0f766e"}))
            st.dataframe(blocks,hide_index=True,width="stretch")
            st.download_button("100회 구간 결과 CSV",(folder / "blocks_100.csv").read_bytes(),"AJ-R1_blocks_100.csv","text/csv")
            st.download_button("회차별 상세 CSV",(folder / "per_round.csv").read_bytes(),"AJ-R1_per_round.csv","text/csv")
            with st.expander("고정한 가설·계산식·실행 정보"):
                st.markdown((ROOT / "research/AJ_R1_PROTOCOL.md").read_text(encoding="utf-8"))
                st.json(manifest)

        elif page == "데이터 관리":
            st.title("당첨 데이터 관리")
            st.caption("공식 결과 가져오기 · CSV 등록 · 원본 검증")
            official, upload, manual = st.tabs(["공식 결과 가져오기", "CSV 가져오기", "회차 직접 등록"])
            with official:
                st.write("동행복권 결과 페이지에서 사용하는 조회 경로로 요청합니다. 공개 API 계약에 따른 서비스가 아니므로 사이트 변경·접근 제한으로 실패할 수 있습니다.")
                estimated = max(1, (datetime.now(ZoneInfo("Asia/Seoul")).date() - datetime(2002, 12, 7).date()).days // 7 + 1)
                with st.form("fetch_form"):
                    a, b = st.columns(2)
                    start = a.number_input("시작 회차", 1, 10000, max(1, latest.round - 9) if latest else max(1, estimated - 99))
                    end = b.number_input("끝 회차", 1, 10000, estimated)
                    fetch = st.form_submit_button("결과 가져오기", type="primary")
                st.caption("한 번에 최대 1,500개 회차를 요청합니다. 기본 끝 회차는 날짜로 추정하므로 토요일 추첨 전에는 이전 회차로 바꾸세요. 실패한 데이터는 저장하지 않습니다.")
                if fetch:
                    try:
                        from lotto.collector import fetch_range
                        progress = st.progress(0, text="공식 결과 확인 중…")
                        fetched = fetch_range(start, end, progress=lambda done, total: progress.progress(done / total))
                        added = save_draws(db, fetched)
                        progress.empty()
                        st.session_state.data_notice = f"{len(fetched)}개 결과 확인 · 새 회차 {added}개 저장"
                        st.session_state.pop("backtest_result", None)
                        st.rerun()
                    except (ValueError, RuntimeError) as exc:
                        st.error(str(exc))
            with upload:
                st.write("CSV는 UTF-8 또는 CP949 인코딩을 지원합니다. 날짜 형식은 YYYY-MM-DD입니다.")
                st.code(",".join(CSV_FIELDS), language=None)
                st.download_button("빈 CSV 양식 다운로드", (",".join(CSV_FIELDS) + "\n").encode("utf-8-sig"), "lotto_template.csv", "text/csv")
                file = st.file_uploader("당첨 이력 CSV", type=["csv"])
                if file:
                    try:
                        imported = read_csv(file.getvalue())
                        st.dataframe(pd.read_csv(io.BytesIO(export_draws(imported))), hide_index=True)
                        if st.button("검증한 CSV 저장", type="primary"):
                            added = save_draws(db, imported)
                            st.session_state.data_notice = f"CSV에서 새 회차 {added}개 저장"
                            st.session_state.pop("backtest_result", None)
                            st.rerun()
                    except (ValueError, UnicodeError) as exc:
                        st.error(str(exc))
            with manual:
                with st.form("manual_form"):
                    a, b = st.columns(2)
                    r = a.number_input("등록 회차", 1, 10000, latest.round + 1 if latest else 1)
                    day = b.date_input("추첨일", value=datetime.now(ZoneInfo("Asia/Seoul")).date())
                    numbers = st.text_input("본번호 6개", placeholder="공식 결과의 6개 번호")
                    bonus = st.number_input("보너스번호", 1, 45, 1)
                    register = st.form_submit_button("회차 저장")
                if register:
                    try:
                        draw = Draw(r, day.isoformat(), parse_numbers(numbers), bonus, "사용자 직접 등록")
                        added = save_draws(db, [draw])
                        st.session_state.data_notice = f"{r}회 확인 · 새 회차 {added}개 저장"
                        st.session_state.pop("backtest_result", None)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            if st.session_state.get("data_notice"):
                st.success(st.session_state.pop("data_notice"))
            st.divider()
            if draws:
                st.subheader(f"등록 데이터 · {len(draws)}개 회차")
                known = {d.round for d in draws}
                missing = [n for n in range(draws[0].round, draws[-1].round + 1) if n not in known]
                if missing:
                    st.warning("누락 회차: " + ", ".join(map(str, missing[:40])) + (" …" if len(missing) > 40 else ""))
                st.dataframe(pd.DataFrame([{"회차": d.round, "추첨일": d.date, "본번호": " · ".join(map(str, d.numbers)), "보너스": d.bonus, "출처": d.source} for d in reversed(draws)]), hide_index=True, width="stretch")
                st.download_button("당첨 데이터 전체 백업 CSV", export_draws(draws), "lotto_draws.csv", "text/csv")
                st.caption("수집 시각은 로컬 데이터베이스에 UTC로 기록됩니다. CSV·직접 등록 자료의 원본 정확성은 공식 결과와 대조하세요.")
            else:
                st.info("등록된 데이터가 없습니다. 예시·가상 데이터를 실제 당첨 이력으로 넣지 않습니다.")
        st.divider()
        st.caption("로또 랩 · 개인용 통계 도구 | 모든 조합의 1등 확률 1 / 8,145,060 | 과거 기록은 미래 당첨을 보장하지 않습니다.")


if __name__ == "__main__":
    main()
