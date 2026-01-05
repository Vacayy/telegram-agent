from typing import Any, Callable, Coroutine, Optional, Literal
from enum import Enum

from google import genai
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.callbacks import AsyncCallbackHandler
from langchain.agents import AgentExecutor, create_openai_tools_agent

import config
from src.tools import get_tools
from src.tools.xai_tools import search_web, search_x
from src.database import get_all_messages_as_context


class UserIntent(str, Enum):
    """사용자 의도 분류"""
    SAVE_MESSAGE = "save_message"        # 메시지 저장
    LIST_MESSAGES = "list_messages"      # 저장된 메시지 목록 보기
    LIST_ALL_MESSAGES = "list_all"       # 전체 메시지 보기
    GET_MESSAGE = "get_message"          # 특정 메시지 내용 조회
    CLEAR_MESSAGES = "clear_messages"    # 메시지 전체 삭제
    DELETE_MESSAGE = "delete_message"    # 특정 메시지 삭제
    HELP = "help"                        # 도움말
    USAGE = "usage"                      # 사용량 조회
    QUESTION = "question"                # 일반 질문 (AI Agent 필요)
    COMPLEX = "complex"                  # 복합 작업 (Task Planner 필요)


INTENT_CLASSIFIER_PROMPT = """당신은 사용자 의도를 분류하는 분류기입니다.

사용자 메시지를 분석하여 다음 중 하나의 의도로 분류하세요:

- save_message: 단순히 특정 내용만 저장 (예: "'안녕' 저장해줘", "메모해줘: 내일 회의")
- list_messages: 저장된 메시지 목록 조회 (예: "저장된 거 보여줘", "뭐 저장했지?")
- list_all: 전체 메시지 모두 보기 (예: "전체 목록", "다 보여줘")
- get_message: 특정 메시지 내용 조회 (예: "1번 메시지 알려줘", "3번 내용 보여줘", "2번 뭐야?")
  [조회 동사: 알려줘, 보여줘, 뭐야, 읽어줘, 확인해줘]
- clear_messages: 저장된 메시지 전부 삭제 (예: "다 지워줘", "초기화")
- delete_message: 특정 메시지 삭제 (예: "1번 삭제해줘", "첫번째 거 지워")
  [삭제 동사: 삭제해줘, 지워줘, 없애줘]
- help: 사용법이나 도움말 (예: "어떻게 써?", "도움말")
- usage: 사용량/비용 조회 (예: "사용량 알려줘", "얼마나 썼어?", "비용 확인", "API 사용량")
- question: 단순 질문이나 분석 요청 (예: "이거 분석해줘", "날씨 알려줘", "요약해줘")
- complex: 여러 단계가 연결된 복합 작업 요청
  예: "검색해서 저장해줘", "X에서 찾아서 번역해줘", "뉴스 찾아서 요약해줘"

[중요 - get_message vs delete_message 구분]
"N번" 또는 "N번째" 패턴이 있을 때 동사로 구분:
- "N번 알려줘/보여줘/뭐야/읽어줘" → get_message (조회)
- "N번 삭제해줘/지워줘/없애줘" → delete_message (삭제)

[중요 - complex 판단 기준]
다음과 같이 2개 이상의 동작이 순서대로 연결된 경우 complex로 분류:
- "검색 → 저장", "검색 → 번역", "검색 → 요약"
- "~해서 ~해줘", "~한 다음 ~해줘", "~하고 ~해줘"
- 단일 의도로 마무리되지 않고 여러 의도가 연결되어있는 모든 경우

[중요]
- 반드시 위 10개 중 하나만 출력하세요.
- 다른 설명 없이 의도 이름만 출력하세요.
- 단일 동작이면 question, 복합 동작이면 complex

사용자 메시지: {message}

의도:"""


