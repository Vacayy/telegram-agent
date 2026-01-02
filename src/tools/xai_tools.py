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


def _call_xai_with_tool(query: str, tool_name: str, count: int = None) -> str:
    """xAI API를 호출하여 내장 도구 사용

    Args:
        query: 검색 쿼리
        tool_name: 사용할 도구 이름 (web_search, x_search)
        count: 결과 개수 (선택, 기본값 None = API 기본값 사용)
    """
    print(f"\n{'─'*40}")
    print(f"[xAI Tool] {tool_name} 호출")
    print(f"[xAI Tool] 원본 query: '{query}'")
    print(f"[xAI Tool] count: {count}")
    print(f"[xAI Tool] 모델: grok-4-1-fast-reasoning")

    if not config.XAI_API_KEY:
        print(f"[xAI Tool] 오류: API 키 없음")
        raise SearchError("XAI_API_KEY가 설정되지 않았습니다.")

    # count가 지정된 경우 쿼리에 포함
    original_query = query
    if count is not None and count > 0:
        query = f"{query} (Return exactly {count} most recent results)"
        print(f"[xAI Tool] count 적용된 query: '{query}'")

    try:
        print(f"[xAI Tool] API 호출 중...")
        response = xai_client.responses.create(
            model="grok-4-1-fast-reasoning",
            tools=[{"type": tool_name}],
            input=query,
        )
        print(f"[xAI Tool] API 응답 수신")

        # 응답에서 텍스트 추출
        if hasattr(response, 'output') and response.output:
            print(f"[xAI Tool] output 항목 수: {len(response.output)}")
            for idx, item in enumerate(response.output):
                if hasattr(item, 'content') and item.content:
                    for content in item.content:
                        if hasattr(content, 'text'):
                            result = content.text
                            print(f"[xAI Tool] 텍스트 추출 성공: {len(result)}자")
                            print(f"[xAI Tool] 결과 미리보기: {result[:150]}...")
                            print(f"{'─'*40}\n")
                            return result

        print(f"[xAI Tool] 응답에서 텍스트를 찾을 수 없음")
        print(f"[xAI Tool] 응답 구조: {response}")
        raise SearchError("검색 결과를 가져오지 못했습니다. 응답이 비어있습니다.")

    except SearchError:
        raise
    except Exception as e:
        error_msg = str(e)
        print(f"[xAI Tool] 예외 발생: {type(e).__name__}: {error_msg}")
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


# 직접 호출용 함수 (명령어 및 Executor에서 사용)
async def search_web(query: str, count: int = None) -> str:
    """웹 검색 직접 호출

    Args:
        query: 검색 쿼리
        count: 결과 개수 (선택, 기본값 None = API 기본값)

    Returns:
        검색 결과 문자열
    """
    return _call_xai_with_tool(query, "web_search", count)


async def search_x(query: str, count: int = None) -> str:
    """X 검색 직접 호출

    Args:
        query: 검색 쿼리
        count: 결과 개수 (선택, 기본값 None = API 기본값)

    Returns:
        X 검색 결과 문자열
    """
    return _call_xai_with_tool(query, "x_search", count)
