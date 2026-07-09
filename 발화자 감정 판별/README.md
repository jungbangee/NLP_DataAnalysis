-----

# 🗣️ Speaker Sentiment Analysis Project

> **Multimodal Approach for Mental Health Assessment using KoBERT & FT-Transformer**

## 📖 Project Overview

이 프로젝트는 발화자의 \*\*대화 텍스트(Text)\*\*와 \*\*인구통계학적 정보(Tabular Data)\*\*를 결합하여 발화자의 심리 상태(불안 및 우울 수준)를 예측하는 **멀티모달 딥러닝 모델**입니다.

단순히 텍스트만 분석하는 것이 아니라, 연령, 성별, 교육 수준 등 배경 정보를 함께 고려하기 위해 **KoBERT**와 **FT-Transformer**를 결합하였으며, **Cross-Attention** 메커니즘을 통해 두 데이터 양식(Modality)을 효과적으로 융합했습니다.

### 🎯 Objective

  * **Input:** 발화자 대화 텍스트 (`combined_answer`) + 인구통계학적 수치/범주형 데이터 (나이, 교육년수, 가족 구성 등)
  * **Output:** 4가지 심리 지표에 대한 멀티태스크 분류 (Multi-task Classification)
      * `anxiety_score_1`, `anxiety_score_2` (불안 지표)
      * `depression_score_1`, `depression_score_2` (우울 지표)

-----

## 🏗️ Model Architecture

텍스트 데이터의 의미적 맥락과 정형 데이터의 패턴을 동시에 학습하기 위해 **Late Fusion** 방식을 고도화한 아키텍처를 사용했습니다.

```
graph TD
    subgraph Input
    T[Conversation Text]
    D[Demographics Table]
    end

    subgraph Text Branch
    T -->|Tokenize| KB[KoBERT (Fine-tuned)]
    KB -->|Last Hidden State| H_Text[Text Embeddings]
    end

    subgraph Tabular Branch
    D -->|Preprocessing| FT[FT-Transformer Encoder]
    FT -->|Feature Tokens| H_Tab[Tabular Embeddings]
    end

    subgraph Fusion & Prediction
    H_Tab & H_Text --> CA[Cross-Attention Fusion]
    CA -->|Fused Features| MLP[Shared Layer & Dropout]
    MLP --> H1[Head 1: Anxiety 1]
    MLP --> H2[Head 2: Anxiety 2]
    MLP --> H3[Head 3: Depression 1]
    MLP --> H4[Head 4: Depression 2]
    end
```

### Key Components

1.  **Text Encoder (KoBERT):** 한국어 대화의 문맥을 파악하기 위해 `skt/kobert-base-v1`을 사용. 1차적으로 텍스트 데이터만으로 Fine-tuning을 수행한 후, Fusion 모델에서 Feature Extractor로 활용합니다.
2.  **Tabular Encoder (FT-Transformer):** 수치형 및 범주형 데이터를 처리하기 위해 Transformer 구조를 정형 데이터에 적용한 FT-Transformer를 구현하여 사용했습니다.
3.  **Cross-Attention Fusion:** 텍스트와 정형 데이터 간의 상호작용을 학습하기 위해 단순 결합(Concatenation) 대신 Cross-Attention 메커니즘을 적용하여 정보 손실을 최소화했습니다.

-----

## 🚀 Training Pipeline

학습 과정은 데이터 전처리부터 모델 병합 학습까지 단계별로 구성되어 있습니다.

### 1\. Data Preprocessing (`data_preprocess.py`)

  * **Text:** 결측치 제거 및 Tokenizer 적용 준비.
  * **Numerical:** `StandardScaler`를 사용한 정규화 (교육년수, 자녀 수 등).
  * **Categorical:** `LabelEncoder`를 사용한 수치 변환 (연령대, 지역 등).

### [cite_start]2. KoBERT Fine-tuning (`kobert_finetune.py`) [cite: 1]

  * Fusion 학습 전, 텍스트 특징을 더 잘 추출하기 위해 KoBERT 모델을 먼저 4가지 Target에 대해 Fine-tuning 합니다.
  * 이 단계에서 저장된 가중치는 이후 Fusion 모델의 초기 가중치로 사용됩니다.

### 3\. Fusion Model Training (`train_fusion.py`)

  * Fine-tuned KoBERT(가중치 Freeze)와 FT-Transformer를 결합하여 학습합니다.
  * Multi-task Loss(`CrossEntropyLoss`의 합)를 최소화하는 방향으로 학습이 진행됩니다.

-----

## 📂 Project Structure

```bash
Speaker-sentiment-analysis/
├── data_preprocess.py      # 데이터 전처리 (Scaling, Encoding, Split)
├── kobert_finetune.py      # 1단계: 텍스트 전용 KoBERT 파인튜닝
├── fusion_model.py         # 2단계: 모델 아키텍처 정의 (KoBERT + FT-Transformer + Fusion)
├── train_fusion.py         # 3단계: 결합 모델 학습 및 평가 스크립트
├── KoBERT_FTTransformer.py # (통합) 전체 파이프라인 실행 스크립트
├── requirements.txt        # 의존성 패키지 목록
└── README.md               # 프로젝트 문서
```

-----

## 🛠️ How to Run

### 1\. Environment Setup

필요한 라이브러리를 설치합니다.

```bash
pip install -r requirements.txt
```

### 2\. Data Preparation

데이터 경로를 설정하고 전처리를 수행합니다.

```python
python data_preprocess.py
```

### 3\. Run Training

전체 파이프라인(KoBERT Fine-tuning → Fusion Training)을 실행합니다.

```bash
python KoBERT_FTTransformer.py
```

> **Note:** GPU 환경(CUDA)에서 실행하는 것을 권장합니다.

-----

## 📊 Tech Stack

| Category | Technology |
| :--- | :--- |
| **Language Model** | `KoBERT` (skt/kobert-base-v1) |
| **Tabular Model** | `FT-Transformer` (Feature Tokenizer + Transformer Encoder) |
| **Fusion Strategy** | Cross-Attention Mechanism |
| **Framework** | PyTorch, Hugging Face Transformers |
| **Data Processing** | Pandas, Scikit-learn (StandardScaler, LabelEncoder) |

-----

### 💡 Future Improvements

  * 데이터 불균형 해소를 위한 **Focal Loss** 또는 **Class Weighting** 적용
  * 하이퍼파라미터 최적화 (Learning Rate, Batch Size 등)
  * 설명 가능한 AI (XAI) 도입을 통한 예측 근거 시각화 (Attention Map 분석)
