from google import genai
from google.genai import types
import json
import re
import sys
from pathlib import Path

# prompts 폴더 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))
from prompts.evaluation_prompt import EVALUATION_PROMPT

class GeminiEvaluator:

    def __init__(self, api_key):
        if not api_key:
            raise ValueError(
                "api_key is required. Set GOOGLE_API_KEY or GEMINI_API_KEY."
            )
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3.1-pro-preview"

    def evaluate(self, script):
        prompt = EVALUATION_PROMPT.format(script=script)
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=8192,
                temperature=0.0,
            ),
        )

        text = response.text.strip()

        # 코드블록 제거 (```json ... ```)
        text = re.sub(r"```(json)?", "", text).replace("```", "").strip()

        # JSON 파싱
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print("❌ RAW RESPONSE:\n", response.text)
            raise
