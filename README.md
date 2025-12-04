-----

# 📂 NLP & Data Analysis

> **Natural Language Processing (NLP)** 및 **Multimodal Data Analysis** 연구/개발 프로젝트 아카이브입니다.  
> LLM 파인튜닝(RLHF)과 멀티모달 딥러닝(Text+Tabular)을 활용한 데이터 분석 모델링을 중점으로 다룹니다.

<br>

## 📜 Project List

| Project Name | Description | Key Tech Stack |
| :--- | :--- | :--- |
| **[1] QA봇** | **Llama-3.2 기반 RLHF 파이프라인 구축**<br>• `SFT` → `RM` → `PPO` → `Merge` 전 과정 구현<br>• Human Feedback을 반영한 QA 모델 정렬(Alignment)<br>• LoRA 및 4-bit Quantization을 통한 효율적 학습 |   <br> `Transformers` `TRL` `PEFT` |
| **[2] 발화자 감정 판별** | **KoBERT & FT-Transformer 기반 멀티모달 심리 분석**<br>• 대화 텍스트(Text)와 인구통계 정보(Tabular) 결합<br>• **Cross-Attention**을 활용한 Late Fusion 아키텍처<br>• 발화자의 불안/우울 지수 예측 멀티태스크 학습 |   <br> `FT-Transformer` `Pandas` `Scikit-learn` |

<br>

## 🛠️ Detail Overview

### 1\. QA봇

  * **주요 목표:** Pre-trained LLM(Llama-3.2-1B)이 사용자의 의도에 부합하는 자연스러운 답변을 생성하도록 강화학습(RLHF) 적용.
  * **핵심 기능:**
      * **SFT (Supervised Fine-Tuning):** 질의응답 데이터셋을 통한 기본 답변 능력 학습.
      * **Reward Model:** 인간의 선호도를 모방하여 답변 품질을 평가하는 보상 모델 학습.
      * **PPO (Proximal Policy Optimization):** 보상 점수를 최대화하는 방향으로 생성 모델 정책 최적화.

### 2\. 발화자 감정 판별

  * **주요 목표:** 단순 텍스트 분석의 한계를 넘어, 발화자의 배경 정보(나이, 성별, 가구 형태 등)를 함께 고려하여 정밀한 심리 상태(불안/우울) 진단.
  * **핵심 기능:**
      * **Multimodal Fusion:** 텍스트 임베딩(KoBERT)과 정형 데이터 임베딩(FT-Transformer)을 Attention 메커니즘으로 융합.
      * **Multi-task Learning:** 4가지 심리 척도(Anxiety 1/2, Depression 1/2)를 동시에 예측하여 일반화 성능 향상.

<br>

-----

ⓒ 2025. NLP & Data Analysis Portfolio. All rights reserved.
