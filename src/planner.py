"""Task Planner - 복합 작업을 단계별로 분해"""

import json
from typing import Optional

from google import genai
import config


TASK_PLANNER_PROMPT = """사용자 요청을 실행 가능한 단계로 분해하세요.

[저장된 메시지 컨텍스트]
{context}

[사용 가능한 작업]
- web_search: 웹에서 정보 검색 (params: query)
- x_search: X(트위터)에서 검색 (params: query)
- translate: 텍스트 번역 (params: text, to - 언어코드 ko/en/ja/zh)
- summarize: 텍스트 요약 (params: text)
- analyze: 텍스트 분석 (params: text, question - 선택)
- save_message: DB에 저장 (params: content)

[출력 형식 - 반드시 JSON만 출력]
{{
    "steps": [
        {{"action": "x_search", "params": {{"query": "@elon_musk"}}, "output_key": "search_result"}},
        {{"action": "translate", "params": {{"text": "$search_result", "to": "ko"}}, "output_key": "translated"}},
        {{"action": "save_message", "params": {{"content": "$translated"}}}}
    ],
    "summary": "X에서 검색 후 번역하여 저장"
}}

[규칙]
1. $변수명으로 이전 단계 결과를 참조
2. 최소한의 단계로 분해 (불필요한 단계 생략)
3. 마지막 단계에는 output_key 생략 가능
4. "이거", "방금 거" 등은 [가장 최근 저장된 메시지]를 참조
5. summary는 전체 작업을 한 줄로 설명

사용자 요청: {message}

JSON:"""


async def plan_tasks(user_message: str, context: str) -> tuple[list[dict], str]:
    """복합 작업을 단계별로 분해

    Args:
        user_message: 사용자 요청 메시지
        context: 저장된 메시지 컨텍스트

    Returns:
        (steps, summary) 튜플
        - steps: 실행할 작업 단계 리스트
        - summary: 작업 요약 설명
    """
    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    prompt = TASK_PLANNER_PROMPT.format(
        context=context if context else "저장된 메시지 없음",
        message=user_message
    )

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )

        response_text = response.text.strip()
        print(f"[Task Planner] 원본 응답:\n{response_text}")

        # JSON 파싱
        # 응답에서 JSON 부분만 추출 (```json ... ``` 형태 처리)
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()

        result = json.loads(response_text)
        steps = result.get("steps", [])
        summary = result.get("summary", "복합 작업 실행")

        print(f"[Task Planner] 분해된 단계: {len(steps)}개")
        for i, step in enumerate(steps):
            print(f"  {i+1}. {step.get('action')}: {step.get('params')}")

        return steps, summary

    except json.JSONDecodeError as e:
        print(f"[Task Planner] JSON 파싱 오류: {e}")
        print(f"[Task Planner] 원본 텍스트: {response_text}")
        # 파싱 실패 시 단순 질문으로 폴백
        return [], "작업 계획 실패"

    except Exception as e:
        print(f"[Task Planner 오류] {type(e).__name__}: {e}")
        return [], "작업 계획 실패"
