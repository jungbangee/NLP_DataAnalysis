"""
Voice Similarity Tool
음성 임베딩 벡터 간 코사인 유사도 계산
"""
from typing import List, Dict, Optional
from langchain.tools import tool
import numpy as np


@tool
async def calculate_voice_similarity(
    new_embedding: List[float],
    stored_profiles: List[Dict]
) -> Dict:
    """
    새 화자의 음성 임베딩과 DB의 프로필들을 비교합니다.

    Args:
        new_embedding: 현재 오디오의 화자 임베딩 벡터 [0.12, -0.45, ...]
        stored_profiles: DB에 저장된 프로필들 [
            {"name": "김민서", "voice_embedding": [0.11, -0.44, ...]},
            ...
        ]

    Returns:
        {
            "matched_profile": "김민서" or None,
            "similarity": 0.92,
            "threshold_passed": True/False
        }
    """
    if not stored_profiles or len(stored_profiles) == 0:
        return {
            "matched_profile": None,
            "similarity": 0.0,
            "threshold_passed": False
        }

    threshold = 0.85
    new_emb = np.array(new_embedding)
    
    best_match = None
    best_similarity = 0.0

    for profile in stored_profiles:
        stored_emb = profile.get("voice_embedding")
        if not stored_emb:
            continue

        stored_emb = np.array(stored_emb)
        dot_product = np.dot(new_emb, stored_emb)
        norm_new = np.linalg.norm(new_emb)
        norm_stored = np.linalg.norm(stored_emb)

        if norm_new == 0 or norm_stored == 0:
            similarity = 0.0
        else:
            similarity = dot_product / (norm_new * norm_stored)

        if similarity > best_similarity:
            best_similarity = similarity
            best_match = profile.get("name")

    return {
        "matched_profile": best_match if best_similarity >= threshold else None,
        "similarity": float(best_similarity),
        "threshold_passed": best_similarity >= threshold
    }













