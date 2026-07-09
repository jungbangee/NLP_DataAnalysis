import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
import joblib

def preprocess_data(path_all, path_finetune, save_dir):
    all_df = pd.read_json(path_all)
    fine_df = pd.read_json(path_finetune)

    remain_df = all_df[~all_df["jsonId"].isin(fine_df["jsonId"])].reset_index(drop=True)

    num_cols = ["education_year", "num_children", "num_housemates"]
    cat_cols = [
        "age", "gender", "spouse", "hometown", "region",
        "has_children", "region_match",
        "age_education_combo", "age_housemates_combo",
        "age_children_combo", "education_housemates_combo", "education_children_combo"
    ]
    target_cols = ["anxiety_score_1", "anxiety_score_2", "depression_score_1", "depression_score_2"]

    # 문자 → 숫자
    age_map = {"60대": 0, "70대": 1, "80대": 2}
    ox_map = {"O": 1, "X": 0, "o": 1, "x": 0}
    remain_df["age"] = remain_df["age"].map(age_map)
    remain_df["region_match"] = remain_df["region_match"].replace(ox_map)
    remain_df["has_children"] = remain_df["has_children"].replace(ox_map)

    # 수치형 스케일링
    scaler = StandardScaler()
    remain_df[num_cols] = scaler.fit_transform(remain_df[num_cols])

    # 범주형 인코딩
    cat_encoders = {}
    for col in cat_cols:
        le = LabelEncoder()
        remain_df[col] = le.fit_transform(remain_df[col].astype(str))
        cat_encoders[col] = le

    # Train/Test Split
    train_df, test_df = train_test_split(remain_df, test_size=0.1, random_state=42)

    # 저장
    joblib.dump(scaler, f"{save_dir}/scaler.pkl")
    joblib.dump(cat_encoders, f"{save_dir}/cat_encoders.pkl")
    train_df.to_json(f"{save_dir}/train_df.json")
    test_df.to_json(f"{save_dir}/test_df.json")

    print(f"✅ 전처리 완료 — train={len(train_df)}, test={len(test_df)}")
    return train_df, test_df, num_cols, cat_cols, target_cols
