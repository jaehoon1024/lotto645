# AJ 로또 연구

첫 모델 AJ-R1은 공식 당첨번호의 번호 쌍 관계 변화가 개별 빈도 기준보다 다음 회차에 관한 정보를 더 제공하는지 살피는 회고적 실험입니다.

`AJ_R1_PROTOCOL.md`에 가설, 계산식, 비교 기준, 100회 구간, 우연 대조 방법을 결과 계산 전에 고정했습니다.
이미 공개된 과거 자료이므로 진정한 전향 검증이나 외부 사전등록이라고 표현하지 않습니다.

## 데이터

- `official_1_1248.csv`: 공식 동행복권 결과 조회에서 검증한 1~1248회 전체 이력.
- 마지막 추첨: 2026-10-31, 본번호 16·18·27·36·38·42, 보너스 22.
- 출처: https://www.dhlottery.co.kr/lt645/result
- 원본 경로: `/lt645/selectPstLt645InfoNew.do`.
- 회차 누락·중복, 번호 유효성, 본번호·보너스 중복, 첫 추첨일로부터의 7일 간격을 검증합니다.
- 개인 구매 데이터는 포함하지 않습니다.

## 재현

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.collect_research_archive
.\.venv\Scripts\python.exe -X utf8 -m scripts.run_aj_r1 --null-repeats 199
```

결과는 `results/AJ-R1`에 저장됩니다. 후보 난수는 대상 회차로 고정하여 모든 방식에서 공유하며,
각 공정 모의 이력에도 동일한 학습·선택·평가 파이프라인을 다시 적용합니다.
설정값을 바꾸어 재실행한 결과를 첫 실험 결과인 것처럼 덮어쓰지 마세요.
완료된 결과는 덮어쓰지 않습니다. 재현 실행은 `--output research/results/AJ-R1-reproduction`처럼 새 폴더를 지정하세요.
