#%% 
#%% =====================================
# FT-Transformer + KoBERT 결합용 데이터 전처리
#=========================================
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset

path_all = "/home/master2/Desktop/keyhyun/conversation/processed_features_cleaned.json"
path_finetune = "/home/master2/Desktop/keyhyun/conversation/finetune_sqrt_balanced_processed.json"

all_df = pd.read_json(path_all)
fine_df = pd.read_json(path_finetune)
print(f"전체 데이터: {len(all_df)}개,  Fine-tuning 사용 데이터: {len(fine_df)}개")

# --------------------------------------
# 2️⃣ Fine-tuning에 사용된 jsonId 제외
# --------------------------------------
remain_df = all_df[~all_df["jsonId"].isin(fine_df["jsonId"])].reset_index(drop=True)
print(f"✅ FT+MLP 학습용 데이터: {len(remain_df)}개")

# --------------------------------------
# 3️⃣ 수치형/범주형 Feature 구분
# --------------------------------------
num_cols = ["education_year", "num_children", "num_housemates"]
cat_cols = [
    "age", "gender", "spouse", "hometown", "region",
    "has_children", "region_match",
    "age_education_combo", "age_housemates_combo",
    "age_children_combo", "education_housemates_combo", "education_children_combo"
]
target_cols = ["anxiety_score_1", "anxiety_score_2", "depression_score_1", "depression_score_2"]

# --------------------------------------
# 4️⃣ 전처리 변환 (매핑 + 스케일링 + 인코딩)
# --------------------------------------

# (1) age, region_match, has_children 등 문자 → 숫자 변환
age_map = {"60대": 0, "70대": 1, "80대": 2}
ox_map = {"O": 1, "X": 0, "o": 1, "x": 0}

remain_df["age"] = remain_df["age"].map(age_map)
remain_df["region_match"] = remain_df["region_match"].replace(ox_map)
remain_df["has_children"] = remain_df["has_children"].replace(ox_map)

# (2) 수치형 feature 표준화
scaler = StandardScaler()
# ✅ (수정된 부분 1) — StandardScaler 전체 fit
remain_df[num_cols] = scaler.fit_transform(remain_df[num_cols])
print("✅ 수치형 전체 컬럼 표준화 완료")


# (3) 범주형 feature Label Encoding
cat_encoders = {}
for col in cat_cols:
    if col in remain_df.columns:
        le = LabelEncoder()
        remain_df[col] = le.fit_transform(remain_df[col].astype(str))
        cat_encoders[col] = le

print("✅ 수치형 표준화 + 범주형 인코딩 + OX 매핑 완료")

# --------------------------------------
# 5️⃣ Train/Test Split
# --------------------------------------
train_df, test_df = train_test_split(remain_df, test_size=0.1, random_state=42)
print(f"Train={len(train_df)}, Test={len(test_df)}")
#%%
#=====================================
# KoBERT Multi-task Classification Fine-tuning
#=========================================
#%% ======================================
# 🚀 KoBERT Multi-task Classification Fine-tuning (Cached 버전)
#=========================================
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModel, get_linear_schedule_with_warmup
from torch.optim import AdamW
from tqdm import tqdm

# -----------------------------------------
# 1️⃣ 데이터 로드
# -----------------------------------------
data = fine_df.copy()
target_cols = ["anxiety_score_1", "anxiety_score_2", "depression_score_1", "depression_score_2"]
use_cols = ["combined_answer"] + target_cols
data = data[use_cols].dropna().reset_index(drop=True)

# 0~4 정수 범위로 변환
for col in target_cols:
    data[col] = data[col].clip(0, 4).round().astype(int)

print(f"✅ Fine-tuning 데이터: {len(data)}개")

# -----------------------------------------
# 2️⃣ Tokenizer 사전 변환 (캐싱)
# -----------------------------------------
MODEL_NAME = "skt/kobert-base-v1"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

