from pathlib import Path

from streamlit.testing.v1 import AppTest

from lotto.storage import connect, save_draws
from test_core import history

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def setup_app(tmp_path, monkeypatch, with_data=False):
    path = tmp_path / "ui.sqlite3"
    monkeypatch.setenv("LOTTO_DB_PATH", str(path))
    if with_data:
        db = connect(path)
        save_draws(db, history())
        db.close()
    return AppTest.from_file(APP, default_timeout=30).run()


def test_empty_dashboard_and_generation_and_saving(tmp_path, monkeypatch):
    app = setup_app(tmp_path, monkeypatch)
    assert not app.exception
    app.sidebar.radio[0].set_value("번호 추천").run()
    next(b for b in app.button if b.label == "번호 생성").click().run()
    assert not app.exception
    assert len(app.session_state["generated"]["tickets"]) == 5
    next(b for b in app.button if b.label == "추천 기록에 저장").click().run()
    assert app.session_state["generated"]["saved"]
    app.sidebar.radio[0].set_value("추천 기록 · 결과").run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 5


def test_all_pages_with_data(tmp_path, monkeypatch):
    app = setup_app(tmp_path, monkeypatch, with_data=True)
    assert not app.exception
    for page in ["통계 분석", "번호 추천", "구매 이력", "추천 기록 · 결과", "과거 검증", "데이터 관리"]:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, page
    app.sidebar.radio[0].set_value("과거 검증").run()
    next(b for b in app.button if b.label == "비교 실행").click().run()
    assert not app.exception
    assert len(app.dataframe) >= 1


def test_invalid_recommendation_shows_message(tmp_path, monkeypatch):
    app = setup_app(tmp_path, monkeypatch)
    app.sidebar.radio[0].set_value("번호 추천").run()
    app.text_input[0].set_value("1,1")
    next(b for b in app.button if b.label == "번호 생성").click().run()
    assert not app.exception
    assert app.error and "중복" in app.error[0].value


def test_public_sessions_keep_records_separate(monkeypatch):
    monkeypatch.delenv("LOTTO_DB_PATH", raising=False)
    monkeypatch.delenv("LOTTO_LOCAL_MODE", raising=False)
    first = AppTest.from_file(APP, default_timeout=30).run()
    first.sidebar.radio[0].set_value("번호 추천").run()
    next(b for b in first.button if b.label == "번호 생성").click().run()
    next(b for b in first.button if b.label == "추천 기록에 저장").click().run()
    first.sidebar.radio[0].set_value("추천 기록 · 결과").run()
    assert not first.exception
    assert len(first.dataframe[0].value) == 5
    second = AppTest.from_file(APP, default_timeout=30).run()
    second.sidebar.radio[0].set_value("추천 기록 · 결과").run()
    assert not second.exception
    assert len(second.dataframe) == 0
    assert first.session_state["workspace"].name != second.session_state["workspace"].name


def test_manual_purchase_is_reflected_in_next_generation(tmp_path, monkeypatch):
    app = setup_app(tmp_path, monkeypatch, with_data=True)
    app.sidebar.radio[0].set_value("구매 이력").run()
    app.text_input[0].set_value("3 5 8 10 25 27")
    app.checkbox[0].check()
    next(b for b in app.button if b.label == "구매 완료 기록").click().run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 1
    app.sidebar.radio[0].set_value("번호 추천").run()
    next(b for b in app.button if b.label == "번호 생성").click().run()
    assert not app.exception
    assert app.session_state["generated"]["settings"]["purchase_history_count"] == 1
