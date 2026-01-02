"""Task Planner - 복합 작업을 단계별로 분해"""

import json
from typing import Optional

from google import genai
import config


TASK_PLANNER_PROMPT = """사용자 요청을 실행 가능한 단계로 분해하세요.

[저장된 메시지 컨텍스트]
{context}

[사용 가능한 작업]
- web_search: 웹에서 정보 검색
  params: query (검색어), count (결과 개수, 선택)
- x_search: X(트위터)에서 검색
  params: query (검색어), count (결과 개수, 선택)
- translate: 텍스트 번역
  params: text (번역할 텍스트), to (언어코드: ko/en/ja/zh)
- summarize: 텍스트 요약
  params: text (요약할 텍스트), language (출력 언어: same/ko/en/ja/zh, 선택, 기본값 same)
- analyze: 텍스트 분석
  params: text (분석할 텍스트), question (분석 관점/질문, 선택)
- save_message: DB에 저장
  params: content (저장할 내용)

[출력 형식 - 반드시 JSON만 출력]
{{
    "steps": [
        {{"action": "x_search", "params": {{"query": "@elon_musk", "count": 3}}, "output_key": "search_result"}},
        {{"action": "summarize", "params": {{"text": "$search_result", "language": "ko"}}, "output_key": "summarized"}},
        {{"action": "save_message", "params": {{"content": "$summarized"}}}}
    ],
    "summary": "X에서 3개 검색 후 한글로 요약하여 저장"
}}

[규칙]
1. [중요] 이전 단계 결과를 참조할 때 반드시 "$" 기호를 붙여야 함
   - 올바른 예: "$search_result", "$summarized"
   - 잘못된 예: "search_result", "summarized" ($ 없으면 변수 참조 안됨!)
2. 최소한의 단계로 분해 (불필요한 단계 생략)
3. 마지막 단계에는 output_key 생략 가능
4. "이거", "방금 거" 등은 [가장 최근 저장된 메시지]를 참조
5. summary는 전체 작업을 한 줄로 설명
6. 사용자가 지정한 조건은 반드시 params에 반영:
   - "3개", "5개" 등 개수 → count 파라미터
   - "한글로", "영어로" 등 언어 → language 또는 to 파라미터
7. 요약+번역이 필요하면 summarize의 language로 처리 (별도 translate 불필요)
8. 요약 없이 번역만 필요하면 translate 사용

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
    print(f"\n{'='*60}")
    print(f"[Task Planner] 시작")
    print(f"[Task Planner] 사용자 요청: '{user_message}'")
    print(f"[Task Planner] 컨텍스트 길이: {len(context) if context else 0}자")
    print(f"[Task Planner] 모델: gemini-2.0-flash")

    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    prompt = TASK_PLANNER_PROMPT.format(
        context=context if context else "저장된 메시지 없음",
        message=user_message
    )
    print(f"[Task Planner] 프롬프트 길이: {len(prompt)}자")

    try:
        print(f"[Task Planner] LLM 호출 중...")
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )

        response_text = response.text.strip()
        print(f"[Task Planner] LLM 응답 수신")
        print(f"[Task Planner] 원본 응답 ({len(response_text)}자):")
        print(f"{'─'*40}")
        print(response_text)
        print(f"{'─'*40}")

        # JSON 파싱
        # 응답에서 JSON 부분만 추출 (```json ... ``` 형태 처리)
        if "```json" in response_text:
            print(f"[Task Planner] JSON 코드블록 감지 (```json)")
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            print(f"[Task Planner] 일반 코드블록 감지 (```)")
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()

        print(f"[Task Planner] JSON 파싱 시도...")
        result = json.loads(response_text)
        steps = result.get("steps", [])
        summary = result.get("summary", "복합 작업 실행")

        print(f"[Task Planner] 파싱 성공")
        print(f"[Task Planner] summary: '{summary}'")
        print(f"[Task Planner] 분해된 단계: {len(steps)}개")
        for i, step in enumerate(steps):
            action = step.get('action')
            params = step.get('params', {})
            output_key = step.get('output_key', '-')
            print(f"[Task Planner]   Step {i+1}: {action}")
            print(f"[Task Planner]     params: {json.dumps(params, ensure_ascii=False)}")
            print(f"[Task Planner]     output_key: {output_key}")

        print(f"{'='*60}\n")
        return steps, summary

    except json.JSONDecodeError as e:
        print(f"[Task Planner] JSON 파싱 오류: {e}")
        print(f"[Task Planner] 파싱 실패한 텍스트: {response_text}")
        print(f"{'='*60}\n")
        # 파싱 실패 시 단순 질문으로 폴백
        return [], "작업 계획 실패"

    except Exception as e:
        print(f"[Task Planner] 오류 발생: {type(e).__name__}: {e}")
        import traceback
        print(f"[Task Planner] 스택 트레이스:\n{traceback.format_exc()}")
        print(f"{'='*60}\n")
        return [], "작업 계획 실패"