texts = data["combined_answer"].tolist()
labels = torch.tensor(data[target_cols].values.astype("int64"))

print(f"🧩 Tokenizing {len(texts)} samples...")
text_token = tokenizer(
    texts,
    padding="max_length",
    truncation=True,
    max_length=512,
    return_tensors="pt"
)

# -----------------------------------------
# 3️⃣ Dataset 정의 (캐싱 버전)
# -----------------------------------------
class EmotionDatasetCached(Dataset):
    def __init__(self, tokenized_texts, labels):
        self.input_ids = tokenized_texts["input_ids"]
        self.attn_mask = tokenized_texts["attention_mask"]
        self.labels = labels

    def __len__(self):
        return self.labels.size(0)

    def __getitem__(self, idx):
        return {
            "input_ids": self.input_ids[idx],
            "attention_mask": self.attn_mask[idx],
            "labels": self.labels[idx]
        }

# Dataset / Dataloader
dataset = EmotionDatasetCached(text_token, labels)
train_loader = DataLoader(dataset, batch_size=16, shuffle=True)

print("✅ Cached Dataset & DataLoader 준비 완료")


# -----------------------------------------
# 4️⃣ Multi-task KoBERT 분류 모델 정의
# -----------------------------------------
class MultiTaskKoBERT_Cls(nn.Module):
    def __init__(self, bert, hidden_size=768, num_classes_each=5, dr_rate=0.3):
        super().__init__()
        self.bert = bert
        self.dropout = nn.Dropout(dr_rate)
        self.heads = nn.ModuleList([
            nn.Linear(hidden_size, num_classes_each) for _ in range(4)
        ])

    def forward(self, input_ids, attention_mask):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        cls = outputs.last_hidden_state[:, 0, :]  # [CLS]
        cls = self.dropout(cls)
        outs = [head(cls) for head in self.heads]
        return outs


# -----------------------------------------
# 5️⃣ 학습 세팅
# -----------------------------------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
bert = AutoModel.from_pretrained(MODEL_NAME)
model = MultiTaskKoBERT_Cls(bert).to(device)

optimizer = AdamW(model.parameters(), lr=3e-5)
loss_fn = nn.CrossEntropyLoss()

num_epochs = 5
total_steps = len(train_loader) * num_epochs
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=int(total_steps * 0.1),
    num_training_steps=total_steps
)

# -----------------------------------------
# 6️⃣ 학습 루프
# -----------------------------------------
for epoch in range(num_epochs):
    model.train()
    total_loss = 0

    for batch in tqdm(train_loader, desc=f"Epoch {epoch+1}"):
        input_ids = batch["input_ids"].to(device)
        attn_mask = batch["attention_mask"].to(device)
        labels = batch["labels"].to(device)

        outs = model(input_ids, attn_mask)
        loss = sum(loss_fn(outs[i], labels[:, i]) for i in range(4)) / 4

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        scheduler.step()

        total_loss += loss.item()

    avg_loss = total_loss / len(train_loader)
    print(f"✅ Epoch {epoch+1} | Train Loss: {avg_loss:.4f}")

# -----------------------------------------
# 7️⃣ 저장
# -----------------------------------------
save_path = "/home/master2/Desktop/keyhyun/conversation/fine_tuned_kobert_cls.pt"
torch.save(model.state_dict(), save_path)
print(f"💾 Fine-tuned KoBERT 저장 완료 → {save_path}")




#%% =======================================
# 🔗 Fine-tuned KoBERT + FT-Transformer 학습 준비
#==========================================
import torch
from torch.utils.data import DataLoader
from transformers import AutoTokenizer, AutoModel

