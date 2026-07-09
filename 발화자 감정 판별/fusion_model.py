import torch
import torch.nn as nn
from transformers import AutoModel

class FeatureTokenizer(nn.Module):
    def __init__(self, num_numeric, cat_cardinalities, d_token):
        super().__init__()
        self.numeric_embeds = nn.ModuleList([nn.Linear(1, d_token) for _ in range(num_numeric)])
        self.cat_embeds = nn.ModuleList([nn.Embedding(c, d_token) for c in cat_cardinalities])
        self.pos = nn.Parameter(torch.randn(num_numeric + len(cat_cardinalities), d_token))
        self.norm = nn.LayerNorm(d_token)

    def forward(self, num_x, cat_x):
        tokens = [emb(num_x[:, i:i+1]) for i, emb in enumerate(self.numeric_embeds)]
        tokens += [emb(cat_x[:, i]) for i, emb in enumerate(self.cat_embeds)]
        x = torch.stack(tokens, dim=1)
        return self.norm(x + self.pos.unsqueeze(0))


class FTTransformerEncoder(nn.Module):
    def __init__(self, d_token=192, n_heads=8, n_layers=3):
        super().__init__()
        self.cls_token = nn.Parameter(torch.randn(1, 1, d_token))
        layer = nn.TransformerEncoderLayer(
            d_model=d_token, nhead=n_heads, dim_feedforward=d_token*4,
            batch_first=True, dropout=0.1, norm_first=True
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)

    def forward(self, tokens):
        B = tokens.size(0)
        cls = self.cls_token.expand(B, -1, -1)
        x = torch.cat([cls, tokens], dim=1)
        return self.encoder(x)[:, 0, :]


class CrossAttentionFusion(nn.Module):
    def __init__(self, d_tab, d_text, n_heads=8):
        super().__init__()
        self.linear_proj = nn.Linear(d_text, d_tab)
        self.cross_attn = nn.MultiheadAttention(embed_dim=d_tab, num_heads=n_heads, batch_first=True)
        self.norm = nn.LayerNorm(d_tab)

    def forward(self, h_tab, h_text):
        h_text = self.linear_proj(h_text)
        q = h_tab.unsqueeze(1)
        attn_out, _ = self.cross_attn(q, h_text, h_text)
        return self.norm(h_tab + attn_out.squeeze(1))


class FTTransformer_KoBERT(nn.Module):
    def __init__(self, bert_model_name, num_numeric, cat_cardinalities, d_token=192, n_heads=8, n_layers=3):
        super().__init__()
        self.kobert = AutoModel.from_pretrained(bert_model_name)
        for p in self.kobert.parameters():
            p.requires_grad = False

        self.ft_tokenizer = FeatureTokenizer(num_numeric, cat_cardinalities, d_token)
        self.ft_encoder = FTTransformerEncoder(d_token, n_heads, n_layers)
        self.fusion = CrossAttentionFusion(d_tab=d_token, d_text=768)
        self.shared_fc = nn.Sequential(nn.LayerNorm(d_token), nn.Linear(d_token, 256), nn.ReLU(), nn.Dropout(0.3))
        self.heads = nn.ModuleList([nn.Linear(256, 5) for _ in range(4)])

    def forward(self, num_x, cat_x, input_ids, attn_mask):
        with torch.no_grad():
            bert_out = self.kobert(input_ids=input_ids, attention_mask=attn_mask)
            h_text = bert_out.last_hidden_state
        h_tab = self.ft_encoder(self.ft_tokenizer(num_x, cat_x))
        fused = self.fusion(h_tab, h_text)
        h = self.shared_fc(fused)
        return [head(h) for head in self.heads]
