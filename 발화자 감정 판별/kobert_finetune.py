import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel, AdamW, get_linear_schedule_with_warmup
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm
import pandas as pd

class EmotionDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len=512):
        self.texts = texts
        self.labels = torch.tensor(labels.values, dtype=torch.long)
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __getitem__(self, idx):
        enc = self.tokenizer(
            self.texts[idx], padding="max_length", truncation=True,
            max_length=self.max_len, return_tensors="pt"
        )
        return {
            "input_ids": enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "labels": self.labels[idx]
        }

    def __len__(self):
        return len(self.labels)


class MultiTaskKoBERT_Cls(nn.Module):
    def __init__(self, bert_name, num_classes=5):
        super().__init__()
        self.bert = AutoModel.from_pretrained(bert_name)
        self.dropout = nn.Dropout(0.3)
        self.heads = nn.ModuleList([nn.Linear(768, num_classes) for _ in range(4)])

    def forward(self, input_ids, attention_mask):
        out = self.bert(input_ids, attention_mask=attention_mask)
        cls = self.dropout(out.last_hidden_state[:, 0, :])
        return [head(cls) for head in self.heads]


def train_kobert_finetune(data_path, save_path, model_name="skt/kobert-base-v1", epochs=5):
    df = pd.read_json(data_path)
    target_cols = ["anxiety_score_1", "anxiety_score_2", "depression_score_1", "depression_score_2"]
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    dataset = EmotionDataset(
        df["combined_answer"].tolist(),
        df[target_cols],
        tokenizer
    )
    loader = DataLoader(dataset, batch_size=16, shuffle=True)

    model = MultiTaskKoBERT_Cls(model_name).to("cuda" if torch.cuda.is_available() else "cpu")
    optimizer = AdamW(model.parameters(), lr=3e-5)
    loss_fn = nn.CrossEntropyLoss()

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for batch in tqdm(loader, desc=f"Epoch {epoch+1}"):
            ids, mask, labels = batch["input_ids"].to("cuda"), batch["attention_mask"].to("cuda"), batch["labels"].to("cuda")
            outs = model(ids, mask)
            loss = sum(loss_fn(outs[i], labels[:, i]) for i in range(4)) / 4
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total_loss += loss.item()
        print(f"✅ Epoch {epoch+1} | Loss = {total_loss/len(loader):.4f}")

    torch.save(model.state_dict(), save_path)
    print(f"💾 Fine-tuned KoBERT 저장 완료 → {save_path}")