class EmotionDataset_TabularCached(Dataset):
    def __init__(self, df, num_cols, cat_cols, target_cols, tokenizer, max_len=512):
        # --- Tabular features ---
        self.num_x = torch.tensor(df[num_cols].values, dtype=torch.float32)
        self.cat_x = torch.tensor(df[cat_cols].values, dtype=torch.long)
        self.labels = torch.tensor(df[target_cols].values, dtype=torch.long)

        # --- Text tokenizer caching ---
        texts = df["combined_answer"].tolist()
        print(f"🧩 Tokenizing {len(texts)} samples...")
        text_token = tokenizer(
            texts,
            padding="max_length",
            truncation=True,
            max_length=max_len,
            return_tensors="pt"
        )

        self.input_ids = text_token["input_ids"]
        self.attn_mask = text_token["attention_mask"]

    def __len__(self):
        return self.labels.size(0)

    def __getitem__(self, idx):
        return (
            self.num_x[idx],
            self.cat_x[idx],
            self.input_ids[idx],
            self.attn_mask[idx],
            self.labels[idx]
        )



print("✅ Dataset 구성 준비 완료")

# -----------------------------
# 1️⃣ 기본 세팅
# -----------------------------
MODEL_NAME = "skt/kobert-base-v1"
ckpt_path = "/home/master2/Desktop/keyhyun/conversation/fine_tuned_kobert_cls.pt"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

# -----------------------------
# 3️⃣ DataLoader 생성
# -----------------------------
train_dataset = EmotionDataset_TabularCached(train_df, num_cols, cat_cols, target_cols, tokenizer)
test_dataset  = EmotionDataset_TabularCached(test_df,  num_cols, cat_cols, target_cols, tokenizer)

train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
test_loader  = DataLoader(test_dataset,  batch_size=16, shuffle=False)

print(f"✅ DataLoader 준비 완료 (train={len(train_loader)}, test={len(test_loader)})")


# -----------------------------
# 4️⃣ Fine-tuned KoBERT 로드 + Freeze
# -----------------------------
bert = AutoModel.from_pretrained(MODEL_NAME)
state_dict = torch.load(ckpt_path, map_location="cpu")

# strict=False → classification head는 무시
bert.load_state_dict(state_dict, strict=False)

for p in bert.parameters():
    p.requires_grad = False

print("✅ Fine-tuned KoBERT 로드 및 Freeze 완료")



import torch
import torch.nn as nn
from transformers import AutoModel
from sklearn.metrics import accuracy_score, f1_score

# ✅ 기존 FT-Transformer 블록 재사용
class FeatureTokenizer(nn.Module):
    def __init__(self, num_numeric_features, cat_cardinalities, d_token):
        super().__init__()
        self.numeric_embeds = nn.ModuleList([
            nn.Linear(1, d_token) for _ in range(num_numeric_features)
        ])
        self.cat_embeds = nn.ModuleList([
            nn.Embedding(c, d_token) for c in cat_cardinalities
        ])
        self.numeric_weights = nn.Parameter(torch.ones(num_numeric_features, 1))
        self.cat_weights = nn.Parameter(torch.ones(len(cat_cardinalities), 1))
        self.feature_positions = nn.Parameter(torch.randn(num_numeric_features + len(cat_cardinalities), d_token))
        self.out_norm = nn.LayerNorm(d_token)

    def forward(self, num_x, cat_x):
        tokens = []
        for i, emb in enumerate(self.numeric_embeds):
            t = emb(num_x[:, i:i+1]) * self.numeric_weights[i]
            tokens.append(t)
        for i, emb in enumerate(self.cat_embeds):
            t = emb(cat_x[:, i]) * self.cat_weights[i]
            tokens.append(t)
        tokens = torch.stack(tokens, dim=1)
        tokens = tokens + self.feature_positions.unsqueeze(0)
        tokens = self.out_norm(tokens)
        return tokens


