"""Tool Registry - AI Provider 추상화 및 도구 관리

도구들을 중앙에서 관리하고, Provider 교체 및 Fallback을 지원합니다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Optional


@dataclass
class CostConfig:
    """비용 설정 (토큰 기반)"""
    input_cost_per_1m: float = 0.0    # 입력 토큰 100만개당 비용 (USD)
    output_cost_per_1m: float = 0.0   # 출력 토큰 100만개당 비용 (USD)
    cost_per_call: float = 0.0        # 호출당 고정 비용 (검색 도구 등)

    def calculate(self, input_tokens: int = 0, output_tokens: int = 0) -> float:
        """실제 비용 계산"""
        token_cost = (
            (input_tokens * self.input_cost_per_1m / 1_000_000) +
            (output_tokens * self.output_cost_per_1m / 1_000_000)
        )
        return token_cost + self.cost_per_call


@dataclass
class ToolConfig:
    """도구 설정"""
    name: str                    # 도구 이름 (web_search, translate 등)
    provider: str                # Provider 이름 (xai, gemini, internal)
    handler: Callable            # 실행 함수
    cost: CostConfig = field(default_factory=CostConfig)  # 비용 설정
    fallback: Optional[str] = None  # 장애 시 대체 Provider
    description: str = ""        # 도구 설명


@dataclass
class UsageRecord:
    """사용량 기록"""
    action: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    success: bool = True
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


class ToolRegistry:
    """도구 레지스트리 - 도구 등록, 실행, Fallback 관리"""

    def __init__(self):
        # {action_name: {provider_name: ToolConfig}}
        self._registry: dict[str, dict[str, ToolConfig]] = {}
        # 기본 Provider 설정
        self._default_providers: dict[str, str] = {}
        # 사용량 기록
        self._usage_log: list[UsageRecord] = []
        # user_id 저장 (save_message 등에서 사용)
        self._current_user_id: Optional[int] = None

    def register(
        self,
        action: str,
        provider: str,
        handler: Callable,
        fallback: Optional[str] = None,
        input_cost_per_1m: float = 0.0,
        output_cost_per_1m: float = 0.0,
        cost_per_call: float = 0.0,
        description: str = ""
    ) -> None:
        """도구 등록

        Args:
            action: 작업 이름 (web_search, translate 등)
            provider: Provider 이름 (xai, gemini, internal)
            handler: 실행 함수 (async 함수)
            fallback: 장애 시 대체 Provider
            input_cost_per_1m: 입력 토큰 100만개당 비용 (USD)
            output_cost_per_1m: 출력 토큰 100만개당 비용 (USD)
            cost_per_call: 호출당 고정 비용 (검색 도구 등)
            description: 도구 설명
        """
        if action not in self._registry:
            self._registry[action] = {}

        cost_config = CostConfig(
            input_cost_per_1m=input_cost_per_1m,
            output_cost_per_1m=output_cost_per_1m,
            cost_per_call=cost_per_call
        )

        self._registry[action][provider] = ToolConfig(
            name=action,
            provider=provider,
            handler=handler,
            cost=cost_config,
            fallback=fallback,
            description=description
        )

        # 첫 번째로 등록된 Provider를 기본값으로 설정
        if action not in self._default_providers:
            self._default_providers[action] = provider

        print(f"[Registry] 등록: {action} ({provider})")

    def set_default_provider(self, action: str, provider: str) -> None:
        """기본 Provider 설정"""
        if action in self._registry and provider in self._registry[action]:
            self._default_providers[action] = provider
            print(f"[Registry] 기본 Provider 변경: {action} → {provider}")
        else:
            print(f"[Registry] 경고: {action}/{provider} 가 등록되지 않음")

    def set_user_id(self, user_id: int) -> None:
        """현재 사용자 ID 설정 (save_message 등에서 사용)"""
        self._current_user_id = user_id

    def get_user_id(self) -> Optional[int]:
        """현재 사용자 ID 반환"""
        return self._current_user_id

    async def execute(
        self,
        action: str,
        params: dict,
        preferred_provider: Optional[str] = None
    ) -> str:
        """도구 실행 (Fallback 지원)

        Args:
            action: 작업 이름
            params: 작업 파라미터
            preferred_provider: 선호 Provider (없으면 기본값 사용)

        Returns:
            실행 결과

        Raises:
            ValueError: 알 수 없는 작업인 경우
        """
        if action not in self._registry:
            raise ValueError(f"알 수 없는 작업: {action}")

        providers = self._registry[action]
        provider_name = preferred_provider or self._default_providers.get(action)

        if not provider_name or provider_name not in providers:
            provider_name = next(iter(providers))

        config = providers[provider_name]

        print(f"\n{'─'*40}")
        print(f"[Registry] 실행: {action}")
        print(f"[Registry] Provider: {provider_name}")
        print(f"[Registry] params: {self._truncate_params(params)}")

        try:
            # 핸들러 실행
            result = await config.handler(**params)

            # 토큰 수 추정 (실제 API 응답에서 가져오면 더 정확)
            input_tokens = self._estimate_tokens(str(params))
            output_tokens = self._estimate_tokens(str(result))
            cost = config.cost.calculate(input_tokens, output_tokens)

            # 성공 기록
            self._log_usage(action, provider_name, input_tokens, output_tokens, cost, True)

            print(f"[Registry] 성공: {len(str(result))}자")
            print(f"[Registry] 토큰: ~{input_tokens} in / ~{output_tokens} out")
            print(f"[Registry] 예상 비용: ${cost:.6f}")
            print(f"{'─'*40}\n")
            return result

        except Exception as e:
            error_msg = str(e)
            print(f"[Registry] 오류: {type(e).__name__}: {error_msg}")

            # 실패 기록
            self._log_usage(action, provider_name, 0, 0, 0, False, error_msg)

            # Fallback 시도
            if config.fallback and config.fallback in providers:
                print(f"[Registry] Fallback 시도: {config.fallback}")
                fallback_config = providers[config.fallback]

                try:
                    result = await fallback_config.handler(**params)
                    input_tokens = self._estimate_tokens(str(params))
                    output_tokens = self._estimate_tokens(str(result))
                    cost = fallback_config.cost.calculate(input_tokens, output_tokens)
                    self._log_usage(action, config.fallback, input_tokens, output_tokens, cost, True)
                    print(f"[Registry] Fallback 성공: {len(str(result))}자")
                    print(f"{'─'*40}\n")
                    return result
                except Exception as fallback_error:
                    print(f"[Registry] Fallback 실패: {fallback_error}")
                    self._log_usage(action, config.fallback, 0, 0, 0, False, str(fallback_error))

            print(f"{'─'*40}\n")
            raise

    def _estimate_tokens(self, text: str) -> int:
        """토큰 수 추정 (대략 4글자 = 1토큰)

        실제로는 API 응답의 usage 정보를 사용하는 것이 정확함.
        현재는 추정치로 대체.
        """
        return len(text) // 4

    def _log_usage(
        self,
        action: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """사용량 기록"""
        self._usage_log.append(UsageRecord(
            action=action,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost if success else 0,
            success=success,
            error=error
        ))

    def _truncate_params(self, params: dict, max_length: int = 100) -> str:
        """파라미터 문자열 자르기 (로그용)"""
        result = {}
        for key, value in params.items():
            if isinstance(value, str) and len(value) > max_length:
                result[key] = f"{value[:max_length]}... ({len(value)}자)"
            else:
                result[key] = value
        return str(result)

    def get_usage_report(self) -> dict:
        """사용량 리포트 생성

        Returns:
            {
                "by_action": {
                    "web_search": {
                        "calls": 10,
                        "input_tokens": 1500,
                        "output_tokens": 3000,
                        "cost": 0.05,
                        "success_rate": 0.9
                    }
                },
                "by_provider": {"xai": {...}, "gemini": {...}},
                "total_calls": 25,
                "total_tokens": {"input": 5000, "output": 10000},
                "total_cost": 0.08,
                "success_rate": 0.92
            }
        """
        by_action: dict[str, dict] = {}
        by_provider: dict[str, dict] = {}

        for record in self._usage_log:
            # 액션별 집계
            if record.action not in by_action:
                by_action[record.action] = {
                    "calls": 0, "input_tokens": 0, "output_tokens": 0,
                    "cost": 0.0, "success": 0
                }
            by_action[record.action]["calls"] += 1
            by_action[record.action]["input_tokens"] += record.input_tokens
            by_action[record.action]["output_tokens"] += record.output_tokens
            by_action[record.action]["cost"] += record.cost
            if record.success:
                by_action[record.action]["success"] += 1

            # Provider별 집계
            if record.provider not in by_provider:
                by_provider[record.provider] = {
                    "calls": 0, "input_tokens": 0, "output_tokens": 0,
                    "cost": 0.0, "success": 0
                }
            by_provider[record.provider]["calls"] += 1
            by_provider[record.provider]["input_tokens"] += record.input_tokens
            by_provider[record.provider]["output_tokens"] += record.output_tokens
            by_provider[record.provider]["cost"] += record.cost
            if record.success:
                by_provider[record.provider]["success"] += 1

        # 성공률 계산
        for data in by_action.values():
            data["success_rate"] = data["success"] / data["calls"] if data["calls"] > 0 else 0
        for data in by_provider.values():
            data["success_rate"] = data["success"] / data["calls"] if data["calls"] > 0 else 0

        total_calls = len(self._usage_log)
        total_success = sum(1 for r in self._usage_log if r.success)
        total_input = sum(r.input_tokens for r in self._usage_log)
        total_output = sum(r.output_tokens for r in self._usage_log)
        total_cost = sum(r.cost for r in self._usage_log)

        return {
            "by_action": by_action,
            "by_provider": by_provider,
            "total_calls": total_calls,
            "total_tokens": {"input": total_input, "output": total_output},
            "total_cost": total_cost,
            "success_rate": total_success / total_calls if total_calls > 0 else 0
        }

    def get_available_actions(self) -> list[str]:
        """사용 가능한 작업 목록 반환"""
        return list(self._registry.keys())

    def get_action_info(self, action: str) -> dict:
        """작업 정보 반환"""
        if action not in self._registry:
            return {}

        providers = self._registry[action]
        return {
            "action": action,
            "providers": list(providers.keys()),
            "default_provider": self._default_providers.get(action),
            "configs": {
                name: {
                    "input_cost_per_1m": config.cost.input_cost_per_1m,
                    "output_cost_per_1m": config.cost.output_cost_per_1m,
                    "cost_per_call": config.cost.cost_per_call,
                    "fallback": config.fallback,
                    "description": config.description
                }
                for name, config in providers.items()
            }
        }


# 글로벌 레지스트리 인스턴스
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """글로벌 레지스트리 인스턴스 반환"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
    return _registry


