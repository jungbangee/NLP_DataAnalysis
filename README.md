-----

# 📂 NLP & Data Analysis

> **Natural Language Processing (NLP)** 및 **Multimodal Data Analysis** 연구/개발 프로젝트 아카이브입니다.
> LLM 파인튜닝, 멀티모달 딥러닝 모델링, 그리고 비즈니스 인사이트 도출을 위한 데이터 시각화 프로젝트를 포함합니다.

<br>

## 📜 Project List

| Project Name | Description | Key Tech Stack |
| :--- | :--- | :--- |
| **[1] QA봇** | **Llama-3.2 기반 RLHF 파이프라인 구축**<br>• `SFT` → `RM` → `PPO` → `Merge` 전 과정 구현<br>• Human Feedback을 반영한 QA 모델 정렬(Alignment)<br>• LoRA 및 4-bit Quantization을 통한 효율적 학습 |   <br> `Transformers` `TRL` `PEFT` |
| **[2] 발화자 감정 판별** | **KoBERT & FT-Transformer 기반 멀티모달 심리 분석**<br>• 대화 텍스트(Text)와 인구통계 정보(Tabular) 결합<br>• **Cross-Attention**을 활용한 Late Fusion 아키텍처<br>• 발화자의 불안/우울 지수 예측 멀티태스크 학습 |   <br> `FT-Transformer` `Pandas` `Scikit-learn` |
| **[3] 예술의 전당 예매 데이터 분석** | **예술의 전당 예매 데이터 기반 매출 증대 전략 분석**<br>• 2015\~2023년 티켓 판매 빅데이터 전처리 및 EDA<br>• 고객 세분화(Member, Age) 및 시기별 매출 패턴 분석<br>• **Tableau** 대시보드를 활용한 마케팅 인사이트 도출 |   <br> `Pandas` `Data Visualization` |

<br>

## 🛠️ Detail Overview

### 1\. QA봇

  * **주요 목표:** Pre-trained LLM(Llama-3.2-1B)이 사용자의 의도에 부합하는 자연스러운 답변을 생성하도록 강화학습(RLHF) 적용.
  * **데이터:** [RLHF 학습 데이터](https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=data&dataSetSn=71748)
  * **핵심 기능:**
      * **SFT (Supervised Fine-Tuning):** 질의응답 데이터셋을 통한 기본 답변 능력 학습.
      * **Reward Model:** 인간의 선호도를 모방하여 답변 품질을 평가하는 보상 모델 학습.
      * **PPO (Proximal Policy Optimization):** 보상 점수를 최대화하는 방향으로 생성 모델 정책 최적화.

### 2\. 발화자 감정 판별

  * **주요 목표:** 단순 텍스트 분석의 한계를 넘어, 발화자의 배경 정보(나이, 성별, 가구 형태 등)를 함께 고려하여 정밀한 심리 상태(불안/우울) 진단.
  * **데이터:** [고령자 근현대 경험 기반 스토리 구술 데이터](https://www.aihub.or.kr/aihubdata/data/view.do?pageIndex=2&currMenu=115&topMenu=100&srchOptnCnd=OPTNCND001&searchKeyword=&srchDetailCnd=DETAILCND001&srchOrder=ORDER001&srchPagePer=20&srchDataRealmCode=REALM002&aihubDataSe=data&dataSetSn=71703)
  * **핵심 기능:**
      * **Multimodal Fusion:** 텍스트 임베딩(KoBERT)과 정형 데이터 임베딩(FT-Transformer)을 Attention 메커니즘으로 융합.
      * **Multi-task Learning:** 4가지 심리 척도(Anxiety 1/2, Depression 1/2)를 동시에 예측하여 일반화 성능 향상.

### 3\. 예술의 전당 예매 데이터 분석

  * **주요 목표:** 예술의 전당 예매 데이터를 분석하여 적자 개선 및 흑자 전환을 위한 효율적인 마케팅/프로모션 전략 수립.
  * **데이터:** [문화 빅데이터 플랫폼의 2015\~2023년 티켓 판매 데이터 및 공연장 좌석 정보](https://www.bigdata-culture.kr/bigdata/user/data_market/detail.do?id=1bc78801-5d36-4295-b49e-fe2a47e062e)
  * **핵심 과정:**
      * **Data Preprocessing:** 결측치 처리, 파생변수 생성(ID, 날짜 병합), 범주형 데이터 변환(나이대, 환불여부 등)을 통한 분석용 데이터셋 구축.
      * **EDA & Strategy:** 유료 회원 등급, 공연 요일/시간, 장르별 선호도, 연령대가 매출에 미치는 영향 분석.
      * **Dashboarding:** 경영진 및 마케팅 팀을 위한 Tableau 대시보드 설계 (시간 흐름, 성별/연령별 분포 시각화).
  * **결과:** 맞춤형 공연 기획 및 타겟 마케팅을 통한 매출 극대화 방안 제시.

<br>

-----

ⓒ 2025. NLP & Data Analysis Portfolio. All rights reserved.
