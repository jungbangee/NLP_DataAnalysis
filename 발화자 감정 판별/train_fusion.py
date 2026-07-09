import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer
from tqdm import tqdm
import joblib, numpy as np
from sklearn.metrics import accuracy_score, f1_score
from fusion_model import FTTransformer_KoBERT

class FusionDataset(Dataset):
    def __init__(self, df, num_cols, cat_cols, target_cols, tokenizer, max_len=512):
        self.num_x = torch.tensor(df[num_cols].values, dtype=torch.float32)
        self.cat_x = torch.tensor(df[cat_cols].values, dtype=torch.long)
        self.labels = torch.tensor(df[target_cols].values, dtype=torch.long)
        enc = tokenizer(list(df["combined_answer"]), padding="max_length", truncation=True, max_length=max_len, return_tensors="pt")
        self.input_ids, self.attn_mask = enc["input_ids"], enc["attention_mask"]

    def __getitem__(self, idx):
        return self.num_x[idx], self.cat_x[idx], self.input_ids[idx], self.attn_mask[idx], self.labels[idx]
    def __len__(self):
        return len(self.labels)


def train_fusion_model(train_df, test_df, num_cols, cat_cols, target_cols, model_ckpt, save_path):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained("skt/kobert-base-v1")
    train_loader = DataLoader(FusionDataset(train_df, num_cols, cat_cols, target_cols, tokenizer), batch_size=16, shuffle=True)
    test_loader = DataLoader(FusionDataset(test_df, num_cols, cat_cols, target_cols, tokenizer), batch_size=16)

    cat_cardinalities = [len(joblib.load("artifacts/cat_encoders.pkl")[c].classes_) for c in cat_cols]
    model = FTTransformer_KoBERT("skt/kobert-base-v1", len(num_cols), cat_cardinalities).to(device)
    model.load_state_dict(torch.load(model_ckpt, map_location=device), strict=False)

    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=1e-4)
    loss_fn = torch.nn.CrossEntropyLoss()

    for epoch in range(5):
        model.train()
        total_loss = 0
        for num_x, cat_x, ids, mask, labels in tqdm(train_loader, desc=f"Epoch {epoch+1}"):
            num_x, cat_x, ids, mask, labels = num_x.to(device), cat_x.to(device), ids.to(device), mask.to(device), labels.to(device)
            outs = model(num_x, cat_x, ids, mask)
            loss = sum(loss_fn(outs[i], labels[:, i]) for i in range(4)) / 4
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total_loss += loss.item()
        print(f"✅ Epoch {epoch+1} | Loss={total_loss/len(train_loader):.4f}")

    torch.save(model.state_dict(), save_path)
    print(f"💾 결합 모델 저장 완료 → {save_path}")
