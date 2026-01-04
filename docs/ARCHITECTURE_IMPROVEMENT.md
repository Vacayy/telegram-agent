# 아키텍처 개선 계획서

## 현황 분석

### 현재 아키텍처

```
사용자 메시지
    ↓
[1단계] 의도 분류 (Gemini 2.0 Flash)
    ↓
┌─────────────────────────────────────────┐
│ save_message → DB 저장                  │
│ list_messages → 메시지 목록             │
│ delete_message → 메시지 삭제            │
│ clear_messages → 전체 삭제              │
│ help → 도움말                           │
│ question → [2단계] AI Agent             │
└─────────────────────────────────────────┘
    ↓ (question인 경우만)
[2단계] AI Agent (Grok)
    ├─ web_search (Grok 내장)
    └─ x_search (Grok 내장)
```

### 문제점

#### 1. 복합 의도 처리 불가

```
사용자: "X에서 @elon_musk 검색해서 번역 후 저장해줘"

기대 동작:
  1. X 검색 (@elon_musk)
  2. 번역 (영→한)
  3. DB 저장

실제 동작:
  - 의도 분류: save_message (마지막 키워드만 인식)
  - 결과: 원문 그대로 저장됨
```

**원인**: 의도 분류가 단일 레이블만 반환하며, 작업 계획(Planning) 로직이 없음

#### 2. Grok 의존성

| 기능 | 현재 구현 | 문제 |
|------|-----------|------|
| 웹 검색 | Grok web_search | Grok 전용 |
| X 검색 | Grok x_search | Grok 전용 (대체 불가) |
| 분석/요약 | Grok LLM | 다른 LLM으로 교체 어려움 |

- Grok API 장애 시 전체 기능 마비
- 다른 LLM이 더 저렴하거나 성능 좋아져도 교체 비용 큼

#### 3. 기능 확장의 어려움

새 기능 추가 시 필요한 작업:
1. `UserIntent` enum에 새 의도 추가
2. 의도 분류 프롬프트 수정
3. `bot.py`에 핸들러 추가
4. 필요시 Agent 도구 추가

**문제**: 의도 분류가 복잡해질수록 정확도 저하

---

## 개선 목표

### 1. 기능 확장성

- 새 기능 추가 시 최소한의 코드 변경
- 의도 분류와 실행 로직 분리
- 복합 작업 자연스럽게 처리

### 2. 비용 최적화

- 작업별 최적 AI 모델 선택
- 단순 작업은 저렴한 모델 사용
- Provider fallback으로 비용/성능 균형

---

## 개선 아키텍처

### Phase 1: Task Planner 도입

```
사용자 메시지
    ↓
[1단계] 의도 분류 (Gemini Flash)
    ↓
┌─────────────────────────────────────────┐
│ simple_intent (기존 6가지)              │
│   → 직접 처리                           │
│                                         │
│ complex_intent                          │
│   → [2단계] Task Planner                │
└─────────────────────────────────────────┘
    ↓ (complex_intent인 경우)
[2단계] Task Planner (Gemini Flash)
    ↓
[3단계] Task Executor
    ├─ Step 1: X 검색
    ├─ Step 2: 번역
    └─ Step 3: 저장
```

#### 변경 사항

**1. 의도 분류 단순화**

```python
class UserIntent(str, Enum):
    # 단순 의도 (직접 처리)
    SAVE_MESSAGE = "save_message"
    LIST_MESSAGES = "list_messages"
    DELETE_MESSAGE = "delete_message"
    CLEAR_MESSAGES = "clear_messages"
    HELP = "help"

    # 복합 의도 (Task Planner로 라우팅)
    COMPLEX = "complex"
```

**2. Task Planner 추가**

```python
# src/planner.py (신규)

TASK_PLANNER_PROMPT = """
사용자 요청을 분석하여 실행 가능한 단계로 분해하세요.

사용 가능한 작업:
- web_search: 웹에서 정보 검색
- x_search: X(트위터)에서 검색
- translate: 텍스트 번역
- summarize: 텍스트 요약
- save_message: DB에 저장
- analyze: 내용 분석

출력 형식 (JSON):
{
    "steps": [
        {"action": "x_search", "params": {"query": "..."}, "output_key": "result1"},
        {"action": "translate", "params": {"text": "$result1", "to": "ko"}, "output_key": "result2"},
        {"action": "save_message", "params": {"content": "$result2"}}
    ]
}
"""

async def plan_tasks(user_message: str, context: str) -> list[dict]:
    """사용자 요청을 실행 단계로 분해"""
    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=TASK_PLANNER_PROMPT.format(
            message=user_message,
            context=context
        )
    )

    return json.loads(response.text)["steps"]
```