def _register_default_tools(registry: ToolRegistry) -> None:
    """기본 도구 등록"""
    from src.tools.xai_tools import search_web, search_x
    from src.tools.llm import translate, summarize, analyze
    from src.database import save_message

    # xAI Grok 검색 도구
    # - LLM 비용: $0.20/1M input, $0.50/1M output (grok-4-1-fast-reasoning)
    # - 검색 도구: 현재 무료 프로모션 (정가 $5/1000 calls = $0.005/call)
    registry.register(
        action="web_search",
        provider="xai",
        handler=search_web,
        input_cost_per_1m=0.20,
        output_cost_per_1m=0.50,
        cost_per_call=0.0,  # 현재 프로모션 무료
        description="웹에서 최신 정보 검색"
    )

    registry.register(
        action="x_search",
        provider="xai",
        handler=search_x,
        input_cost_per_1m=0.20,
        output_cost_per_1m=0.50,
        cost_per_call=0.0,  # 현재 프로모션 무료
        description="X(트위터)에서 검색"
    )

    # Google Gemini (무료 티어)
    # Gemini 2.0 Flash는 무료 티어 내에서 사용
    registry.register(
        action="translate",
        provider="gemini",
        handler=translate,
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
        description="텍스트 번역"
    )

    registry.register(
        action="summarize",
        provider="gemini",
        handler=summarize,
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
        description="텍스트 요약"
    )

    registry.register(
        action="analyze",
        provider="gemini",
        handler=analyze,
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
        description="텍스트 분석"
    )

    # 내부 도구 (DB) - 비용 없음
    async def save_message_wrapper(content: str, **kwargs) -> str:
        """save_message 래퍼 - user_id를 Registry에서 가져옴"""
        user_id = registry.get_user_id()
        if user_id is None:
            raise ValueError("user_id가 설정되지 않음")

        await save_message(
            user_id=user_id,
            content=content,
            is_forwarded=False
        )
        return f"저장 완료: {content[:50]}..." if len(content) > 50 else f"저장 완료: {content}"

    registry.register(
        action="save_message",
        provider="internal",
        handler=save_message_wrapper,
        description="메시지 DB 저장"
    )

    print(f"[Registry] 기본 도구 {len(registry.get_available_actions())}개 등록 완료")
