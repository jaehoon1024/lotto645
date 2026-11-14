from datetime import datetime
import json
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from . import purchases
from . import workspace_v2 as workspace
from .core import match
from .storage import recommendation_rows, save_recommendations


def render(db,draws,root,balls,chart):
    journal=json.loads((root / "research/journal.json").read_text(encoding="utf-8"))
    summary_path=root / "research/results/AJ-R1/summary.json"
    summary=json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    five_game_path = root / "research/results/five_game_comparison.json"
    five_game = json.loads(five_game_path.read_text(encoding="utf-8")) if five_game_path.exists() else None
    frozen=[json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "research/forward").glob("*.json"))]
    frozen.sort(key=lambda r:r["target_round"],reverse=True)
    latest=draws[-1] if draws else None
    st.markdown('<div class="hero"><div class="eyebrow">AJ RESEARCH JOURNAL</div><h2>가설부터 결과까지, 연구를 쌓아갑니다.</h2><p>연구 타임라인 · 실험 버전 · 발표 전 고정한 추천 · 나의 기록</p></div>',unsafe_allow_html=True)
    cols=st.columns(4)
    cols[0].metric("연구 활동",f"{len(journal['events'])}건")
    cols[1].metric("완료한 실험", f"{int(summary is not None) + int(five_game is not None)}개")
    cols[2].metric("마지막 등록 결과",f"{latest.round}회" if latest else "—")
    cols[3].metric("나의 구매 기록",f"{sum(p['copies'] for p in purchases.records(db) if p['status']=='purchased')}게임")
    st.write("")
    render_results(db,draws,frozen,balls)
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
        if five_game:
            render_five_game_comparison(five_game)
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
            st.markdown(f"### {item['target_round']}회 · {item['draw_date']} · " + ("결과 확인" if any(d.round==item["target_round"] for d in draws) else "결과 대기"))
            st.caption(f"고정 시각 {created} · {item['model_id']} · 비교 모델 데이터 {item['history_start']}~{item['history_end']}회")
            model_notes = {
                "무작위": "5게임 비교 규칙의 무작위 후보 순서에서 처음 5개 조합을 고정했습니다.",
                "AJ-D1": "한 번씩만 쓰는 30개 번호를 5게임에 나눴습니다.",
                "AJ-R1": "최근 빈도와 번호 쌍 관계 변화를 사용한 연구 추천입니다.",
            }
            if item["model_id"] in model_notes:
                st.info(model_notes[item["model_id"]])
            target=next((d for d in draws if d.round==item["target_round"]),None)
            rows=[]
            for index,ticket in enumerate(item["recommended_tickets"],1):
                hits,rank=match(ticket,target) if target else (None,None)
                result=f"{rank}등" if rank else "미당첨" if target else "결과 대기"
                st.markdown(f'<div class="ticket"><div class="ticket-label">GAME {index:02d} · {result}</div>{balls(ticket)}</div>',unsafe_allow_html=True)
                rows.append({"대상 회차":item["target_round"],"게임":index,"번호":" · ".join(map(str,ticket)),"일치":hits,"결과":result})
            saved=any(r["settings"].get("frozen_id")==item["id"] for r in workspace.recommendations(db))
            if st.button("개인 추천 기록에 보관",disabled=saved,type="primary"):
                save_recommendations(db,item["target_round"],f"{item['model_id']} 연구 추천",item["recommended_tickets"],
                                     {"frozen_id":item["id"],"forecast_created_at":item["created_at"],"history_start":item["history_start"],"history_end":item["history_end"],"data_latest_round":item["history_end"],"model_code_sha256":item["model_code_sha256"]})
                st.rerun()
            if saved:
                st.success("개인 추천 기록에 보관했습니다. 구매하셨다면 구매 이력에서 따로 기록하세요.")
            st.download_button("고정 추천 CSV",pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),f"AJ_round_{item['target_round']}.csv","text/csv")
            st.download_button("예측 원본·비교 기준 JSON",json.dumps(item,ensure_ascii=False,indent=2).encode("utf-8"),f"{item['model_id']}_round{item['target_round']}.json","application/json")
            with st.expander("추첨 전에 고정한 연구 예측과 비교 기준"):
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


