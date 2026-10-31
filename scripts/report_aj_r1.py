"""AJ-R1 결과 표, 보고서와 과학적 비교 그림 생성."""
import json
from pathlib import Path
import os

os.environ.setdefault("MPLCONFIGDIR",str(Path(__file__).resolve().parents[1] / "artifacts/matplotlib-cache"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd


def main():
    folder = Path("research/results/AJ-R1")
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    blocks = pd.read_csv(folder / "blocks_100.csv")
    null = pd.read_csv(folder / "fair_null.csv")
    pivot = blocks.pivot(index="구간 시작",columns="방식",values="평균일치")
    sizes = blocks[blocks["방식"]=="AJ-R1"].set_index("구간 시작")
    diff = pivot["AJ-R1"]-pivot["빈도 기준"]
    font = Path("C:/Windows/Fonts/malgun.ttf")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 10
    fig,axes = plt.subplots(2,1,figsize=(11,8),layout="constrained")
    labels = [f"{start}–{int(sizes.loc[start,'구간끝'])}" + ("\n48회" if sizes.loc[start,"회차수"] < 100 else "") for start in pivot.index]
    axes[0].bar(range(len(diff)),diff,color=["#0f766e" if v>0 else "#b56565" for v in diff])
    axes[0].axhline(0,color="#536774",linewidth=1)
    axes[0].axhline(summary["primary_delta"],color="#1e3d52",linewidth=1.5,linestyle="--",label=f"전체 차이 {summary['primary_delta']:+.5f}")
    axes[0].set_xticks(range(len(diff)),labels,rotation=30,ha="right")
    axes[0].set_ylabel("평균 일치 개수 차이\nAJ-R1 - 빈도 기준")
    axes[0].set_title("100회 구간별 비교 · 마지막 구간은 48회",loc="left",fontweight="bold")
    axes[0].legend(frameon=False)
    axes[1].hist(null["primary_delta"],bins=20,color="#b7cbd1",edgecolor="white",label="공정 추첨 이력 199개에 동일한 분석 적용")
    axes[1].axvline(summary["primary_delta"],color="#b24c45",linewidth=2,label=f"실제 이력의 차이 · 단측 p={summary['one_sided_fair_null_p']:.3f}")
    axes[1].set_title("관측한 차이가 우연으로도 나오는가?",loc="left",fontweight="bold")
    axes[1].set_xlabel("AJ-R1 - 빈도 기준 · 게임당 평균 일치 개수 차이")
    axes[1].set_ylabel("가상 이력 수")
    axes[1].legend(frameon=False,fontsize=9)
    for ax in axes:
        ax.spines[["top","right"]].set_visible(False)
        ax.grid(axis="y",alpha=.18)
        ax.set_axisbelow(True)
    fig.suptitle("AJ-R1 첫 탐색 실험: 이번 계산식의 우위는 확인되지 않음",fontsize=15,fontweight="bold")
    fig.savefig(folder / "comparison.png",dpi=180,facecolor="white")
    fig.savefig(folder / "comparison.svg",facecolor="white")
    plt.close(fig)
    lines = ["# AJ-R1 첫 100회 구간 검증 결과", "",
        "결론: 고정한 첫 관계 변화 계산식이 빈도 기준보다 우수하다는 근거를 확인하지 못했습니다.", "",
        "이 결과는 로또에서 가능한 모든 관계 모델이 불가능하다는 증명은 아닙니다. AJ-R1이라는 한 계산식의 첫 회고 실험 결과입니다.", "",
        "## 검증 범위", "",
        "공식 1~1248회 전체 이력. 1~200회는 최초 학습 전용, 201~1248회 총 1,048회를 평가했습니다.",
        "100회 완전 구간 10개와 48회 부분 구간 1개입니다. 각 회차 직전 200회만 이용하고 모든 방식이 같은 후보 512개와 게임 간 중복 상한 3개를 사용했습니다.",
        "각 방식은 회차당 10게임, 합계 10,480게임을 평가했습니다. 한 회차의 10게임은 독립 표본으로 세지 않습니다.", "",
        "## 전체 결과", "", "| 방식 | 게임당 평균 본번호 일치 |", "|---|---:|"]
    for method in ("무작위","빈도 기준","AJ-R1"):
        lines.append(f"| {method} | {summary['means'][method]:.6f} |")
    lines += ["", f"AJ-R1 − 빈도 기준: **{summary['primary_delta']:+.6f}개**.",
        f"공정한 가상 이력 199개에서 동일 파이프라인을 반복한 단측 Monte Carlo p값: **{summary['one_sided_fair_null_p']:.3f}**.",
        f"설명용 공정 모의 차이 분포의 2.5~97.5 백분위 범위: {summary['null_delta_2_5_97_5_percentiles'][0]:+.6f} ~ {summary['null_delta_2_5_97_5_percentiles'][1]:+.6f}. 이 범위는 실제 차이의 신뢰구간이 아닙니다.",
        f"빈도 기준보다 높은 구간: {summary['positive_blocks_vs_frequency']}/{summary['total_blocks']} (48회 부분 구간 포함).", "",
        "## 100회 구간 전체 공개", "", "| 평가 구간 | 회차 수 | 무작위 | 빈도 기준 | AJ-R1 | AJ-R1 − 빈도 |", "|---|---:|---:|---:|---:|---:|"]
    for start,row in pivot.iterrows():
        lines.append(f"| {start}~{int(sizes.loc[start,'구간끝'])} | {int(sizes.loc[start,'회차수'])} | {row['무작위']:.4f} | {row['빈도 기준']:.4f} | {row['AJ-R1']:.4f} | {row['AJ-R1']-row['빈도 기준']:+.4f} |")
    lines += ["", "## 해석과 다음 연구", "",
        "평균 본번호 일치 개수는 1등 확률이나 수익률이 아닙니다. 1,048회 자료로 드문 고등수의 우위를 입증할 수 없습니다.",
        "가상 대조는 공정하고 독립적인 추첨을 가정합니다. p값은 다음 회차의 예측 성공 확률이 아닙니다.",
        "이미 공개된 과거 결과로 진행한 회고적 탐색입니다. 향후 1249회 이후 예측을 발표 전에 기록해야 진정한 전향 검증이 됩니다.",
        "후속 가설은 AJ-R2로 구분하고, 이번 결과를 보고 설정을 바꾼 뒤 AJ-R1의 성공으로 표현하지 않습니다.", "",
        "## 재현 자료", "", "- 가설·계산식: `research/AJ_R1_PROTOCOL.md`", "- 원본 데이터: `research/official_1_1248.csv`",
        "- 회차별 상세: `per_round.csv`", "- 100회 구간: `blocks_100.csv`", "- 가상 대조: `fair_null.csv`",
        "- 설정·데이터·코드 해시: `manifest.json`", "", "공식 출처: https://www.dhlottery.co.kr/lt645/result", ""]
    (folder / "REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    print("Saved REPORT.md, comparison.png, comparison.svg")


if __name__ == "__main__":
    main()
