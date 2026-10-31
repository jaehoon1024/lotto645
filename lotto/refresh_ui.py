from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo
import os

import streamlit as st

from .collector import fetch_range
from .refresh import completed_round
from .storage import connect, load_draws, save_draws


@st.cache_data(ttl=3600, show_spinner=False)
def cached_results(start, end):
    try:
        return fetch_range(start, end), None
    except (RuntimeError, ValueError) as exc:
        return [], str(exc)


@st.fragment(run_every="1h")
def auto_results(path):
    if os.environ.get("LOTTO_DB_PATH"):
        return
    with closing(connect(path)) as db:
        known = load_draws(db)
        end = completed_round()
        start = known[-1].round + 1 if known else max(1, end - 99)
        if start <= end:
            fetched, error = cached_results(start, end)
            if error:
                st.caption("결과 자동 갱신 보류 · 기존 데이터 유지. 1시간 후 재시도하거나 데이터 관리에서 직접 확인하세요.")
            else:
                try:
                    added = save_draws(db, fetched)
                    if added:
                        st.session_state.pop("backtest_result", None)
                        st.rerun(scope="app")
                except ValueError as exc:
                    st.warning(str(exc))
        st.caption("결과 자동 확인: 토요일 21시 이후 · 접속 중 1시간 간격. 마지막 확인 " + datetime.now(ZoneInfo("Asia/Seoul")).strftime("%m/%d %H:%M"))