async def classify_intent(message: str) -> tuple[UserIntent, Optional[str]]:
    """Gemini 2.0 Flash를 사용하여 사용자 의도 분류

    Args:
        message: 사용자 메시지

    Returns:
        (의도, 인자) 튜플.
        - delete_message인 경우: 삭제할 번호 (str)
        - save_message인 경우: 저장할 내용 (str)
    """
    print(f"\n{'='*60}")
    print(f"[의도 분류] 시작")
    print(f"[의도 분류] 입력 메시지: '{message}'")
    print(f"[의도 분류] 모델: gemini-2.0-flash")

    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    try:
        prompt = INTENT_CLASSIFIER_PROMPT.format(message=message)
        print(f"[의도 분류] 프롬프트 길이: {len(prompt)}자")

        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        intent_str = response.text.strip().lower()
        print(f"[의도 분류] LLM 원본 응답: '{response.text.strip()}'")

        # 의도 매핑
        intent_map = {
            "save_message": UserIntent.SAVE_MESSAGE,
            "list_messages": UserIntent.LIST_MESSAGES,
            "list_all": UserIntent.LIST_ALL_MESSAGES,
            "get_message": UserIntent.GET_MESSAGE,
            "clear_messages": UserIntent.CLEAR_MESSAGES,
            "delete_message": UserIntent.DELETE_MESSAGE,
            "help": UserIntent.HELP,
            "usage": UserIntent.USAGE,
            "question": UserIntent.QUESTION,
            "complex": UserIntent.COMPLEX,
        }

        intent = intent_map.get(intent_str, UserIntent.QUESTION)

        print(f"[의도 분류] 매핑 결과: '{intent_str}' → {intent.value}")

        # 의도별 인자 추출
        import re
        arg = None

        if intent == UserIntent.GET_MESSAGE:
            print(f"[의도 분류] GET_MESSAGE - 번호 추출 시도")
            # 조회할 번호 추출
            numbers = re.findall(r'\d+', message)
            if numbers:
                arg = numbers[0]
                print(f"[의도 분류] 추출된 번호: {arg}")

        elif intent == UserIntent.DELETE_MESSAGE:
            print(f"[의도 분류] DELETE_MESSAGE - 번호 추출 시도")
            # 삭제할 번호 추출
            numbers = re.findall(r'\d+', message)
            if numbers:
                arg = numbers[0]
                print(f"[의도 분류] 추출된 번호: {arg}")

        elif intent == UserIntent.SAVE_MESSAGE:
            print(f"[의도 분류] SAVE_MESSAGE - 저장 내용 추출 시도")
            # 저장할 내용 추출 (따옴표 안의 내용 또는 키워드 뒤의 내용)
            # 패턴 1: 따옴표로 감싼 내용 ('xxx' 또는 "xxx")
            quoted = re.findall(r"['\"](.+?)['\"]", message)
            if quoted:
                arg = quoted[0]
                print(f"[의도 분류] 따옴표에서 추출: '{arg}'")
            else:
                print(f"[의도 분류] 따옴표 없음, 패턴 매칭 시도")
                # 패턴 2: "저장해줘", "기억해줘", "메모해줘" 등 앞의 내용
                patterns = [
                    r"(.+?)\s*저장해\s*줘?",
                    r"(.+?)\s*기억해\s*줘?",
                    r"(.+?)\s*메모해\s*줘?",
                    r"저장해\s*줘?\s*[:\s]*(.+)",
                    r"기억해\s*줘?\s*[:\s]*(.+)",
                    r"메모해\s*줘?\s*[:\s]*(.+)",
                ]
                for pattern in patterns:
                    match = re.search(pattern, message)
                    if match:
                        arg = match.group(1).strip()
                        print(f"[의도 분류] 패턴 '{pattern}'에서 추출: '{arg}'")
                        break

        print(f"[의도 분류] 최종 결과: intent={intent.value}, arg={arg}")
        print(f"{'='*60}\n")
        return intent, arg

    except Exception as e:
        # 오류 시 기본값으로 question 반환
        print(f"[의도 분류] 오류 발생: {type(e).__name__}: {e}")
        print(f"[의도 분류] 기본값 QUESTION 반환")
        print(f"{'='*60}\n")
        return UserIntent.QUESTION, None


