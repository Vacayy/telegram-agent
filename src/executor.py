"""Task Executor - 계획된 작업을 순차 실행"""

import json
from typing import Any, Callable, Coroutine, Optional

from src.tools.xai_tools import search_web, search_x
from src.tools.llm import translate, summarize, analyze
from src.database import save_message


# 작업별 상태 메시지 템플릿
ACTION_STATUS_TEMPLATES = {
    "web_search": "🌐 웹 검색 중... ('{query}')",
    "x_search": "🐦 X 검색 중... ('{query}')",
    "translate": "🌍 번역 중...",
    "summarize": "📝 요약 중...",
    "analyze": "🔍 분석 중...",
    "save_message": "💾 저장 중...",
}


class TaskExecutor:
    """계획된 작업을 순차 실행하는 실행기"""

    def __init__(
        self,
        user_id: int,
        status_callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None
    ):
        """
        Args:
            user_id: 사용자 ID
            status_callback: 상태 업데이트 콜백 함수
        """
        self.user_id = user_id
        self.status_callback = status_callback
        self.context_chain: dict[str, str] = {}  # 단계별 결과 저장
        self.status_lines: list[str] = []  # 상태 메시지 스택

    async def execute(self, steps: list[dict], summary: str) -> str:
        """단계별 작업 실행

        Args:
            steps: 실행할 작업 단계 리스트
            summary: 작업 요약 설명

        Returns:
            최종 결과 메시지
        """
        print(f"\n{'='*60}")
        print(f"[Executor] 실행 시작")
        print(f"[Executor] user_id: {self.user_id}")
        print(f"[Executor] 총 단계 수: {len(steps)}")
        print(f"[Executor] summary: '{summary}'")

        if not steps:
            print(f"[Executor] 실행할 작업 없음")
            print(f"{'='*60}\n")
            return "❌ 실행할 작업이 없습니다."

        results = []

        for i, step in enumerate(steps):
            action = step.get("action")
            params = step.get("params", {})
            output_key = step.get("output_key")

            print(f"\n{'─'*40}")
            print(f"[Executor] Step {i+1}/{len(steps)}: {action}")
            print(f"[Executor] 원본 params: {json.dumps(params, ensure_ascii=False)}")

            # 파라미터에서 $변수 참조 해결
            resolved_params = self._resolve_params(params)
            if params != resolved_params:
                print(f"[Executor] 변수 치환 후: {json.dumps(resolved_params, ensure_ascii=False, default=str)[:200]}")

            # 상태 업데이트
            await self._update_status(action, resolved_params)

            try:
                # 작업 실행
                print(f"[Executor] _execute_action() 호출 중...")
                result = await self._execute_action(action, resolved_params)
                result_preview = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                print(f"[Executor] Step {i+1} 완료")
                print(f"[Executor] 결과 길이: {len(str(result))}자")
                print(f"[Executor] 결과 미리보기: {result_preview}")

                # 결과 저장 (다음 단계에서 참조 가능)
                if output_key:
                    self.context_chain[output_key] = result
                    print(f"[Executor] context_chain['{output_key}'] 저장됨")

                results.append({
                    "action": action,
                    "success": True,
                    "result": result
                })

            except Exception as e:
                print(f"[Executor] Step {i+1} 오류 발생: {type(e).__name__}: {e}")
                import traceback
                print(f"[Executor] 스택 트레이스:\n{traceback.format_exc()}")
                results.append({
                    "action": action,
                    "success": False,
                    "error": str(e)
                })
                # 오류 발생 시 중단
                print(f"[Executor] 오류로 인해 실행 중단")
                break

        print(f"\n{'─'*40}")
        print(f"[Executor] 전체 실행 완료")
        print(f"[Executor] 성공: {sum(1 for r in results if r.get('success'))}/{len(results)}")
        print(f"{'='*60}\n")

        return self._format_final_result(results, summary)

    def _resolve_params(self, params: dict) -> dict:
        """$변수 참조를 실제 값으로 치환

        Args:
            params: 원본 파라미터 딕셔너리

        Returns:
            변수가 치환된 파라미터 딕셔너리
        """
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                # Case 1: $변수명 형태 (정상)
                if value.startswith("$"):
                    var_name = value[1:]  # $ 제거
                    if var_name in self.context_chain:
                        resolved[key] = self.context_chain[var_name]
                        print(f"[Executor] 변수 치환: ${var_name} → ({len(str(self.context_chain[var_name]))}자)")
                    else:
                        print(f"[Executor] 경고: ${var_name} 변수를 찾을 수 없음")
                        resolved[key] = value
                # Case 2: $ 없이 변수명만 있는 경우 (LLM이 $ 빼먹은 경우 방어)
                elif value in self.context_chain:
                    resolved[key] = self.context_chain[value]
                    print(f"[Executor] 변수 치환 ($ 누락 보정): {value} → ({len(str(self.context_chain[value]))}자)")
                else:
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    async def _update_status(self, action: str, params: dict) -> None:
        """상태 메시지 업데이트

        Args:
            action: 작업 이름
            params: 작업 파라미터
        """
        template = ACTION_STATUS_TEMPLATES.get(action, f"🔧 {action} 실행 중...")

        # 템플릿에 파라미터 적용
        try:
            if action in ["web_search", "x_search"]:
                status_line = template.format(query=params.get("query", ""))
            else:
                status_line = template
        except KeyError:
            status_line = template

        self.status_lines.append(status_line)

        if self.status_callback:
            try:
                await self.status_callback("\n".join(self.status_lines))
            except Exception as e:
                print(f"[Executor] 상태 업데이트 실패: {e}")

    async def _execute_action(self, action: str, params: dict) -> str:
        """개별 작업 실행

        Args:
            action: 작업 이름
            params: 작업 파라미터

        Returns:
            작업 결과 문자열

        Raises:
            ValueError: 알 수 없는 작업인 경우
        """
        if action == "web_search":
            query = params.get("query", "")
            count = params.get("count")
            print(f"[Executor] web_search 호출: query='{query}', count={count}")
            return await search_web(query=query, count=count)

        elif action == "x_search":
            query = params.get("query", "")
            count = params.get("count")
            print(f"[Executor] x_search 호출: query='{query}', count={count}")
            return await search_x(query=query, count=count)

        elif action == "translate":
            text = params.get("text", "")
            to_lang = params.get("to", "ko")
            print(f"[Executor] translate 호출: to='{to_lang}', text길이={len(text)}자")
            return await translate(text=text, to=to_lang)

        elif action == "summarize":
            text = params.get("text", "")
            language = params.get("language", "same")
            print(f"[Executor] summarize 호출: language='{language}', text길이={len(text)}자")
            return await summarize(text=text, language=language)

        elif action == "analyze":
            text = params.get("text", "")
            question = params.get("question")
            print(f"[Executor] analyze 호출: question='{question}', text길이={len(text)}자")
            return await analyze(text=text, question=question)

        elif action == "save_message":
            content = params.get("content", "")
            print(f"[Executor] save_message 호출: content길이={len(content)}자")
            await save_message(
                user_id=self.user_id,
                content=content,
                is_forwarded=False
            )
            print(f"[Executor] DB 저장 완료")
            return f"저장 완료: {content[:50]}..." if len(content) > 50 else f"저장 완료: {content}"

        else:
            print(f"[Executor] 알 수 없는 action: {action}")
            raise ValueError(f"알 수 없는 작업: {action}")

    def _format_final_result(self, results: list[dict], summary: str) -> str:
        """최종 결과 메시지 포맷팅

        Args:
            results: 각 단계별 결과 리스트
            summary: 작업 요약 설명

        Returns:
            사용자에게 보여줄 최종 메시지
        """
        if not results:
            return "❌ 작업을 수행하지 못했습니다."

        # 모든 단계 성공 여부 확인
        all_success = all(r.get("success") for r in results)

        if all_success:
            # 마지막 결과를 주요 결과로 사용
            last_result = results[-1].get("result", "")

            # 결과가 너무 길면 요약
            if len(last_result) > 2000:
                last_result = last_result[:2000] + "...\n\n(결과가 너무 길어 일부만 표시)"

            return f"✅ {summary}\n\n{last_result}"
        else:
            # 실패한 단계 찾기
            failed = next((r for r in results if not r.get("success")), None)
            if failed:
                return f"❌ 작업 실패: {failed.get('action')}\n오류: {failed.get('error')}"
            return "❌ 알 수 없는 오류가 발생했습니다."
