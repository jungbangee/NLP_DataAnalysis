"""
Text Similarity Tool
발화 스타일 임베딩 유사도 계산
"""
from typing import List, Dict
from langchain.tools import tool
from openai import OpenAI
from app.core.config import settings
import numpy as np


@tool
async def calculate_text_similarity(
    current_utterances: List[str],
    stored_profiles: List[Dict]
) -> Dict:
    """
    화자의 발화 스타일을 DB의 프로필들과 비교합니다.

    Args:
        current_utterances: 현재 화자의 발화들 ["안녕하세요", "네, 알겠습니다", ...]
        stored_profiles: DB에 저장된 프로필들 [
            {"name": "김민서", "text_embedding": [0.11, -0.44, ...], "sample_texts": [...]},
            ...
        ]

    Returns:
        {
            "matched_profile": "김민서" or None,
            "similarity": 0.87,
            "sample_comparison": {...}
        }
    """
    if not stored_profiles or len(stored_profiles) == 0:
        return {
            "matched_profile": None,
            "similarity": 0.0,
            "sample_comparison": {}
        }

    combined_text = " ".join(current_utterances)
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=combined_text
        )
        current_embedding = response.data[0].embedding
    except Exception as e:
        return {
            "matched_profile": None,
            "similarity": 0.0,
            "sample_comparison": {"error": str(e)}
        }

    threshold = 0.85
    current_emb = np.array(current_embedding)
    
    best_match = None
    best_similarity = 0.0

    for profile in stored_profiles:
        stored_emb = profile.get("text_embedding")
        if not stored_emb:
            continue

        stored_emb = np.array(stored_emb)
        dot_product = np.dot(current_emb, stored_emb)
        norm_current = np.linalg.norm(current_emb)
        norm_stored = np.linalg.norm(stored_emb)

        if norm_current == 0 or norm_stored == 0:
            similarity = 0.0
        else:
            similarity = dot_product / (norm_current * norm_stored)

        if similarity > best_similarity:
            best_similarity = similarity
            best_match = profile.get("name")

    return {
        "matched_profile": best_match if best_similarity >= threshold else None,
        "similarity": float(best_similarity),
        "sample_comparison": {
            "current_utterances_count": len(current_utterances),
            "best_match": best_match,
            "similarity_score": float(best_similarity)
        }
    }