# 도구 이름 -> 사용자 친화적 메시지 템플릿 매핑
TOOL_STATUS_TEMPLATES = {
    "web_search": "🌐 웹 검색 중... ('{query.query}')",
    "x_search": "🐦 X 검색 중... ('{query.query}')",
}


class ToolStatusCallback(AsyncCallbackHandler):
    """도구 사용 시 상태를 알려주는 비동기 콜백 핸들러"""

    def __init__(self, status_callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None):
        super().__init__()
        self.status_callback = status_callback
        self.status_lines = []  # 상태 메시지 스택

    def _extract_query(self, input_str: str) -> str:
        """input_str에서 검색어 추출"""
        import json
        import ast

        query = input_str
        try:
            # Case 1: JSON 문자열 ({"query": "..."})
            parsed = json.loads(input_str)
            if isinstance(parsed, dict) and "query" in parsed:
                return parsed["query"]
        except (json.JSONDecodeError, TypeError):
            pass

        # Case 2: Python dict repr 형태 ({'query': '...'})
        try:
            parsed = ast.literal_eval(input_str)
            if isinstance(parsed, dict) and "query" in parsed:
                return parsed["query"]
        except (ValueError, SyntaxError):
            pass

        return query

    def _build_status_message(self) -> str:
        """스택에 쌓인 상태들을 하나의 메시지로 조합"""
        return "\n".join(self.status_lines)

    async def on_tool_start(
        self,
        serialized: dict,
        input_str: str,
        *,
        run_id,
        parent_run_id=None,
        tags=None,
        metadata=None,
        inputs=None,
        **kwargs
    ) -> None:
        """도구 실행 시작 시 호출"""
        tool_name = serialized.get("name", "unknown")
        query = self._extract_query(input_str)

        print(f"[ToolCallback] 도구 시작: {tool_name}, 검색어: {query}")

        # 상태 메시지 생성
        if tool_name == "web_search":
            status_line = f"🌐 웹 검색 중... ('{query}')"
        elif tool_name == "x_search":
            status_line = f"🐦 X 검색 중... ('{query}')"
        else:
            status_line = f"🔧 {tool_name} 실행 중..."

        # 스택에 추가
        self.status_lines.append(status_line)

        # 전체 상태 업데이트
        if self.status_callback:
            try:
                await self.status_callback(self._build_status_message())
            except Exception as e:
                print(f"[ToolCallback] 상태 업데이트 실패: {e}")

SYSTEM_PROMPT = """당신은 사용자의 개인 AI 비서입니다.

[역할]
- 사용자가 저장한 메시지를 기억하고, 질문에 답변합니다.
- 필요시 웹 검색과 X(트위터) 검색을 통해 최신 정보를 제공합니다.

[저장된 메시지 컨텍스트]
{context}

[사용 가능한 도구]
- web_search: 웹에서 최신 정보를 검색합니다.
- x_search: X(트위터)에서 트렌드, 반응, 트윗을 검색합니다.

[중요: 대명사 및 지시어 해석]
사용자가 다음과 같은 표현을 사용하면, [가장 최근 저장된 메시지]를 참조하세요:
- "이거", "이것", "이 메시지", "이 내용"
- "방금 거", "방금 것", "방금 보낸 거"
- "위에 거", "위에 것", "위 메시지"
- "저거", "그거", "그것"
- "확인해줘", "분석해줘", "요약해줘" (단독 사용 시)
- "뭐야?", "뭔가요?", "무슨 내용이야?" (단독 사용 시)

예시:
- 사용자: "이거 확인해줘" → [가장 최근 저장된 메시지] 내용을 분석/확인
- 사용자: "방금 거 요약해줘" → [가장 최근 저장된 메시지]를 요약
- 사용자: "이게 주가에 영향을 줄까?" → [가장 최근 저장된 메시지]와 관련하여 분석

[지침]
1. 사용자의 질문이 저장된 메시지와 관련 있으면, 해당 내용을 참조하여 답변하세요.
2. 실시간 정보나 최신 뉴스가 필요한 경우, web_search 도구를 사용하세요.
3. 트위터 트렌드나 실시간 반응이 필요한 경우, x_search 도구를 사용하세요.
4. 저장된 내용이 없거나 관련 없는 질문이면, 일반적인 지식으로 답변하세요.
5. 답변은 간결하고 명확하게 한국어로 작성하세요.
6. 검색 결과를 인용할 때는 출처를 명시하세요.

[중요: 응답 형식]
- 마크다운 문법을 사용하지 마세요. (**, ##, *, ``` 등 금지)
- 일반 텍스트로만 답변하세요.
- 강조가 필요하면 대괄호 [중요] 또는 줄바꿈으로 구분하세요.
"""