# ✅ (수정된 부분 6) — CLS 토큰 기반 FT-Transformer Encoder
class FTTransformerEncoder(nn.Module):
    def __init__(self, d_token=192, n_heads=8, n_layers=3):
        super().__init__()
        # CLS 토큰 추가
        self.cls_token = nn.Parameter(torch.randn(1, 1, d_token))
        layer = nn.TransformerEncoderLayer(
            d_model=d_token,
            nhead=n_heads,
            dim_feedforward=d_token * 4,
            dropout=0.1,
            batch_first=True,
            norm_first=True
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)

    def forward(self, tokens):
        B = tokens.size(0)
        # CLS 토큰 확장 후 입력 맨 앞에 추가
        cls_tokens = self.cls_token.expand(B, -1, -1)
        x = torch.cat([cls_tokens, tokens], dim=1)  # (B, 1 + T, d_token)
        # Transformer 통과
        h = self.encoder(x)
        # CLS 토큰의 hidden state 반환
        return h[:, 0, :]



# ✅ KoBERT + FT-Transformer 통합 멀티태스크 분류 모델

import torch
import torch.nn as nn
from transformers import AutoModel

# -----------------------------
# ✨ Cross-Attention Fusion 모듈
# -----------------------------
class CrossAttentionFusion(nn.Module):
    def __init__(self, d_tab, d_text, n_heads=8):
        super().__init__()
        self.cross_attn = nn.MultiheadAttention(
            embed_dim=d_tab,
            kdim=d_text,
            vdim=d_text,
            num_heads=n_heads,
            batch_first=True
        )
        self.norm = nn.LayerNorm(d_tab)

    def forward(self, h_tab, h_text):
        """
        h_tab: (B, d_tab)
        h_text: (B, L, d_text)
        """
        q = h_tab.unsqueeze(1)  # (B, 1, d_tab)
        attn_out, _ = self.cross_attn(q, h_text, h_text)  # (B, 1, d_tab)
        fused = self.norm(h_tab + attn_out.squeeze(1))  # residual connection
        return fused


# -----------------------------
# ✅ FT-Transformer + KoBERT 결합 모델 (concat → attention 융합)
# -----------------------------
class FTTransformer_KoBERT(nn.Module):
    def __init__(self, 
                 bert_model_name="skt/kobert-base-v1",
                 num_numeric_features=0, 
                 cat_cardinalities=[],
                 d_token=192,
                 n_heads=8, n_layers=3,
                 mlp_hidden=256,
                 num_classes=5):
        super().__init__()
        
        # ---- KoBERT branch ----
        self.kobert = AutoModel.from_pretrained(bert_model_name)
        for p in self.kobert.parameters():
            p.requires_grad = False
        bert_dim = 768

        # ---- FT-Transformer branch ----
        self.tokenizer = FeatureTokenizer(num_numeric_features, cat_cardinalities, d_token)
        self.ft_encoder = FTTransformerEncoder(d_token, n_heads, n_layers)

        # ---- ✨ concat → attention fusion 대체 ----
        self.fusion = CrossAttentionFusion(d_tab=d_token, d_text=bert_dim, n_heads=n_heads)

        # ---- Shared + Multi-task Classifiers ----
        self.shared_fc = nn.Sequential(
            nn.LayerNorm(d_token),
            nn.Linear(d_token, mlp_hidden),
            nn.ReLU(),
            nn.Dropout(0.3)
        )
        self.classifiers = nn.ModuleList([
            nn.Linear(mlp_hidden, num_classes) for _ in range(4)
        ])

    def forward(self, num_x, cat_x, input_ids, attn_mask):
        # --- (1) KoBERT 임베딩 ---
        with torch.no_grad():
            bert_out = self.kobert(input_ids=input_ids, attention_mask=attn_mask)
            h_text = bert_out.last_hidden_state  # (B, L, 768)

        # --- (2) FT-Transformer 임베딩 ---
        tokens = self.tokenizer(num_x, cat_x)
        h_tab = self.ft_encoder(tokens)  # (B, d_token)

        # --- (3) ✨ Attention 융합 ---
        fused = self.fusion(h_tab, h_text)  # (B, d_token)

        # --- (4) Shared + Heads ---
        fused = self.shared_fc(fused)
        outs = [clf(fused) for clf in self.classifiers]  # list of 4 × (B, 5)
        return outs

