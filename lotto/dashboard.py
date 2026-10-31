from datetime import datetime
import json
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from . import purchases, workspace
from .core import match
from .storage import recommendation_rows, save_recommendations


def render(db,draws,root,balls,chart):
    journal=json.loads((root / "research/journal.json").read_text(encoding="utf-8"))
    summary_path=root / "research/results/AJ-R1/summary.json"
    summary=json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    frozen=[json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "research/forward").glob("*.json"))]
    frozen.sort(key=lambda r:r["target_round"],reverse=True)
    latest=draws[-1] if draws else None
    st.markdown('<div class="hero"><div class="eyebrow">AJ RESEARCH JOURNAL</div><h2>가설부터 결과까지, 연구를 쌓아갑니다.</h2><p>연구 타임라인 · 실험 버전 · 발표 전 고정한 추천 · 나의 기록</p></div>',unsafe_allow_html=True)
    cols=st.columns(4)
    cols[0].metric("연구 활동",f"{len(journal['events'])}건")
    cols[1].metric("완료한 첫 실험", "1개" if summary else "0개")
    cols[2].metric("마지막 등록 결과",f"{latest.round}회" if latest else "—")
    cols[3].metric("나의 구매 기록",f"{sum(p['copies'] for p in purchases.records(db) if p['status']=='purchased')}게임")
    st.write("")
    timeline,models,rounds,personal,backup_tab=st.tabs(["연구 타임라인","가설·실험","회차별 추천","개인 메모","백업·복원"])
    with timeline:
        st.subheader("활동 히스토리")
        kind=st.selectbox("활동 유형",["전체",*dict.fromkeys(e["kind"] for e in journal["events"])])
        for event in reversed(journal["events"]):
            if kind != "전체" and event["kind"] != kind:
                continue
            with st.container(border=True):
                st.caption(f"{event['date']} · {event['kind']} · {event['model_id']}")
                st.markdown(f"**{event['title']}**")
                st.write(event["detail"])
        with st.expander("우리의 연구 원칙"):
            for principle in journal["principles"]:
                st.write("• " + principle)
    with models:
        st.subheader("모델 버전과 상태")
        for model in journal["models"]:
            with st.container(border=True):
                st.markdown(f"### {model['id']}")
                st.write(model["hypothesis"])
                st.caption(model["status"])
                st.write("다음 단계: " + model["next_step"])
        if summary:
            st.dataframe(pd.DataFrame([{"방식":k,"게임당 평균 일치":v} for k,v in summary["means"].items()]),hide_index=True,width="stretch")
            st.caption(f"AJ-R1 첫 실험 · 회고 평가 {summary['tested_rounds']:,}회 · 빈도 기준 대비 {summary['primary_delta']:+.6f}개 · p={summary['one_sided_fair_null_p']:.3f}")
            st.write("세부 구간과 고정 계산식은 왼쪽 AJ 연구 메뉴에서 확인할 수 있습니다.")
    with rounds:
        st.subheader("발표 전 고정한 회차별 추천")
        if not frozen:
            st.info("아직 고정한 추천이 없습니다.")
        else:
            options={item["id"]:item for item in frozen}
            selected=st.selectbox("고정 추천 회차",list(options),format_func=lambda key:f"{options[key]['target_round']}회 · {options[key]['model_id']}")
            item=options[selected]
            created=datetime.fromisoformat(item["created_at"]).astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
            st.markdown(f"### {item['target_round']}회 · {item['draw_date']} 예정")
            st.caption(f"고정 시각 {created} · {item['history_start']}~{item['history_end']}회만 사용 · AJ-R1 고정 계산식")
            st.info("AJ-R1은 첫 회고 실험에서 우위가 확인되지 않았습니다. AJ-R2는 미적용이며, 아래 번호는 연구용 추천입니다. 구매 완료 기록과 구분합니다.")
            target=next((d for d in draws if d.round==item["target_round"]),None)
            rows=[]
            for index,ticket in enumerate(item["recommended_tickets"],1):
                hits,rank=match(ticket,target) if target else (None,None)
                result=f"{rank}등" if rank else "미당첨" if target else "결과 대기"
                st.markdown(f'<div class="ticket"><div class="ticket-label">GAME {index:02d} · {result}</div>{balls(ticket)}</div>',unsafe_allow_html=True)
                rows.append({"대상 회차":item["target_round"],"게임":index,"번호":" · ".join(map(str,ticket)),"일치":hits,"결과":result})
            saved=any(r["settings"].get("frozen_id")==item["id"] for r in workspace.recommendations(db))
            if st.button("개인 추천 기록에 보관",disabled=saved,type="primary"):
                save_recommendations(db,item["target_round"],"AJ-R1 연구 추천",item["recommended_tickets"],
                                     {"frozen_id":item["id"],"forecast_created_at":item["created_at"],"history_start":item["history_start"],"history_end":item["history_end"],"data_latest_round":item["history_end"],"model_code_sha256":item["model_code_sha256"]})
                st.rerun()
            if saved:
                st.success("개인 추천 기록에 보관했습니다. 구매하셨다면 구매 이력에서 따로 기록하세요.")
            st.download_button("고정 추천 CSV",pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),f"AJ_round_{item['target_round']}.csv","text/csv")
            st.download_button("예측 원본·비교 기준 JSON",json.dumps(item,ensure_ascii=False,indent=2).encode("utf-8"),f"AJ-R1_round{item['target_round']}.json","application/json")
            with st.expander("동일 조건의 10게임 연구 예측과 비교 기준"):
                st.json(item)
    with personal:
        st.subheader("나의 연구 메모")
        st.caption("메모와 개인 추천·구매 이력은 이 브라우저 또는 로컬 DB에 보관합니다. 공개 GitHub에는 올리지 않습니다.")
        if st.session_state.get("workspace_notice"):
            st.success(st.session_state.pop("workspace_notice"))
        with st.form("research_note_form"):
            title=st.text_input("메모 제목",max_chars=200)
            body=st.text_area("관찰·아이디어·질문",max_chars=10_000)
            a,b=st.columns(2)
            model=a.selectbox("관련 연구",["전체","AJ-R1","AJ-R2"])
            target_round=b.number_input("관련 회차 · 없으면 0",0,10000,0)
            if st.form_submit_button("연구 메모 저장"):
                try:
                    workspace.add_note(db,title,body,model,target_round or None)
                    st.session_state.workspace_notice="연구 메모를 저장했습니다."
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        for note in workspace.notes(db):
            timestamp=datetime.fromisoformat(note["created_at"]).astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
            with st.expander(f"{timestamp} · {note['title']}"):
                st.caption(f"{note['model_id']} · 관련 회차 {note['target_round'] or '전체'}")
                st.write(note["body"])
        st.subheader("나의 추천·구매 기록")
        a,b=st.columns(2)
        a.metric("저장한 추천",len(workspace.recommendations(db)))
        b.metric("구매 등록",len(purchases.records(db)))
        recent=recommendation_rows(db)
        if recent:
            st.dataframe(pd.DataFrame(recent[:20]).drop(columns=["설정"]),hide_index=True,width="stretch")
    with backup_tab:
        st.subheader("연구 작업 공간 전체 백업")
        st.write("개인 메모, 저장한 추천, 구매 기록을 한 파일로 보관합니다. 다른 기기에서는 이 JSON을 가져오세요.")
        st.download_button("전체 기록 JSON 백업",workspace.backup(db),"AJ_workspace_backup.json","application/json",type="primary")
        file=st.file_uploader("전체 기록 또는 기존 구매 이력 JSON",type=["json"],key="workspace_import")
        if file and st.button("작업 공간 복원"):
            try:
                added=workspace.restore(db,file.getvalue())
                st.session_state.workspace_notice=f"복원 완료: 구매 {added['purchases']}개 · 추천 {added['recommendations']}개 · 메모 {added['notes']}개 추가"
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        st.caption("같은 기록은 중복 추가하지 않습니다. 예전 구매 이력 백업(version 1)도 지원합니다. 브라우저 데이터 삭제·시크릿 모드 종료에 대비해 백업을 보관하세요. 로그인 기반 기기 간 자동 동기화는 제공하지 않습니다.")
    with st.expander("마지막 등록 당첨번호"):
        if latest:
            st.caption(f"{latest.round}회 · {latest.date} · {latest.source}")
            st.markdown(balls(latest.numbers)+'<span class="muted"> ＋ 보너스 </span>'+balls([latest.bonus]),unsafe_allow_html=True)
        else:
            st.info("당첨 데이터가 없습니다. 데이터 관리에서 가져올 수 있습니다.")