def render_results(db,draws,frozen,balls):
    st.subheader("회차 결과 대시보드")
    if not frozen:
        st.info("고정 추천이 등록되면 결과를 표시합니다.")
        return
    options={item["target_round"]:item for item in frozen}
    selected=st.selectbox("결과 확인 회차",list(options),format_func=lambda n:f"{n}회",key="result_round")
    item=options[selected]
    target=next((d for d in draws if d.round==selected),None)
    if target is None:
        st.info(f"{selected}회 공식 결과 확인 대기 · {item['draw_date']} 추첨")
        return
    st.caption(f"{target.round}회 · {target.date} · 공식 당첨번호")
    st.markdown(balls(target.numbers)+'<span class="muted"> ＋ 보너스 </span>'+balls([target.bonus]),unsafe_allow_html=True)
    ticket_results=[match(ticket,target) for ticket in item["recommended_tickets"]]
    a,b,c=st.columns(3)
    a.metric("고정 추천",f"{len(ticket_results)}게임")
    b.metric("당첨 게임",f"{sum(rank is not None for _,rank in ticket_results)}게임")
    c.metric("최대 본번호 일치",f"{max(hits for hits,_ in ticket_results)}개")
    rows=[]
    for index,(ticket,(hits,rank)) in enumerate(zip(item["recommended_tickets"],ticket_results),1):
        rows.append({"게임":index,"추천 번호":" · ".join(map(str,ticket)),"일치 번호":" · ".join(map(str,sorted(set(ticket)&set(target.numbers)))) or "—","본번호 일치":hits,"결과":f"{rank}등" if rank else "미당첨"})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width="stretch")
    st.download_button("회차 결과 CSV",pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),f"AJ_round_{selected}_results.csv","text/csv",key="result_download")
    registered=[p for p in purchases.records(db) if p["target_round"]==selected and p["status"]=="purchased"]
    if registered:
        count=sum(p["copies"] for p in registered)
        won=sum(p["copies"] for p in registered if match(p["numbers"],target)[1] is not None)
        st.success(f"나의 구매 기록: {count}게임 · 구매액 {count*1000:,}원 · 당첨 {won}게임")
    else:
        st.caption("개인 구매 기록이 이 브라우저에 없습니다. 백업·복원에서 전체 기록 JSON을 가져오면 구매 현황도 표시됩니다.")
    games_per_method = len(next(iter(item["research_predictions"].values())))
    with st.expander(f"추첨 전에 고정한 {games_per_method}게임씩의 연구 비교",expanded=True):
        comparison=[]
        for name,tickets in item["research_predictions"].items():
            outcomes=[match(ticket,target) for ticket in tickets]
            comparison.append({"방식":name,"게임 수":len(tickets),"게임당 평균 일치":sum(h for h,_ in outcomes)/len(outcomes),"최대 일치":max(h for h,_ in outcomes),"당첨 게임":sum(r is not None for _,r in outcomes)})
        st.dataframe(pd.DataFrame(comparison),hide_index=True,width="stretch")
        st.caption(f"각 방식의 사전 고정 조합 {games_per_method}게임 기준입니다.")
    st.divider()



def render_five_game_comparison(study):
    st.subheader("같은 5게임 당첨률 비교")
    st.caption(
        f"{study['first_round']}~{study['last_round']}회 · {study['round_count']:,}회 과거 검증. "
        "한 게임이라도 본번호를 3개 이상 맞힌 회차를 한 번으로 셉니다."
    )
    rows = [
        {"방식": name, "당첨 회차": result["winning_rounds"],
         "당첨 회차 비율": f"{result['winning_rate']:.2%}",
         "게임당 평균 본번호 일치": round(result["mean_hits"], 3)}
        for name, result in study["overall"].items()
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("이미 결과가 공개된 회차의 탐색 평가입니다. 각 회차의 추천에는 직전까지의 데이터만 사용했습니다.")
    with st.expander("100회 구간별 당첨률"):
        blocks = [
            {"회차": f"{block['first']}~{block['last']}", "평가 회차 수": block["count"],
             **{name: f"{result['winning_rounds']}/{block['count']} ({result['winning_rate']:.1%})"
                for name, result in block["methods"].items()}}
            for block in study["blocks"]
        ]
        st.dataframe(pd.DataFrame(blocks), hide_index=True, width="stretch")
