from typing import Any, Callable, Coroutine, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.callbacks import AsyncCallbackHandler
from langchain.agents import AgentExecutor, create_openai_tools_agent

import config
from src.tools import get_tools
from src.tools.xai_tools import search_web, search_x
from src.database import get_all_messages_as_context


# 도구 이름 -> 사용자 친화적 메시지 템플릿 매핑
TOOL_STATUS_TEMPLATES = {
    "web_search": "🌐 웹 검색 중... ('{query.query}')",
    "x_search": "🐦 X 검색 중... ('{query.query}')",
}


class ToolStatusCallback(AsyncCallbackHandler):
    """도구 사용 시 상태를 알려주는 비동기 콜백 핸들러"""

    def __init__(self, status_callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None):
        self.status_callback = status_callback
        self.tool_calls = []  # 호출된 도구 목록

    async def on_tool_start(
        self,
        serialized: dict,
        input_str: str,
        **kwargs
    ) -> None:
        """도구 실행 시작 시 호출"""
        tool_name = serialized.get("name", "unknown")
        self.tool_calls.append(tool_name)

        if self.status_callback:
            template = TOOL_STATUS_TEMPLATES.get(tool_name)
            if template:
                message = template.format(query=input_str)
            else:
                message = f"🔧 {tool_name} 실행 중..."
            await self.status_callback(message)

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
    # xAI Grok API는 OpenAI 호환 API를 제공
    llm = ChatOpenAI(
        model="grok-4-1-fast-reasoning",
        api_key=config.XAI_API_KEY,
        base_url="https://api.x.ai/v1",
        temperature=0.7
    )

    tools = get_tools()

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5
    )


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
    try:
        # 저장된 메시지 컨텍스트 가져오기
        context = await get_all_messages_as_context(user_id)

        # 콜백 핸들러 생성
        tool_callback = ToolStatusCallback(status_callback)

        # Agent 실행 (비동기)
        agent_executor = create_agent()
        result = await agent_executor.ainvoke(
            {
                "input": user_message,
                "context": context,
                "chat_history": []
            },
            config={"callbacks": [tool_callback]}
        )

        return result.get("output", "죄송합니다. 응답을 생성하지 못했습니다.")

    except Exception as e:
        return f"오류가 발생했습니다: {str(e)}"


async def search_web_only(query: str) -> str:
    """웹 검색만 수행 (/search 명령어용)"""
    return await search_web(query)


async def search_x_only(query: str) -> str:
    """X 검색만 수행 (/x 명령어용)"""
    return await search_x(query)