# FT-Transformer + KoBERT 통합 모델 초기화
model = FTTransformer_KoBERT(
    bert_model_name=MODEL_NAME,
    num_numeric_features=len(num_cols),
    cat_cardinalities=[len(cat_encoders[c].classes_) for c in cat_cols],
    d_token=192,
    n_heads=8,
    n_layers=3,
    mlp_hidden=256,
    num_classes=5
).to(device)


# Fine-tuned KoBERT 가중치 복사
model.kobert.load_state_dict(state_dict, strict=False)
for p in model.kobert.parameters():
    p.requires_grad = False

print("✅ FT-Transformer + KoBERT 결합 모델 준비 완료")

# ----------------------------
# 2️⃣ Optimizer / Loss
# ----------------------------
optimizer = AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=1e-4)
loss_fn = nn.CrossEntropyLoss()

# ----------------------------
# 3️⃣ 학습 루프
# ----------------------------
num_epochs = 5

for epoch in range(num_epochs):
    model.train()
    total_loss = 0
    progress = tqdm(train_loader, desc=f"🚀 Epoch {epoch+1}")

    for num_x, cat_x, input_ids, attn_mask, labels in progress:
        num_x, cat_x = num_x.to(device), cat_x.to(device)
        input_ids, attn_mask = input_ids.to(device), attn_mask.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        outs = model(num_x, cat_x, input_ids, attn_mask)  # [list of 4 × (B, 5)]

        # 4개의 감정별 loss 평균
        loss = sum(loss_fn(outs[i], labels[:, i]) for i in range(4)) / 4
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        total_loss += loss.item()
        progress.set_postfix({"loss": f"{total_loss / (len(progress)):.4f}"})

    print(f"✅ Epoch {epoch+1} | Avg Train Loss = {total_loss / len(train_loader):.4f}")

# ----------------------------
# 4️⃣ 평가
# ----------------------------
model.eval()
all_preds, all_labels = [[] for _ in range(4)], [[] for _ in range(4)]

with torch.no_grad():
    for num_x, cat_x, input_ids, attn_mask, labels in tqdm(test_loader, desc="Evaluating"):
        num_x, cat_x = num_x.to(device), cat_x.to(device)
        input_ids, attn_mask = input_ids.to(device), attn_mask.to(device)
        labels = labels.cpu().numpy()

        outs = model(num_x, cat_x, input_ids, attn_mask)
        preds = [torch.argmax(o, dim=1).cpu().numpy() for o in outs]

        for i in range(4):
            all_preds[i].extend(preds[i])
            all_labels[i].extend(labels[:, i])

# ----------------------------
# 5️⃣ 성능 계산
# ----------------------------
print("\n📊 Fine-tuned KoBERT + FT-Transformer + MLP 성능 평가 결과")
for i, name in enumerate(target_cols):
    y_true = np.array(all_labels[i])
    y_pred = np.array(all_preds[i])

    acc = accuracy_score(y_true, y_pred)
    f1  = f1_score(y_true, y_pred, average="weighted")
    print(f"{name:20s} | Acc={acc:.3f} | F1={f1:.3f}")

print("✅ 전체 평가 완료!")
# %%
import joblib

# 모델 저장
model_path = "/home/master2/Desktop/keyhyun/conversation/final_kobert_fttransformer_mlp.pt"
torch.save(model.state_dict(), model_path)

# 인코더/스케일러 저장
joblib.dump(scaler, "/home/master2/Desktop/keyhyun/conversation/scaler.pkl")
joblib.dump(cat_encoders, "/home/master2/Desktop/keyhyun/conversation/cat_encoders.pkl")

print(f"💾 모델/스케일러/인코더 저장 완료:\n- {model_path}\n- scaler.pkl\n- cat_encoders.pkl")


# %%
