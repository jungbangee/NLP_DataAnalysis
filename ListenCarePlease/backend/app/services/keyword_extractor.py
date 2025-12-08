from sqlalchemy.orm import Session
from app.db.base import SessionLocal
from app.models.audio_file import AudioFile
from app.models.stt import STTResult
from app.models.keyword import KeyTerm
from app.agents.keyword_extraction_agent import run_keyword_extraction_agent
import re

async def extract_keywords_from_text(text: str):
    """
    텍스트에서 키워드 추출 (LLM 호출 + 후처리)
    Returns: List[Dict] (processed keywords)
    """
    try:
        raw_keywords = await run_keyword_extraction_agent(text)
    except Exception as e:
        print(f"[KeywordExtractor] Agent execution failed: {e}")
        return []

    if not raw_keywords:
        return []

    # 후처리 (Notebook Logic 이식)
    merged_dict = {}
    for item in raw_keywords:
        raw_clean = item.get('clean_word', '').strip()
        clean_word = re.sub(r'[?(){}\[\]]', '', raw_clean).strip()
        disp = item.get('glossary_display', '')
        glossary_display = re.sub(r'\?', '', disp).strip()

        importance = item.get('importance', 5)
        if isinstance(importance, str):
             try: importance = float(importance)
             except: importance = 5.0

        if not clean_word: continue
        key = clean_word.replace(" ", "")

        if key in merged_dict:
            existing_syns = merged_dict[key]['synonyms']
            new_syns = item.get('synonyms', [])
            if isinstance(new_syns, str): new_syns = [new_syns]
            merged_dict[key]['synonyms'] = list(set(existing_syns + new_syns))
            if importance > merged_dict[key]['importance']:
                merged_dict[key]['importance'] = importance
        else:
            syns = item.get('synonyms', [])
            if isinstance(syns, str): syns = [syns]
            merged_dict[key] = {
                'clean_word': clean_word,
                'glossary_display': glossary_display,
                'mean': item.get('mean', ''),
                'synonyms': syns,
                'importance': importance,
                'first_index': float('inf') # 나중에 계산
            }
            
    return list(merged_dict.values())

def save_keywords_to_db(db: Session, file_id: int, keywords: list, stt_results: list):
    """
    추출된 키워드를 DB에 저장 (위치 매핑 포함)
    """
    # 1. Transcript Correction (대본 수정)
    modified_stt_count = 0
    
    for info in keywords:
        term = info['clean_word']
        synonyms = info['synonyms']
        
        targets = synonyms
        
        for target in targets:
            if not target.strip(): continue
            if target == term: continue 
            
            for stt in stt_results:
                original_text = stt.text if hasattr(stt, 'text') else stt.get('text', '')
                
                if target.lower() in original_text.lower():
                    pattern = re.compile(re.escape(target), re.IGNORECASE)
                    new_text = pattern.sub(term, original_text)
                    
                    if new_text != original_text:
                        if hasattr(stt, 'text'):
                            stt.text = new_text
                        else:
                            stt['text'] = new_text
                        modified_stt_count += 1

    if modified_stt_count > 0:
        print(f"[KeywordExtractor] Corrected {modified_stt_count} transcript segments based on keywords.")

    # 2. Keyword Saving
    final_list = []
    for info in keywords:
        min_idx = float('inf')
        found_any = False
        cleaned_synonyms = [s for s in info['synonyms'] if s.strip()]
        # 메인 term도 검색 대상에 포함
        search_targets = [info['clean_word']] + cleaned_synonyms
        
        for target in search_targets:
            for idx, stt in enumerate(stt_results):
                text = stt.text if hasattr(stt, 'text') else stt.get('text', '')
                
                clean_target = target.replace(" ", "").lower()
                clean_text = text.replace(" ", "").lower()
                
                if clean_target in clean_text:
                    if idx < min_idx:
                        min_idx = idx
                    found_any = True
                    break 
            if found_any and min_idx == 0: break 

        info['first_index'] = min_idx if found_any else float('inf')
        
        if not found_any:
            info['first_index'] = 0 
            print(f"[KeywordExtractor] Keyword '{info['clean_word']}' not found in text, but saving anyway.")
        
        final_list.append(info)

    final_list.sort(key=lambda x: x['first_index'])

    # 기존 키워드 삭제
    db.query(KeyTerm).filter(KeyTerm.audio_file_id == file_id).delete()

    for item in final_list:
        db_term = KeyTerm(
            audio_file_id=file_id,
            term=item['clean_word'],
            meaning=item['mean'],
            glossary_display=item['glossary_display'],
            synonyms=item['synonyms'],
            importance=item['importance'],
            first_appearance_index=item['first_index'] if item['first_index'] != float('inf') else None
        )
        db.add(db_term)
    
    db.commit()
    print(f"[KeywordExtractor] Saved {len(final_list)} keywords for file {file_id}")

async def generate_and_save_keywords(db: Session, file_id: int):
    """
    키워드 추출 및 DB 저장 로직 (기존 함수 유지)
    """
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise ValueError(f"Audio file {file_id} not found")

    stt_results = db.query(STTResult).filter(STTResult.audio_file_id == file_id).order_by(STTResult.start_time).all()
    if not stt_results:
        print(f"[KeywordExtractor] No STT results for file {file_id}. Skipping.")
        return

    full_text = " ".join([stt.text for stt in stt_results])
    
    keywords = await extract_keywords_from_text(full_text)
    if keywords:
        save_keywords_to_db(db, file_id, keywords, stt_results)

async def run_keyword_extraction_background(file_id: int):
    """
    백그라운드 실행용 래퍼 함수
    """
    print(f"[KeywordExtractor] Starting background extraction for file {file_id}")
    db = SessionLocal()
    try:
        await generate_and_save_keywords(db, file_id)
        print(f"[KeywordExtractor] Completed extraction for file {file_id}")
    except Exception as e:
        print(f"[KeywordExtractor] Failed extraction for file {file_id}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
