"""
회의 효율성 분석 서비스 (ver1.ipynb 통합)
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.audio_file import AudioFile
from app.models.transcript import FinalTranscript
from app.models.tagging import SpeakerMapping
from app.models.diarization import DiarizationResult
from app.models.stt import STTResult
from app.models.efficiency import MeetingEfficiencyAnalysis
from collections import defaultdict
import numpy as np
import logging

# 효율성 분석용 라이브러리
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler
import hdbscan
import torch
from transformers import GPT2LMHeadModel, GPT2TokenizerFast
from konlpy.tag import Mecab
import openai
import os

logger = logging.getLogger(__name__)

# 전역 모델 (한 번만 로드)
_embedding_model = None
_gpt2_model = None
_gpt2_tokenizer = None
_mecab = None

def get_embedding_model():
    """임베딩 모델 싱글톤"""
    global _embedding_model
    if _embedding_model is None:
        try:
            logger.info("Loading sentence-transformers model...")
            print("[DEBUG] Loading embedding model...")
            _embedding_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
            logger.info("Model loaded successfully")
            print("[DEBUG] Embedding model loaded")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            print(f"[DEBUG] Failed to load embedding model: {e}")
            _embedding_model = None
    return _embedding_model


def get_gpt2_model():
    """GPT2 모델 싱글톤 (Perplexity 계산용)"""
    global _gpt2_model, _gpt2_tokenizer
    if _gpt2_model is None:
        try:
            logger.info("Loading GPT2 model for PPL calculation...")
            _gpt2_tokenizer = GPT2TokenizerFast.from_pretrained("skt/kogpt2-base-v2")
            _gpt2_model = GPT2LMHeadModel.from_pretrained("skt/kogpt2-base-v2")
            _gpt2_model.eval()

            # GPU 사용 가능하면 GPU로 이동
            if torch.cuda.is_available():
                _gpt2_model = _gpt2_model.cuda()
                logger.info("GPT2 model loaded on GPU")
            else:
                logger.info("GPT2 model loaded on CPU")
        except Exception as e:
            logger.error(f"Failed to load GPT2 model: {e}")
            _gpt2_model = None
            _gpt2_tokenizer = None
    return _gpt2_model, _gpt2_tokenizer


def get_mecab():
    """Mecab 형태소 분석기 싱글톤 (TTR 계산용)"""
    global _mecab
    if _mecab is None:
        try:
            logger.info("Loading Mecab morphological analyzer...")
            _mecab = Mecab()
            logger.info("Mecab loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load Mecab: {e}. Falling back to simple word splitting.")
            _mecab = None
    return _mecab


class EfficiencyAnalyzer:
    """
    ver1.ipynb 분석 코드 통합 서비스

    역할:
    - ver1.ipynb의 계산 로직만 추출 (시각화 제거)
    - 계산 결과를 JSON 형식으로 반환
    - DB에 MeetingEfficiencyAnalysis 객체로 저장
    """

    def __init__(self, audio_file_id, db: Session):
        self.audio_file_id = audio_file_id
        self.db = db

        # 필요 데이터 로드
        self.audio_file = self._load_audio_file()
        self.final_transcripts = self._load_transcripts()
        self.speaker_mappings = self._load_speaker_mappings()
        self.diarization_results = self._load_diarization()
        self.stt_results = self._load_stt()

    def _load_audio_file(self) -> AudioFile:
        """오디오 파일 정보 로드 - int 또는 str UUID 모두 지원"""
        # Try by ID first (integer)
        audio_file = None
        try:
            audio_file_id_int = int(self.audio_file_id)
            audio_file = self.db.query(AudioFile).filter(
                AudioFile.id == audio_file_id_int
            ).first()
        except (ValueError, TypeError):
            pass

        # If not found or not an integer, try by file_path containing UUID
        if not audio_file:
            audio_file = self.db.query(AudioFile).filter(
                (AudioFile.file_path.like(f"%{self.audio_file_id}%")) |
                (AudioFile.original_filename.like(f"%{self.audio_file_id}%"))
            ).first()

        if not audio_file:
            raise ValueError(f"AudioFile {self.audio_file_id} not found")
        return audio_file

    def _load_transcripts(self) -> List[FinalTranscript]:
        """최종 트랜스크립트 로드"""
        return self.db.query(FinalTranscript).filter(
            FinalTranscript.audio_file_id == self.audio_file_id
        ).order_by(FinalTranscript.segment_index).all()

    def _load_speaker_mappings(self) -> List[SpeakerMapping]:
        """화자 매핑 정보 로드"""
        return self.db.query(SpeakerMapping).filter(
            SpeakerMapping.audio_file_id == self.audio_file_id
        ).all()

    def _load_diarization(self) -> List[DiarizationResult]:
        """화자 분리 결과 로드"""
        return self.db.query(DiarizationResult).filter(
            DiarizationResult.audio_file_id == self.audio_file_id
        ).order_by(DiarizationResult.start_time).all()

    def _load_stt(self) -> List[STTResult]:
        """STT 결과 로드"""
        return self.db.query(STTResult).filter(
            STTResult.audio_file_id == self.audio_file_id
        ).order_by(STTResult.word_index).all()

    def analyze_all(self) -> MeetingEfficiencyAnalysis:
        """
        전체 분석 실행

        Returns:
            MeetingEfficiencyAnalysis: DB 저장용 객체
        """
        logger.info(f"Starting efficiency analysis for audio_file_id={self.audio_file_id}")
        print(f"🚀 [Efficiency] Starting analysis for file {self.audio_file_id}")
        print(f"[DEBUG] EfficiencyAnalyzer.analyze_all started for {self.audio_file_id}")

        # 화자별 지표 계산
        speaker_metrics = []
        for speaker in self.speaker_mappings:
            logger.info(f"Analyzing speaker: {speaker.speaker_label}")
            print(f"[DEBUG] Analyzing speaker: {speaker.speaker_label}")

            metrics = {
                "speaker_label": speaker.speaker_label,
                "speaker_name": speaker.final_name or speaker.speaker_label,

                # ver1.ipynb 각 섹션의 계산 함수들
                "turn_frequency": self._calc_turn_frequency(speaker),
                "ttr": self._calc_ttr(speaker),
                "information_content": self._calc_information_content(speaker),
                "sentence_probability": self._calc_sentence_probability(speaker),
                "perplexity": self._calc_perplexity(speaker)
            }
            speaker_metrics.append(metrics)

        # 전체 회의 지표 계산
        print("[DEBUG] Calculating overall metrics...")
        entropy_data = self._calc_entropy()
        overall_ttr = self._calc_overall_ttr()
        overall_info = self._calc_overall_information_content()
        overall_sent_prob = self._calc_overall_sentence_probability()
        overall_ppl = self._calc_overall_perplexity()

        # 8. Interaction Network
        interaction_network = self._calc_interaction_network()

        # 9. Qualitative Evaluation (LLM)
        qualitative_eval = self._generate_qualitative_evaluation(
            speaker_metrics=speaker_metrics,
            ttr=overall_ttr,
            info=overall_info,
            sent_prob=overall_sent_prob,
            ppl=overall_ppl
        )

        # DB 저장 객체 생성
        from datetime import datetime, timezone
        analysis = MeetingEfficiencyAnalysis(
            audio_file_id=self.audio_file.id,
            entropy_values=entropy_data["values"],
            entropy_avg=entropy_data["avg"],
            entropy_std=entropy_data["std"],
            speaker_metrics=speaker_metrics,
            overall_ttr=overall_ttr,
            overall_information_content=overall_info,
            overall_sentence_probability=overall_sent_prob,
            overall_perplexity=overall_ppl,
            
            # New metrics
            silence_analysis=self._calc_silence_analysis(),
            interaction_analysis=interaction_network,
            qualitative_analysis=qualitative_eval,

            total_speakers=len(self.speaker_mappings),
            total_turns=self._count_total_turns(),
            total_sentences=len(self.final_transcripts),
            analysis_version="1.0",
            analyzed_at=datetime.now(timezone.utc)
        )

        logger.info(f"Efficiency analysis completed for audio_file_id={self.audio_file_id}")
        print(f"✅ [Efficiency] Analysis completed for file {self.audio_file_id}")
        return analysis

    def _count_total_turns(self) -> int:
        """전체 턴 수 계산"""
        return len(self.diarization_results)

    # ========================================
    # ver1.ipynb 코드 통합
    # ========================================

    def _calc_turn_frequency(self, speaker: SpeakerMapping) -> Dict[str, Any]:
        """
        발화 빈도 계산 (ver1.ipynb Cell 8: calculate_turn_taking)

        화자별 발화 횟수, 총 발화 시간, 평균 발화 길이 계산
        """
        # 화자별 diarization 결과 필터링
        speaker_diar = [d for d in self.diarization_results if d.speaker_label == speaker.speaker_label]

        if not speaker_diar:
            return {
                "turn_count": 0,
                "total_duration": 0.0,
                "avg_turn_length": 0.0,
                "time_series": []
            }

        # 발화 횟수
        turn_count = len(speaker_diar)

        # 총 발화 시간
        total_duration = sum(d.end_time - d.start_time for d in speaker_diar)

        # 평균 발화 길이
        avg_turn_length = total_duration / turn_count if turn_count > 0 else 0.0

        # 시계열 데이터 (누적 발화 횟수)
        time_series = []
        cumulative_turns = 0
        for d in speaker_diar:
            cumulative_turns += 1
            time_series.append({
                "time": float(d.start_time),
                "cumulative_turns": cumulative_turns
            })

        return {
            "turn_count": turn_count,
            "total_duration": float(total_duration),
            "avg_turn_length": float(avg_turn_length),
            "time_series": time_series
        }

    def _calc_ttr(self, speaker: SpeakerMapping) -> Dict[str, Any]:
        """
        TTR 계산 (ver1.ipynb Cell 18: load_ttr_data)

        Type-Token Ratio 계산 (슬라이딩 윈도우 방식)
        형태소 분석이 필요하므로 현재는 단어 기반으로 단순화

        TODO: konlpy + mecab으로 형태소 분석 추가
        """
        # 화자별 발화 텍스트 추출
        speaker_transcripts = [
            t for t in self.final_transcripts
            if t.speaker_name == (speaker.final_name or speaker.speaker_label)
        ]

        if not speaker_transcripts:
            return {
                "ttr_values": [],
                "ttr_avg": 0.0,
                "ttr_std": 0.0
            }

        # 전체 텍스트 결합
        texts = [t.text for t in speaker_transcripts]
        all_text = " ".join(texts)

        # Mecab 형태소 분석
        mecab = get_mecab()

        if mecab is not None:
            try:
                # 형태소 분석 수행 (명사, 동사, 형용사만 추출)
                morphs = mecab.pos(all_text)
                # 내용어만 추출 (NNG, NNP, VV, VA 등)
                content_words = [
                    word for word, pos in morphs
                    if pos.startswith('NN') or pos.startswith('VV') or pos.startswith('VA')
                ]
                words = content_words
                logger.info(f"TTR: Mecab analysis - {len(words)} content words extracted")
            except Exception as e:
                logger.warning(f"Mecab analysis failed: {e}. Using word splitting.")
                words = all_text.split()
        else:
            # Fallback: 공백 기준 분할
            words = all_text.split()
            logger.info(f"TTR: Using simple word splitting - {len(words)} words")

        if len(words) < 10:
            return {
                "ttr_values": [],
                "ttr_avg": 0.0,
                "ttr_std": 0.0
            }

        # 슬라이딩 윈도우 TTR 계산
        window_size = min(50, len(words) // 2)  # 형태소 단위 윈도우
        ttr_values = []

        for i in range(0, len(words) - window_size + 1, 10):  # 10형태소씩 이동
            window_words = words[i:i + window_size]
            unique_words = len(set(window_words))
            total_words = len(window_words)
            ttr = unique_words / total_words if total_words > 0 else 0.0

            ttr_values.append({
                "window_start": i,
                "window_end": i + window_size,
                "ttr": float(ttr),
                "unique_words": unique_words,
                "total_words": total_words
            })

        # 평균 및 표준편차
        ttr_scores = [v["ttr"] for v in ttr_values]
        ttr_avg = float(np.mean(ttr_scores)) if ttr_scores else 0.0
        ttr_std = float(np.std(ttr_scores)) if ttr_scores else 0.0

        logger.info(f"TTR calculation completed: avg={ttr_avg:.3f}, std={ttr_std:.3f}")

        return {
            "ttr_values": ttr_values,
            "ttr_avg": ttr_avg,
            "ttr_std": ttr_std
        }

    def _calc_information_content(self, speaker: SpeakerMapping) -> Dict[str, Any]:
        """
        정보량 계산 (ver1.ipynb Cell 23: load_information_data)

        코사인 유사도 기반 정보량 측정
        - 전체 발화의 평균 임베딩 vs 각 문장 임베딩
        - 낮은 유사도 = 높은 정보량
        """
        # 화자별 발화 텍스트 추출
        speaker_transcripts = [
            t for t in self.final_transcripts
            if t.speaker_name == (speaker.final_name or speaker.speaker_label)
        ]

        if not speaker_transcripts or len(speaker_transcripts) < 2:
            return {
                "cosine_similarity_values": [],
                "avg_similarity": 0.0,
                "information_score": 0.0
            }

        try:
            # 임베딩 모델 로드
            model = get_embedding_model()

            # 문장 임베딩 계산
            sentences = [t.text for t in speaker_transcripts]
            embeddings = model.encode(sentences, show_progress_bar=False)

            # 전체 발화의 평균 임베딩 계산
            mean_embedding = np.mean(embeddings, axis=0).reshape(1, -1)

            # 각 문장과 평균 임베딩 간 코사인 유사도 계산
            similarities = cosine_similarity(embeddings, mean_embedding).flatten()

            # Z-정규화
            scaler = StandardScaler()
            z_normalized = scaler.fit_transform(similarities.reshape(-1, 1)).flatten()

            # 결과 저장
            cosine_similarity_values = []
            for i, t in enumerate(speaker_transcripts[:100]):  # 최대 100개
                cosine_similarity_values.append({
                    "time": float(t.start_time),
                    "sentence": t.text[:100],
                    "similarity": float(similarities[i]),
                    "z_normalized": float(z_normalized[i])
                })

            avg_similarity = float(np.mean(similarities))
            information_score = 1.0 - avg_similarity  # 낮은 유사도 = 높은 정보량

            return {
                "cosine_similarity_values": cosine_similarity_values,
                "avg_similarity": avg_similarity,
                "information_score": float(information_score)
            }
        except Exception as e:
            logger.error(f"Error calculating information content: {e}", exc_info=True)
            print(f"❌ [Efficiency] Error calculating information content: {e}")
            return {
                "cosine_similarity_values": [],
                "avg_similarity": 0.0,
                "information_score": 0.0
            }

    def _calc_sentence_probability(self, speaker: SpeakerMapping) -> Dict[str, Any]:
        """
        문장 확률 계산 (ver1.ipynb: HDBSCAN 군집화)

        문장 임베딩 기반 군집화로 희귀 문장 탐지
        """
        # 화자별 발화 텍스트 추출
        speaker_transcripts = [
            t for t in self.final_transcripts
            if t.speaker_name == (speaker.final_name or speaker.speaker_label)
        ]

        if not speaker_transcripts or len(speaker_transcripts) < 5:
            return {
                "avg_probability": 0.0,
                "outlier_ratio": 0.0,
                "cluster_info": [],
                "rare_sentences": []
            }

        try:
            # 임베딩 모델 로드
            model = get_embedding_model()

            # 문장 임베딩 계산
            sentences = [t.text for t in speaker_transcripts]
            embeddings = model.encode(sentences, show_progress_bar=False)

            # HDBSCAN 군집화
            clusterer = hdbscan.HDBSCAN(min_cluster_size=max(3, len(sentences) // 10))
            cluster_labels = clusterer.fit_predict(embeddings)

            # 군집별 통계 계산
            cluster_counts = defaultdict(int)
            for label in cluster_labels:
                cluster_counts[label] += 1

            total_sentences = len(speaker_transcripts)
            cluster_info = []
            for cluster_id, count in cluster_counts.items():
                if cluster_id != -1:  # -1은 노이즈
                    cluster_info.append({
                        "cluster_id": int(cluster_id),
                        "sentence_count": count,
                        "probability": round(count / total_sentences, 4)
                    })

            # 희귀 문장 탐지 (노이즈 또는 작은 군집)
            rare_sentences = []
            for i, (label, t) in enumerate(zip(cluster_labels, speaker_transcripts)):
                if label == -1 or cluster_counts[label] < 3:  # 노이즈 또는 작은 군집
                    rare_sentences.append({
                        "sentence": t.text[:100],
                        "probability": round(cluster_counts[label] / total_sentences, 4) if label != -1 else 0.0,
                        "cluster_id": int(label)
                    })

            # 평균 확률 및 이상치 비율 계산
            outlier_count = sum(1 for label in cluster_labels if label == -1 or cluster_counts[label] < 3)
            outlier_ratio = outlier_count / total_sentences if total_sentences > 0 else 0.0

            # 평균 확률 (정상 군집의 평균 확률)
            normal_probs = [count / total_sentences for label, count in cluster_counts.items() if label != -1 and count >= 3]
            avg_probability = np.mean(normal_probs) if normal_probs else 0.0

            return {
                "avg_probability": float(avg_probability),
                "outlier_ratio": float(outlier_ratio),
                "cluster_info": sorted(cluster_info, key=lambda x: x["probability"], reverse=True),
                "rare_sentences": rare_sentences[:10]  # 최대 10개
            }
        except Exception as e:
            logger.error(f"Error calculating sentence probability: {e}", exc_info=True)
            print(f"❌ [Efficiency] Error calculating sentence probability: {e}")
            return {
                "avg_probability": 0.0,
                "outlier_ratio": 0.0,
                "cluster_info": [],
                "rare_sentences": []
            }

    def _calc_perplexity(self, speaker: SpeakerMapping) -> Dict[str, Any]:
        """
        PPL 계산 (ver1.ipynb Cell 36: calculate_conditional_ppl)

        GPT-2 기반 조건부 Perplexity 계산
        """
        try:
            model, tokenizer = get_gpt2_model()
            if model is None or tokenizer is None:
                logger.warning("GPT2 model not available, skipping PPL calculation")
                return {
                    "ppl_values": [],
                    "ppl_avg": 0.0,
                    "ppl_std": 0.0
                }

            # 화자 발화 수집
            speaker_transcripts = [
                t for t in self.final_transcripts
                if t.speaker_name == speaker.speaker_name
            ]

            if len(speaker_transcripts) < 3:  # 최소 3개 문장 필요
                return {
                    "ppl_values": [],
                    "ppl_avg": 0.0,
                    "ppl_std": 0.0
                }

            # 발화 순서대로 정렬
            sorted_transcripts = sorted(speaker_transcripts, key=lambda x: x.start_time)

            ppl_values = []
            device = 'cuda' if torch.cuda.is_available() else 'cpu'

            # 각 문장에 대해 이전 문장들을 컨텍스트로 사용하여 PPL 계산
            for i in range(1, len(sorted_transcripts)):
                # 이전 문장들을 컨텍스트로 사용 (최대 5개)
                context_start = max(0, i - 5)
                context_texts = [t.text for t in sorted_transcripts[context_start:i]]
                target_text = sorted_transcripts[i].text

                # 컨텍스트 + 타겟 결합
                full_text = " ".join(context_texts + [target_text])

                try:
                    # 토크나이징
                    encodings = tokenizer(full_text, return_tensors='pt', truncation=True, max_length=512)
                    input_ids = encodings['input_ids'].to(device)

                    # 모델 forward
                    with torch.no_grad():
                        outputs = model(input_ids, labels=input_ids)
                        loss = outputs.loss

                    # Perplexity = exp(loss)
                    ppl = torch.exp(loss).item()

                    # 이상치 제거 (1000 이상은 너무 높음)
                    if ppl < 1000:
                        ppl_values.append(ppl)

                except Exception as e:
                    logger.warning(f"Error calculating PPL for sentence {i}: {e}")
                    continue

            if not ppl_values:
                return {
                    "ppl_values": [],
                    "ppl_avg": 0.0,
                    "ppl_std": 0.0
                }

            ppl_avg = float(np.mean(ppl_values))
            ppl_std = float(np.std(ppl_values))

            return {
                "ppl_values": ppl_values[:50],  # 최대 50개만 저장
                "ppl_avg": ppl_avg,
                "ppl_std": ppl_std
            }

        except Exception as e:
            logger.error(f"Error calculating perplexity: {e}", exc_info=True)
            return {
                "ppl_values": [],
                "ppl_avg": 0.0,
                "ppl_std": 0.0
            }

    def _calc_entropy(self) -> Dict[str, Any]:
        """
        엔트로피 계산 (ver1.ipynb Cell 31: Entropy)

        TTR 기반 전체 담화 엔트로피

        TODO: 실제 엔트로피 계산 구현
        """
        if not self.final_transcripts:
            return {
                "values": [],
                "avg": 0.0,
                "std": 0.0
            }

        # 전체 텍스트 결합
        all_text = " ".join([t.text for t in self.final_transcripts])
        words = all_text.split()

        if len(words) < 50:
            return {
                "values": [],
                "avg": 0.0,
                "std": 0.0
            }

        # 슬라이딩 윈도우 엔트로피 계산
        window_size = 100  # 단어 단위
        entropy_values = []

        for i in range(0, len(words) - window_size + 1, 20):  # 20단어씩 이동
            window_words = words[i:i + window_size]

            # 단어 빈도 계산
            word_freq = defaultdict(int)
            for word in window_words:
                word_freq[word] += 1

            # 엔트로피 계산: H = -Σ p(x) * log2(p(x))
            total_words = len(window_words)
            entropy = 0.0
            for count in word_freq.values():
                p = count / total_words
                if p > 0:
                    entropy -= p * np.log2(p)

            time_offset = i / len(words) * self.audio_file.duration if self.audio_file.duration else i
            entropy_values.append({
                "time": float(time_offset),
                "entropy": float(entropy)
            })

        # 평균 및 표준편차
        entropy_scores = [v["entropy"] for v in entropy_values]
        entropy_avg = float(np.mean(entropy_scores)) if entropy_scores else 0.0
        entropy_std = float(np.std(entropy_scores)) if entropy_scores else 0.0

        return {
            "values": entropy_values[:100],  # 최대 100개만 저장
            "avg": entropy_avg,
            "std": entropy_std
        }

    # ========================================
    # 전체 회의 지표 계산
    # ========================================

    def _calc_overall_ttr(self) -> Dict[str, Any]:
        """전체 회의 TTR (Type-Token Ratio) 계산"""
        try:
            mecab = get_mecab()

            # 모든 화자의 텍스트 수집
            all_texts = [t.text for t in self.final_transcripts if t.text]
            if not all_texts:
                return None

            combined_text = " ".join(all_texts)

            # 형태소 분석
            if mecab:
                morphs = mecab.morphs(combined_text)
            else:
                morphs = combined_text.split()

            if not morphs:
                return None

            # TTR 계산
            types = len(set(morphs))
            tokens = len(morphs)
            ttr = types / tokens if tokens > 0 else 0.0

            # 윈도우 기반 TTR 계산 (시계열)
            window_size = 50
            ttr_values = []
            for i in range(0, len(morphs), window_size):
                window = morphs[i:i + window_size]
                if len(window) >= 10:
                    window_ttr = len(set(window)) / len(window)
                    ttr_values.append(window_ttr)

            return {
                "ttr_avg": float(ttr),
                "ttr_std": float(np.std(ttr_values)) if ttr_values else 0.0,
                "ttr_values": ttr_values[:100],  # 최대 100개
                "total_types": types,
                "total_tokens": tokens
            }
        except Exception as e:
            logger.error(f"Error calculating overall TTR: {e}")
            return None

    def _calc_overall_information_content(self) -> Dict[str, Any]:
        """전체 회의 정보량 (Information Content) 계산"""
        try:
            model = get_embedding_model()
            if model is None:
                return None

            # 모든 문장 임베딩
            sentences = [t.text for t in self.final_transcripts if t.text]
            if len(sentences) < 2:
                return None

            embeddings = model.encode(sentences)

            # 연속된 문장 간 코사인 유사도
            similarities = []
            for i in range(len(embeddings) - 1):
                sim = cosine_similarity([embeddings[i]], [embeddings[i + 1]])[0][0]
                similarities.append(float(sim))

            # 정보 점수 = 1 - 평균 유사도 (낮은 유사도 = 높은 정보량)
            avg_similarity = float(np.mean(similarities)) if similarities else 0.0
            information_score = 1.0 - avg_similarity

            return {
                "avg_similarity": avg_similarity,
                "information_score": information_score,
                "total_sentences": len(sentences)
            }
        except Exception as e:
            logger.error(f"Error calculating overall information content: {e}")
            return None

    def _calc_overall_sentence_probability(self) -> Dict[str, Any]:
        """전체 회의 문장 확률 (Sentence Probability) 계산"""
        try:
            model = get_embedding_model()
            if model is None:
                return None

            # 모든 문장 임베딩
            sentences = [t.text for t in self.final_transcripts if t.text]
            if len(sentences) < 5:  # 최소 5개 문장 필요 (10에서 5로 완화)
                return {
                    "avg_probability": 0.0,
                    "outlier_ratio": 1.0,
                    "total_sentences": len(sentences)
                }

            embeddings = model.encode(sentences)

            # HDBSCAN 클러스터링으로 이상치 탐지
            clusterer = hdbscan.HDBSCAN(min_cluster_size=max(2, len(sentences) // 10))
            labels = clusterer.fit_predict(embeddings)

            # 이상치 (-1 레이블) 비율
            outliers = sum(1 for label in labels if label == -1)
            outlier_ratio = outliers / len(labels) if len(labels) > 0 else 0.0

            # 평균 확률 (클러스터에 속한 비율)
            avg_probability = 1.0 - outlier_ratio

            return {
                "avg_probability": float(avg_probability),
                "outlier_ratio": float(outlier_ratio),
                "total_sentences": len(sentences)
            }
        except Exception as e:
            logger.error(f"Error calculating overall sentence probability: {e}")
            return None

    def _calc_overall_perplexity(self) -> Dict[str, Any]:
        """전체 회의 Perplexity (PPL) 계산"""
        try:
            model, tokenizer = get_gpt2_model()
            if model is None or tokenizer is None:
                logger.warning("GPT2 model not available, skipping overall PPL calculation")
                return None

            # 모든 문장 수집
            sentences = [t.text for t in self.final_transcripts if t.text]
            if len(sentences) < 5:  # 최소 5개 문장 필요
                return None

            # 발화 순서대로 정렬
            sorted_transcripts = sorted(self.final_transcripts, key=lambda x: x.start_time)

            ppl_values = []
            device = 'cuda' if torch.cuda.is_available() else 'cpu'

            # 각 문장에 대해 이전 문장들을 컨텍스트로 사용하여 PPL 계산
            for i in range(1, min(len(sorted_transcripts), 100)):  # 최대 100개 문장만 계산 (메모리 절약)
                # 이전 문장들을 컨텍스트로 사용 (최대 3개)
                context_start = max(0, i - 3)
                context_texts = [t.text for t in sorted_transcripts[context_start:i]]
                target_text = sorted_transcripts[i].text

                # 컨텍스트 + 타겟 결합
                full_text = " ".join(context_texts + [target_text])

                try:
                    # 토크나이징
                    encodings = tokenizer(full_text, return_tensors='pt', truncation=True, max_length=256)
                    input_ids = encodings['input_ids'].to(device)

                    # 모델 forward
                    with torch.no_grad():
                        outputs = model(input_ids, labels=input_ids)
                        loss = outputs.loss

                    # Perplexity = exp(loss)
                    ppl = torch.exp(loss).item()

                    # 이상치 제거 (1000 이상은 너무 높음)
                    if ppl < 1000:
                        ppl_values.append(ppl)

                except Exception as e:
                    logger.warning(f"Error calculating overall PPL for sentence {i}: {e}")
                    continue

            if not ppl_values:
                return None

            ppl_avg = float(np.mean(ppl_values))
            ppl_std = float(np.std(ppl_values))

            return {
                "ppl_avg": ppl_avg,
                "ppl_std": ppl_std,
                "sample_count": len(ppl_values)
            }

        except Exception as e:
            logger.error(f"Error calculating overall perplexity: {e}", exc_info=True)
            return None

    def _calc_silence_analysis(self) -> Dict[str, Any]:
        """
        침묵 시간 분석 (VER3.ipynb Logic)
        """
        try:
            segments = sorted(self.diarization_results, key=lambda x: x.start_time)
            gaps = []
            
            for i in range(len(segments) - 1):
                current_end = segments[i].end_time
                next_start = segments[i + 1].start_time
                gap_duration = next_start - current_end
                
                if gap_duration > 0.5: # 0.5초 이상만 침묵으로 간주
                    gaps.append({
                        "start_time": float(current_end),
                        "duration": float(gap_duration),
                        "prev_speaker": segments[i].speaker_label,
                        "next_speaker": segments[i+1].speaker_label
                    })
            
            if not gaps:
                return {
                    "stats": {"total_silence": 0, "mean_silence": 0, "count": 0},
                    "gaps": []
                }
                
            gap_durations = [g['duration'] for g in gaps]
            stats = {
                "total_silence": float(sum(gap_durations)),
                "mean_silence": float(np.mean(gap_durations)),
                "median_silence": float(np.median(gap_durations)),
                "max_silence": float(max(gap_durations)),
                "min_silence": float(min(gap_durations)),
                "std_silence": float(np.std(gap_durations)),
                "count": len(gaps)
            }
            
            return {
                "stats": stats,
                "gaps": gaps[:100] # Limit size
            }
        except Exception as e:
            logger.error(f"Error calculating silence analysis: {e}")
            return None

    def _calc_interaction_network(self) -> Dict[str, Any]:
        """
        화자 간 상호작용 네트워크 분석 (Interaction Graph)
        Nodes: 화자
        Edges: 발화 전환 (Turn-taking) 빈도
        """
        try:
            if not self.final_transcripts:
                return None

            # 1. Nodes (Speakers)
            # FinalTranscript has speaker_name, not speaker_label
            # Get unique speakers
            speaker_names = list(set(t.speaker_name for t in self.final_transcripts if t.speaker_name))
            nodes = [{"id": name, "label": name} for name in speaker_names]

            # 2. Edges (Transitions)
            transitions = defaultdict(int)
            sorted_transcripts = sorted(self.final_transcripts, key=lambda x: x.start_time)

            for i in range(len(sorted_transcripts) - 1):
                current_speaker = sorted_transcripts[i].speaker_name
                next_speaker = sorted_transcripts[i+1].speaker_name

                if current_speaker != next_speaker:
                    transitions[(current_speaker, next_speaker)] += 1

            links = []
            for (source, target), count in transitions.items():
                links.append({
                    "source": source,
                    "target": target,
                    "value": count
                })

            return {
                "nodes": nodes,
                "links": links
            }

        except Exception as e:
            logger.error(f"Error calculating interaction network: {e}", exc_info=True)
            return None

    def _generate_qualitative_evaluation(self, speaker_metrics, ttr, info, sent_prob, ppl) -> str:
        """
        LLM 기반 정성적 평가 (VER2.ipynb Logic)
        """
        try:
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # Prepare data summary for LLM
            transcript_preview = " ".join([t.text for t in self.final_transcripts[:50]]) + "..." # First 50 segments
            
            metrics_summary = {
                "speakers": [s['speaker_name'] for s in speaker_metrics],
                "turn_counts": {s['speaker_name']: s['turn_frequency']['turn_count'] for s in speaker_metrics},
                "avg_ttr": ttr['ttr_avg'] if ttr else 0,
                "avg_info": info['information_score'] if info else 0,
                "avg_ppl": ppl['ppl_avg'] if ppl else 0
            }
            
            prompt = f"""
            당신은 기업 컨설팅 전문가입니다. 다음 회의 데이터를 바탕으로 회의 효율성을 평가해주세요.
            
            [회의 개요]
            - 화자 수: {len(metrics_summary['speakers'])}명
            - 화자 목록: {", ".join(metrics_summary['speakers'])}
            - 발화 빈도: {metrics_summary['turn_counts']}
            - 어휘 다양성(TTR): {metrics_summary['avg_ttr']:.3f} (높을수록 다양)
            - 정보 밀도: {metrics_summary['avg_info']:.3f} (높을수록 정보량 많음)
            - 대화 난이도(PPL): {metrics_summary['avg_ppl']:.2f} (낮을수록 평이)
            
            [회의 초반 내용 (참고용)]
            {transcript_preview}
            
            [평가 항목]
            1. 목적 명확성: 회의 목적이 뚜렷하고 공유되었는가?
            2. 문제 해결 중심: 논의가 생산적인가?
            3. 시간 효율성: 밀도 있게 진행되었는가?
            4. 참여 균형성: 특정인의 독점 없이 고르게 참여했는가?
            5. 결론 명확성: 실행 가능한 결론이 도출되었는가?
            
            각 항목별로 점수(10점 만점)와 짧은 평, 그리고 개선점을 작성해주세요.
            마지막에 종합 점수와 총평을 요약해주세요.
            """
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 회의 분석 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating qualitative evaluation: {e}")
            return "평가 생성 실패"


