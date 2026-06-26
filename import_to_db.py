#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

MONGO_URI = 'mongodb://127.0.0.1:27017/nlp_lecture'
client = MongoClient(MONGO_URI)
db = client['nlp_lecture']
BASE = Path(r'C:\Users\buffa\NLP_Task_AI_Report\json')

CATE_MAP = {
    'cate15': {'cate1': ['1.1','1.2','1.3'], 'cate5': ['5.1','5.2','5.3']},
    'cate2':  {'cate2': ['2.1','2.2','2.3','2.4','2.5']},
    'cate3':  {'cate3': ['3.1','3.2','3.3','3.4']},
    'cate4':  {'cate4': ['4.1','4.2','4.3']},
}

# ── categoryresults ───────────────────────────────────────────
for folder_key, cate_split in CATE_MAP.items():
    folder = BASE / folder_key
    if not folder.exists():
        print(f'[{folder_key}] 폴더 없음 — 건너뜀')
        continue
    files = list(folder.glob('*.json'))
    print(f'[{folder_key}] {len(files)}개 처리 중...')
    ops = {}
    for fp in files:
        try:
            d = json.loads(fp.read_text(encoding='utf-8'))
        except Exception as e:
            print(f'  ⚠ {fp.name}: {e}')
            continue
        for cate_key, item_ids in cate_split.items():
            items = {k: v for k, v in d.get('items', {}).items() if k in item_ids}
            if not items:
                continue
            if cate_key not in ops:
                ops[cate_key] = []
            ops[cate_key].append(UpdateOne(
                {'date': d['date'], 'course_id': d['course_id'], 'category': cate_key},
                {'$set': {
                    'date':       d['date'],
                    'course_id':  d['course_id'],
                    'category':   cate_key,
                    'instructor': d.get('instructor', ''),
                    'filename':   d.get('file_name', fp.name),
                    'items':      items,
                    'error':      '',
                    'timestamp':  datetime.now(timezone.utc),
                }},
                upsert=True
            ))
    for ck, o in ops.items():
        try:
            r = db.categoryresults.bulk_write(o, ordered=False)
            print(f'  {ck}: upserted={r.upserted_count}, modified={r.modified_count}')
        except BulkWriteError as e:
            print(f'  ⚠ {ck} 오류: {e.details}')

# ── dailysummaries ────────────────────────────────────────────
daily_dir = BASE / '데일리평가'
if daily_dir.exists():
    files = list(daily_dir.glob('*.json'))
    print(f'[데일리평가] {len(files)}개 처리 중...')
    ops = []
    for fp in files:
        try:
            d = json.loads(fp.read_text(encoding='utf-8'))
        except Exception as e:
            print(f'  ⚠ {fp.name}: {e}')
            continue
        ops.append(UpdateOne(
            {'date': d['date'], 'course_id': d['course_id']},
            {'$set': {**d, 'generated_at': datetime.now(timezone.utc)}},
            upsert=True
        ))
    if ops:
        r = db.dailysummaries.bulk_write(ops, ordered=False)
        print(f'  upserted={r.upserted_count}, modified={r.modified_count}')

# ── instructorsummaries ───────────────────────────────────────
instr_dir = None
for name in ['강사평가 결과_날짜별추이', '강사평가_결과_날짜별추이']:
    if (BASE / name).exists():
        instr_dir = BASE / name
        break

if instr_dir:
    files = list(instr_dir.glob('*.json'))
    print(f'[강사평가] {len(files)}개 처리 중...')
    ops = []
    for fp in files:
        try:
            d = json.loads(fp.read_text(encoding='utf-8'))
        except Exception as e:
            print(f'  ⚠ {fp.name}: {e}')
            continue
        ops.append(UpdateOne(
            {'instructor': d['instructor'], 'course_id': d.get('course_id', '')},
            {'$set': {**d, 'generated_at': datetime.now(timezone.utc)}},
            upsert=True
        ))
    if ops:
        r = db.instructorsummaries.bulk_write(ops, ordered=False)
        print(f'  upserted={r.upserted_count}, modified={r.modified_count}')

print('\nImport 완료!')
client.close()