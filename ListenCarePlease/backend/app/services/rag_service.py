# backend/app/services/rag_service.py

from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langsmith.wrappers import wrap_openai
import openai
import os
from dotenv import load_dotenv
import unicodedata
from difflib import SequenceMatcher

load_dotenv()


class RAGService:
    """회의록 RAG 서비스"""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        # ChromaDB 클라이언트 초기화 (새 버전)
        self.persist_directory = "./chroma_db"
        os.makedirs(self.persist_directory, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=self.persist_directory)
        self.max_tokens = 110000

    def find_most_similar_speaker(self, query: str, speaker_list: List[str], threshold: float = 0.6) -> Optional[str]:
        """
        주어진 쿼리와 가장 유사한 화자를 찾습니다.

        Args:
            query: 검색할 화자 이름
            speaker_list: 화자 이름 목록
            threshold: 유사도 임계값

        Returns:
            가장 유사한 화자 이름 또는 None
        """
        query = unicodedata.normalize("NFC", query)
        best_match = None
        highest_ratio = 0

        for speaker in speaker_list:
            normalized_speaker = unicodedata.normalize("NFC", speaker)
            ratio = SequenceMatcher(None, query, normalized_speaker).ratio()
            if ratio > highest_ratio:
                highest_ratio = ratio
                best_match = speaker

        if highest_ratio >= threshold:
            return best_match
        return None

    def analyze_question(self, question: str, available_speakers: List[str]) -> Dict[str, Any]:
        """
        질문을 분석하여 화자 필터를 자동으로 감지합니다.
        graph.py의 chat_interface_node 로직을 참고합니다.

        Args:
            question: 사용자 질문
            available_speakers: 사용 가능한 화자 목록

        Returns:
            {
                "detected_speaker": str or None,
                "needs_speaker_filter": bool
            }
        """
        if not available_speakers:
            return {"detected_speaker": None, "needs_speaker_filter": False}

        # LLM을 사용하여 질문에서 화자 이름 추출
        try:
            client = wrap_openai(openai.OpenAI())
            analysis_prompt = f"""
다음 질문을 분석하여 특정 발언자에 관한 것인지 확인하세요:
질문: {question}

사용 가능한 발언자 목록: {', '.join(available_speakers)}

이 질문이 특정 발언자에 관한 것인가요? 만약 그렇다면 해당 발언자의 이름을 정확히 추출하세요.

분석 결과:
발언자: [이름 또는 '없음']
"""

            analysis_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": analysis_prompt}]
            )
            analysis_result = analysis_response.choices[0].message.content

            # 결과 파싱
            detected_speaker = None
            for line in analysis_result.split("\n"):
                if line.startswith("발언자:"):
                    speaker_name = line.split(":")[1].strip()
                    if speaker_name != "없음":
                        # 유사도 기반 매칭
                        matched_speaker = self.find_most_similar_speaker(speaker_name, available_speakers)
                        if matched_speaker:
                            detected_speaker = matched_speaker
                    break

            return {
                "detected_speaker": detected_speaker,
                "needs_speaker_filter": detected_speaker is not None
            }
        except Exception as e:
            print(f"질문 분석 중 오류 발생: {e}")
            return {"detected_speaker": None, "needs_speaker_filter": False}

    def create_or_get_collection(self, file_id: str):
        """파일 ID로 ChromaDB 컬렉션 생성 또는 가져오기"""
        collection_name = f"meeting_{file_id}"

        # 컬렉션 존재 여부 확인
        try:
            collection = self.chroma_client.get_collection(collection_name)
            return collection
        except:
            # 컬렉션이 없으면 생성
            collection = self.chroma_client.create_collection(
                name=collection_name,
                metadata={"description": f"Meeting transcript for file {file_id}"}
            )
            return collection

    def store_transcript(self, file_id: str, final_transcript: List[Dict[str, Any]]):
        """
        회의록을 ChromaDB에 저장
        기존 컬렉션이 있으면 삭제하고 새로 생성합니다.

        Args:
            file_id: 파일 ID
            final_transcript: 최종 회의록 데이터
                [{
                    "speaker_name": "김민서",
                    "speaker_label": "SPEAKER_00",
                    "start_time": 0.5,
                    "end_time": 3.2,
                    "text": "안녕하세요..."
                }, ...]
        """
        collection_name = f"meeting_{file_id}"

        # 기존 컬렉션이 있으면 삭제
        try:
            self.chroma_client.delete_collection(collection_name)
            print(f"기존 컬렉션 삭제: {collection_name}")
        except Exception:
            # 컬렉션이 없으면 무시
            pass

        # Document 객체 생성
        documents = []
        for idx, segment in enumerate(final_transcript):
            doc = Document(
                page_content=segment["text"],
                metadata={
                    "speaker_name": segment["speaker_name"],
                    "speaker_label": segment["speaker_label"],
                    "start_time": segment["start_time"],
                    "end_time": segment["end_time"],
                    "segment_index": idx,
                    "file_id": file_id
                }
            )
            documents.append(doc)

        # ChromaDB에 저장
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name=collection_name,
            persist_directory=self.persist_directory
        )

        return vectorstore

    def get_vectorstore(self, file_id: str) -> Optional[Chroma]:
        """파일 ID로 벡터스토어 가져오기"""
        collection_name = f"meeting_{file_id}"

        try:
            vectorstore = Chroma(
                collection_name=collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory
            )
            # 컬렉션이 존재하는지 확인 (간단한 검색으로 테스트)
            vectorstore.similarity_search("test", k=1)
            return vectorstore
        except Exception as e:
            print(f"벡터스토어를 가져올 수 없습니다: {e}")
            return None

    def query_transcript(
        self,
        file_id: str,
        question: str,
        speaker_filter: str = None,
        k: int = 5,
        available_speakers: List[str] = None
    ) -> Dict[str, Any]:
        """
        회의록에 대해 질문하고 답변 받기
        graph.py의 query_processing 로직을 참고하여 개선

        Args:
            file_id: 파일 ID
            question: 사용자 질문
            speaker_filter: 특정 화자로 필터링 (선택사항, None이면 자동 감지)
            k: 검색할 문서 개수
            available_speakers: 사용 가능한 화자 목록 (자동 필터 감지용)

        Returns:
            {
                "answer": "답변 텍스트",
                "sources": [관련 발화 세그먼트들],
                "speakers": [언급된 화자들]
            }
        """
        vectorstore = self.get_vectorstore(file_id)
        
        if vectorstore is None:
            return {
                "answer": "RAG 시스템이 아직 초기화되지 않았습니다. 먼저 초기화를 진행해주세요.",
                "sources": [],
                "speakers": []
            }

        # 화자 필터 자동 감지 (speaker_filter가 None이고 available_speakers가 제공된 경우)
        if speaker_filter is None and available_speakers:
            analysis_result = self.analyze_question(question, available_speakers)
            if analysis_result["needs_speaker_filter"]:
                speaker_filter = analysis_result["detected_speaker"]

        # 화자 필터링이 있으면 메타데이터 필터 적용
        search_kwargs = {"k": k}
        if speaker_filter:
            search_kwargs["filter"] = {"speaker_name": speaker_filter}

        # 유사도 검색
        try:
            docs = vectorstore.similarity_search(question, **search_kwargs)
        except Exception as e:
            print(f"유사도 검색 실패: {e}")
            return {
                "answer": f"검색 중 오류가 발생했습니다: {str(e)}",
                "sources": [],
                "speakers": []
            }

        if not docs:
            return {
                "answer": "관련된 회의 내용을 찾을 수 없습니다.",
                "sources": [],
                "speakers": []
            }

        # 중복 제거 및 정렬 (graph.py 로직 참고)
        seen_contents = {}
        unique_docs = []
        for doc in docs:
            if doc.page_content not in seen_contents:
                unique_docs.append(doc)
                seen_contents[doc.page_content] = doc.metadata

        # segment_index로 정렬
        unique_docs.sort(key=lambda x: x.metadata.get('segment_index', 0))

        # 컨텍스트 구성 (토큰 제한 고려)
        context = ""
        sources = []
        speakers = set()
        current_tokens = 0

        for doc in unique_docs:
            speaker = doc.metadata.get("speaker_name", "Unknown")
            start_time = doc.metadata.get("start_time", 0)
            end_time = doc.metadata.get("end_time", 0)
            text = doc.page_content

            content = f"[{speaker}] ({self._format_time(start_time)} - {self._format_time(end_time)}): {text}\n\n"

            tokens_in_content = len(content)
            if current_tokens + tokens_in_content > self.max_tokens:
                break

            context += content
            current_tokens += tokens_in_content

            sources.append({
                "speaker": speaker,
                "start_time": start_time,
                "end_time": end_time,
                "text": text
            })
            speakers.add(speaker)

        # LLM으로 답변 생성 (graph.py의 개선된 프롬프트 사용)
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return {
                    "answer": "OpenAI API 키가 설정되지 않았습니다.",
                    "sources": sources,
                    "speakers": list(speakers)
                }

            client = openai.OpenAI(api_key=api_key)
            
            # LangSmith 추적이 활성화되어 있으면 wrap
            if os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true":
                client = wrap_openai(client)

            answer_prompt = f"""
다음은 회의록에서 추출한 관련 내용입니다:

{context}

위의 회의 내용을 바탕으로 다음 질문에 답변해 주세요:
질문: {question}

답변 시 다음 사항을 준수해 주세요:
1. 회의록의 내용만을 기반으로 정확하게 답변하세요.
2. 추측이나 외부 지식을 사용하지 마세요.
3. 누가 어떤 발언을 했는지 명확히 언급하세요.
4. 관련 발언을 인용할 때는 화자 이름을 포함하세요.
5. 질문에 대한 정보가 제공된 데이터에 없다면, 그 사실을 명확히 언급하세요.
6. 여러 화자의 발언이 나왔다면, 각 화자의 정보를 구분하여 답변하세요.
"""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": answer_prompt}]
            )

            answer = response.choices[0].message.content

            return {
                "answer": answer,
                "sources": sources,
                "speakers": list(speakers)
            }
        except Exception as e:
            print(f"LLM 답변 생성 실패: {e}")
            return {
                "answer": f"답변 생성 중 오류가 발생했습니다: {str(e)}",
                "sources": sources,
                "speakers": list(speakers)
            }

    def _format_time(self, seconds: float) -> str:
        """초를 mm:ss 형식으로 변환"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def delete_collection(self, file_id: str):
        """파일 ID의 컬렉션 삭제"""
        collection_name = f"meeting_{file_id}"
        try:
            self.chroma_client.delete_collection(collection_name)
            return True
        except Exception as e:
            print(f"Collection 삭제 실패: {e}")
            return False
