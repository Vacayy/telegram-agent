"""xAI 내장 도구 (web_search, x_search)"""

from openai import OpenAI
from langchain_core.tools import tool

import config


class SearchError(Exception):
    """검색 관련 에러"""
    pass


# xAI API 클라이언트
xai_client = OpenAI(
    api_key=config.XAI_API_KEY,
    base_url="https://api.x.ai/v1"
)


def _call_xai_with_tool(query: str, tool_name: str) -> str:
    """xAI API를 호출하여 내장 도구 사용"""
    if not config.XAI_API_KEY:
        raise SearchError("XAI_API_KEY가 설정되지 않았습니다.")

    try:
        response = xai_client.responses.create(
            model="grok-4-1-fast-reasoning",
            tools=[{"type": tool_name}],
            input=query,
        )

        # 응답에서 텍스트 추출
        if hasattr(response, 'output') and response.output:
            for item in response.output:
                if hasattr(item, 'content') and item.content:
                    for content in item.content:
                        if hasattr(content, 'text'):
                            return content.text

        raise SearchError("검색 결과를 가져오지 못했습니다. 응답이 비어있습니다.")

    except SearchError:
        raise
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg:
            raise SearchError("API 인증 실패: API 키를 확인해주세요.")
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            raise SearchError("API 요청 한도 초과: 잠시 후 다시 시도해주세요.")
        elif "timeout" in error_msg.lower():
            raise SearchError("API 요청 시간 초과: 네트워크를 확인하거나 잠시 후 다시 시도해주세요.")
        elif "connection" in error_msg.lower():
            raise SearchError("API 연결 실패: 네트워크 연결을 확인해주세요.")
        else:
            raise SearchError(f"검색 중 오류 발생: {error_msg}")


@tool
def web_search(query: str) -> str:
    """
    웹에서 최신 정보를 검색합니다.
    실시간 뉴스, 최신 데이터, 현재 상황 등을 조회할 때 사용하세요.

    Args:
        query: 검색할 내용

    Returns:
        검색 결과 요약
    """
    return _call_xai_with_tool(query, "web_search")


@tool
def x_search(query: str) -> str:
    """
    X(트위터)에서 정보를 검색합니다.
    트렌드, 실시간 반응, 특정 인물/주제에 대한 트윗을 조회할 때 사용하세요.

    Args:
        query: 검색할 내용 (키워드, 해시태그, 사용자명 등)

    Returns:
        X 검색 결과 요약
    """
    return _call_xai_with_tool(query, "x_search")


def get_tools():
    """사용 가능한 모든 Tool 반환"""
    return [web_search, x_search]


# 직접 호출용 함수 (명령어에서 사용)
async def search_web(query: str) -> str:
    """웹 검색 직접 호출"""
    return _call_xai_with_tool(query, "web_search")


async def search_x(query: str) -> str:
    """X 검색 직접 호출"""
    return _call_xai_with_tool(query, "x_search")