def create_agent():
    """LangChain Agent 생성 (xAI Grok 사용)"""
    print(f"\n{'='*60}")
    print(f"[Agent 생성] 시작")
    print(f"[Agent 생성] 모델: grok-4-1-fast-reasoning")
    print(f"[Agent 생성] API: https://api.x.ai/v1")

    # xAI Grok API는 OpenAI 호환 API를 제공
    llm = ChatOpenAI(
        model="grok-4-1-fast-reasoning",
        api_key=config.XAI_API_KEY,
        base_url="https://api.x.ai/v1",
        temperature=0.7
    )

    tools = get_tools()
    print(f"[Agent 생성] 사용 가능한 도구: {[t.name for t in tools]}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)
    print(f"[Agent 생성] Agent 인스턴스 생성 완료")

    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5
    )
    print(f"[Agent 생성] AgentExecutor 생성 완료 (max_iterations=5)")
    print(f"{'='*60}\n")

    return executor


async def get_ai_response(
    user_id: int,
    user_message: str,
    status_callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None
) -> str:
    """사용자 메시지에 대한 AI 응답 생성

    Args:
        user_id: 사용자 ID
        user_message: 사용자 메시지
        status_callback: 도구 사용 시 상태를 알려주는 비동기 콜백 함수

    Returns:
        AI 응답 문자열
    """
    print(f"\n{'='*60}")
    print(f"[AI 응답] 시작")
    print(f"[AI 응답] user_id: {user_id}")
    print(f"[AI 응답] 메시지: '{user_message}'")

    try:
        # 저장된 메시지 컨텍스트 가져오기
        print(f"[AI 응답] 컨텍스트 로드 중...")
        context = await get_all_messages_as_context(user_id)
        context_preview = context[:200] + "..." if len(context) > 200 else context
        print(f"[AI 응답] 컨텍스트 로드 완료: {len(context)}자")
        print(f"[AI 응답] 컨텍스트 미리보기: {context_preview}")

        # 콜백 핸들러 생성
        tool_callback = ToolStatusCallback(status_callback)
        print(f"[AI 응답] ToolStatusCallback 생성됨")

        # Agent 생성 및 실행
        agent_executor = create_agent()

        print(f"[AI 응답] Agent.ainvoke() 호출 중...")
        result = await agent_executor.ainvoke(
            {
                "input": user_message,
                "context": context,
                "chat_history": []
            },
            config={"callbacks": [tool_callback]}
        )

        output = result.get("output", "죄송합니다. 응답을 생성하지 못했습니다.")
        print(f"[AI 응답] Agent 실행 완료")
        print(f"[AI 응답] 응답 길이: {len(output)}자")
        print(f"[AI 응답] 응답 미리보기: {output[:200]}...")
        print(f"{'='*60}\n")

        return output

    except Exception as e:
        print(f"[AI 응답] 오류 발생: {type(e).__name__}: {e}")
        import traceback
        print(f"[AI 응답] 스택 트레이스:\n{traceback.format_exc()}")
        print(f"{'='*60}\n")
        return f"오류가 발생했습니다: {str(e)}"


async def search_web_only(query: str) -> str:
    """웹 검색만 수행 (/search 명령어용)"""
    return await search_web(query)


async def search_x_only(query: str) -> str:
    """X 검색만 수행 (/x 명령어용)"""
    return await search_x(query)