**3. Task Executor 추가**

```python
# src/executor.py (신규)

class TaskExecutor:
    def __init__(self, user_id: int, status_callback=None):
        self.user_id = user_id
        self.status_callback = status_callback
        self.context_chain = {}  # 이전 단계 결과 저장

    async def execute(self, steps: list[dict]) -> str:
        """단계별 작업 실행"""
        for step in steps:
            action = step["action"]
            params = self._resolve_params(step["params"])

            # 상태 업데이트
            await self._update_status(action, params)

            # 작업 실행
            result = await self._execute_action(action, params)

            # 결과 저장 (다음 단계에서 참조 가능)
            if "output_key" in step:
                self.context_chain[step["output_key"]] = result

        return self.context_chain.get(steps[-1].get("output_key", ""), "완료")

    def _resolve_params(self, params: dict) -> dict:
        """$변수 참조 해결"""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                var_name = value[1:]
                resolved[key] = self.context_chain.get(var_name, value)
            else:
                resolved[key] = value
        return resolved

    async def _execute_action(self, action: str, params: dict) -> str:
        """개별 작업 실행"""
        handler = ACTION_REGISTRY.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
        return await handler(params, self.user_id)
```

### Phase 2: Tool Registry (AI-Agnostic)

```python
# src/registry.py (신규)

@dataclass
class ToolConfig:
    provider: str           # "xai", "gemini", "internal"
    handler: Callable       # 실행 함수
    fallback: str = None    # 대체 provider
    cost_per_call: float = 0.0

TOOL_REGISTRY: dict[str, dict[str, ToolConfig]] = {
    "web_search": {
        "xai": ToolConfig(
            provider="xai",
            handler=xai_web_search,
            cost_per_call=0.005  # 예상 비용
        ),
        "tavily": ToolConfig(
            provider="tavily",
            handler=tavily_search,
            fallback="xai",
            cost_per_call=0.001
        )
    },
    "x_search": {
        "xai": ToolConfig(
            provider="xai",
            handler=xai_x_search,
            # fallback 없음 - Grok만 지원
        )
    },
    "translate": {
        "gemini": ToolConfig(
            provider="gemini",
            handler=gemini_translate,
            cost_per_call=0.0  # 무료
        ),
        "gpt": ToolConfig(
            provider="openai",
            handler=gpt_translate,
            fallback="gemini",
            cost_per_call=0.002
        )
    },
    "summarize": {
        "gemini": ToolConfig(
            provider="gemini",
            handler=gemini_summarize,
            cost_per_call=0.0
        )
    },
    "save_message": {
        "internal": ToolConfig(
            provider="internal",
            handler=db_save_message,
            cost_per_call=0.0
        )
    }
}

async def execute_tool(action: str, params: dict, preferred_provider: str = None):
    """도구 실행 (fallback 지원)"""
    providers = TOOL_REGISTRY.get(action, {})

    # 선호 provider 또는 첫 번째 provider 선택
    provider_key = preferred_provider or next(iter(providers))
    config = providers.get(provider_key)

    try:
        return await config.handler(params)
    except Exception as e:
        if config.fallback:
            fallback_config = providers.get(config.fallback)
            return await fallback_config.handler(params)
        raise
```

### Phase 3: 비용 최적화

```python
# src/cost_optimizer.py (신규)

class CostOptimizer:
    """작업별 최적 provider 선택"""

    def __init__(self):
        self.usage_stats = {}  # 사용량 추적
        self.budget_limit = float(os.getenv("MONTHLY_BUDGET", "5.0"))

    def select_provider(self, action: str) -> str:
        """비용/성능 기준 최적 provider 선택"""
        providers = TOOL_REGISTRY.get(action, {})

        # 무료 provider 우선
        for name, config in providers.items():
            if config.cost_per_call == 0:
                return name

        # 예산 초과 시 저렴한 것 선택
        if self._is_over_budget():
            return min(providers.items(), key=lambda x: x[1].cost_per_call)[0]

        # 기본: 첫 번째 provider
        return next(iter(providers))

    def _is_over_budget(self) -> bool:
        total_cost = sum(self.usage_stats.values())
        return total_cost > self.budget_limit * 0.8  # 80% 도달 시 경고
```

---

## 파일 구조 변경

### 현재

```
src/
├── bot.py           # 텔레그램 핸들러 + 의도 처리
├── agent.py         # 의도 분류 + LangChain Agent
├── database.py      # SQLite
└── tools/
    └── xai_tools.py # Grok 검색 도구
```

### 개선 후

```
src/
├── bot.py           # 텔레그램 핸들러 (단순화)
├── intent.py        # 의도 분류 (단순/복합 구분)
├── planner.py       # Task Planner (복합 작업 분해)
├── executor.py      # Task Executor (단계별 실행)
├── registry.py      # Tool Registry (AI-agnostic)
├── optimizer.py     # Cost Optimizer
├── database.py      # SQLite
└── tools/
    ├── __init__.py
    ├── search.py    # 검색 도구 (web, x)
    ├── llm.py       # LLM 도구 (번역, 요약, 분석)
    └── internal.py  # 내부 도구 (저장, 삭제 등)
```

---

## 구현 로드맵

### Phase 1: Task Planner ✅ 완료

| 작업 | 상태 |
|------|------|
| intent.py 분리 (단순/복합 구분) | ✅ |
| planner.py 구현 | ✅ |
| executor.py 기본 구현 | ✅ |
| bot.py 리팩토링 | ✅ |

**결과**: 복합 의도 ("검색해서 번역 후 저장") 처리 가능

### Phase 2: Tool Registry ✅ 완료

| 작업 | 상태 |
|------|------|
| registry.py 구현 | ✅ |
| 기존 도구 마이그레이션 | ✅ |
| fallback 로직 구현 | ✅ |
| executor.py Registry 연동 | ✅ |

**결과**: Provider 추상화, Fallback 지원, 비용 추적 기반 마련

### Phase 3: 비용 최적화 (향후)

| 작업 | 상태 |
|------|------|
| optimizer.py 구현 | 미정 |
| 사용량 추적 | ✅ (Registry에 기본 구현) |
| 예산 알림 | 미정 |

**목표**: 월 비용 예측 및 제어

---

## 기대 효과

### 기능 확장성

| 항목 | 현재 | 개선 후 |
|------|------|---------|
| 새 도구 추가 | agent.py 수정 + 프롬프트 수정 | registry에 등록만 |
| 복합 작업 | 불가 | Planner가 자동 분해 |
| 의도 분류 복잡도 | 7개 → 계속 증가 | 2개 (단순/복합) |

### 비용 최적화

| 항목 | 현재 | 개선 후 |
|------|------|---------|
| 단순 저장 | Grok 불필요하게 호출 가능 | 내부 함수로 직접 처리 |
| 번역/요약 | Grok 사용 | Gemini 무료 사용 |
| 검색 | Grok만 가능 | fallback으로 저렴한 대안 |

### 유지보수성

| 항목 | 현재 | 개선 후 |
|------|------|---------|
| AI 교체 | 전체 코드 수정 | registry 설정만 변경 |
| 장애 대응 | 서비스 중단 | fallback 자동 전환 |
| 디버깅 | Agent 블랙박스 | 단계별 로그 확인 |

---

## 리스크 및 대응

### 1. Task Planner 정확도

**리스크**: Planner가 잘못된 단계를 생성할 수 있음

**대응**:
- 구조화된 출력 (JSON schema 강제)
- 유효하지 않은 action 검증
- 실패 시 원본 메시지로 Agent 폴백

### 2. 컨텍스트 손실

**리스크**: 단계 간 정보 전달 시 중요 정보 누락

**대응**:
- context_chain에 전체 히스토리 유지
- 각 단계에 필요한 컨텍스트 명시적 전달

### 3. 복잡도 증가

**리스크**: 코드 구조가 복잡해져 이해하기 어려움

**대응**:
- 명확한 모듈 분리
- 각 모듈 단일 책임
- 충분한 문서화

---

## 결론

현재 아키텍처의 핵심 문제는 **Grok 의존성**과 **복합 의도 처리 불가**입니다.

제안하는 개선안은:
1. **Task Planner**로 복합 작업을 단계별로 분해
2. **Tool Registry**로 AI provider를 추상화하여 교체 용이하게
3. **Cost Optimizer**로 작업별 최적 provider 자동 선택

이를 통해 기능 확장성과 비용 최적화 두 가지 목표를 달성할 수 있습니다.
