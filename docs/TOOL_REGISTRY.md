# Tool Registry 도입 배경 및 효과

## 1. 현재 구조

### 코드 구조
```
src/
├── executor.py      # 작업 실행 (하드코딩된 도구 호출)
└── tools/
    ├── xai_tools.py # Grok API 직접 호출
    └── llm.py       # Gemini API 직접 호출
```

### 도구 호출 방식 (executor.py)
```python
async def _execute_action(self, action: str, params: dict) -> str:
    if action == "web_search":
        return await search_web(query=params.get("query"))  # xai_tools.py 직접 호출
    elif action == "x_search":
        return await search_x(query=params.get("query"))    # xai_tools.py 직접 호출
    elif action == "translate":
        return await translate(text=params.get("text"))     # llm.py 직접 호출
    elif action == "summarize":
        return await summarize(text=params.get("text"))     # llm.py 직접 호출
    # ... if-elif 계속 증가
```

### 도구 구현 방식 (xai_tools.py)
```python
def _call_xai_with_tool(query: str, tool_name: str) -> str:
    # Grok API 직접 호출
    response = xai_client.responses.create(
        model="grok-4-1-fast-reasoning",  # 모델 하드코딩
        tools=[{"type": tool_name}],
        input=query,
    )
    return extract_text(response)
```

---

## 2. 문제점

### 문제 1: Provider 교체 어려움

**시나리오**: Grok 대신 Tavily를 웹 검색에 사용하고 싶음

**현재 필요한 작업**:
1. `xai_tools.py`의 `search_web()` 함수 전체 수정
2. `executor.py`의 import 경로 수정
3. 테스트 및 배포

**문제**: 코드 여러 곳을 수정해야 하고, 롤백도 어려움

---

### 문제 2: Fallback 불가

**시나리오**: Grok API 장애 발생

```
사용자: "비트코인 뉴스 검색해줘"
    ↓
search_web() 호출
    ↓
Grok API 오류 (503 Service Unavailable)
    ↓
❌ "검색 실패: API 오류"
```

**현재 상태**: 대체 Provider가 없어 서비스 중단

---

### 문제 3: 비용 추적 불가

**현재 상황**:
- 월말에 xAI 청구서 확인 → "예상보다 많이 나왔네?"
- 어떤 기능이 비용을 많이 썼는지 알 수 없음
- 비용 절감 포인트 파악 불가

**데이터 부재**:
- 도구별 호출 횟수: 모름
- 도구별 비용: 모름
- 사용자별 사용량: 모름

---

### 문제 4: 테스트 어려움

**현재 테스트 방식**:
```python
# 실제 API 호출 필요
async def test_web_search():
    result = await search_web("테스트 쿼리")  # 실제 Grok API 호출
    assert "결과" in result
```

**문제점**:
- 테스트마다 API 비용 발생
- 네트워크 의존으로 테스트 불안정
- CI/CD 파이프라인에서 API 키 관리 필요

---

### 문제 5: 확장성 한계

**새 도구 추가 시 필요한 작업**:

1. `tools/` 디렉토리에 새 파일 생성
2. `executor.py`에 elif 분기 추가
3. `planner.py` 프롬프트에 새 도구 설명 추가
4. import 구문 추가

**문제**: 도구 추가할 때마다 4개 파일 수정 필요

---

## 3. 개선: Tool Registry 도입

### 새로운 구조
```
src/
├── registry.py      # 도구 등록 및 관리 (신규)
├── executor.py      # 작업 실행 (Registry 사용)
└── tools/
    ├── xai_tools.py # Grok Provider
    ├── llm.py       # Gemini Provider
    └── tavily.py    # Tavily Provider (향후)
```

### Registry 핵심 개념
```python
@dataclass
class CostConfig:
    input_cost_per_1m: float = 0.0    # 입력 토큰 100만개당 비용 (USD)
    output_cost_per_1m: float = 0.0   # 출력 토큰 100만개당 비용 (USD)
    cost_per_call: float = 0.0        # 호출당 고정 비용 (검색 도구 등)

@dataclass
class ToolConfig:
    name: str              # 도구 이름 (web_search, translate 등)
    provider: str          # Provider 이름 (xai, gemini, tavily)
    handler: Callable      # 실행 함수
    cost: CostConfig       # 비용 설정 (토큰 기반)
    fallback: str = None   # 장애 시 대체 Provider

# 도구 등록 예시
registry.register(
    action="web_search",
    provider="xai",
    handler=search_web,
    input_cost_per_1m=0.20,   # Grok 입력 토큰
    output_cost_per_1m=0.50,  # Grok 출력 토큰
    cost_per_call=0.0,        # 현재 프로모션 무료
    fallback="tavily"
)
```

### 도구 실행 방식 변경
```python
# Before (executor.py)
if action == "web_search":
    return await search_web(query)

# After (executor.py)
return await registry.execute("web_search", params)  # Registry가 알아서 처리
```

---

## 4. 개선 효과

### 효과 1: Provider 교체 1줄로 해결

**시나리오**: Grok → Tavily 교체

```python
# Before: 코드 수정 필요
# After: 설정만 변경
registry.set_default_provider("web_search", "tavily")
```

또는 환경변수로:
```bash
WEB_SEARCH_PROVIDER=tavily  # .env 파일
```

---

### 효과 2: 자동 Fallback

```python
TOOL_REGISTRY = {
    "web_search": {
        "xai": ToolConfig(handler=xai_search, fallback="tavily"),
        "tavily": ToolConfig(handler=tavily_search),
    }
}

# 실행 시
result = await registry.execute("web_search", {"query": "비트코인"})
# 1. xai 시도
# 2. xai 실패 시 → tavily 자동 전환
# 3. 사용자는 장애 인지 못함
```

**결과**:
```
사용자: "비트코인 뉴스 검색해줘"
    ↓
search_web() 호출 (xai)
    ↓
Grok API 오류
    ↓ (자동 전환)
search_web() 호출 (tavily)
    ↓
✅ 검색 결과 반환
```

---

### 효과 3: 비용 추적 가능 (토큰 기반)

```python
class ToolRegistry:
    async def execute(self, action: str, params: dict):
        result = await config.handler(**params)

        # 토큰 수 추정 및 비용 계산
        input_tokens = self._estimate_tokens(str(params))
        output_tokens = self._estimate_tokens(str(result))
        cost = config.cost.calculate(input_tokens, output_tokens)

        # 사용량 기록
        self._log_usage(action, provider, input_tokens, output_tokens, cost, success=True)

        return result

    def get_usage_report(self) -> dict:
        return {
            "by_action": {
                "web_search": {"calls": 142, "input_tokens": 5000, "output_tokens": 20000, "cost": 0.011},
                "translate": {"calls": 234, "input_tokens": 10000, "output_tokens": 8000, "cost": 0.0},
            },
            "by_provider": {
                "xai": {"calls": 231, "cost": 0.015},
                "gemini": {"calls": 390, "cost": 0.0},
            },
            "total_tokens": {"input": 15000, "output": 28000},
            "total_cost": 0.015
        }
```

**월간 리포트 예시**:
```
📊 이번 달 사용량 리포트

| 도구 | 호출 수 | 입력 토큰 | 출력 토큰 | 비용 |
|------|---------|----------|----------|------|
| web_search | 142회 | 5,000 | 20,000 | $0.011 |
| x_search | 89회 | 3,000 | 12,000 | $0.007 |
| translate | 234회 | 10,000 | 8,000 | $0.00 |
| summarize | 156회 | 15,000 | 5,000 | $0.00 |
| **합계** | **621회** | **33,000** | **45,000** | **$0.018** |
```

---

### 효과 4: Mock Provider로 무료 테스트

```python
# tests/test_executor.py

class MockSearchProvider:
    async def search(self, query: str) -> str:
        return f"Mock 검색 결과: {query}"

def test_web_search():
    # Mock Provider 등록
    registry.register("web_search", "mock", MockSearchProvider())
    registry.set_default_provider("web_search", "mock")

    # 테스트 실행 (API 호출 없음)
    result = await registry.execute("web_search", {"query": "테스트"})
    assert "Mock" in result
```

**장점**:
- API 비용 0원
- 네트워크 독립적
- CI/CD에서 안정적 실행

---

### 효과 5: 도구 추가 1곳만 수정

**새 도구 (예: 이미지 생성) 추가 시**:

```python
# tools/image.py (신규)
async def generate_image(prompt: str) -> str:
    # DALL-E 또는 Stable Diffusion 호출
    return image_url

# registry.py에 등록
TOOL_REGISTRY["image_generate"] = {
    "openai": ToolConfig(handler=generate_image, cost=0.02)
}
```

**끝!** executor.py, planner.py 수정 불필요

---

## 5. 구현 범위

### 이번 작업에서 구현할 것
1. `src/registry.py` 생성
   - ToolConfig 데이터클래스
   - ToolRegistry 클래스 (execute, fallback)
   - 기본 도구 등록 (web_search, x_search, translate, summarize, analyze, save_message)

2. `src/executor.py` 수정
   - if-elif 분기 → Registry.execute() 호출로 변경

3. 기존 도구 유지
   - `xai_tools.py`, `llm.py`는 그대로 사용
   - Registry에서 이들을 handler로 등록

### 향후 확장 가능
- Tavily 검색 Provider 추가
- 비용 추적 및 리포트 기능
- 환경변수로 기본 Provider 설정
- Provider별 rate limiting

---

## 6. 비교 요약

| 항목 | 현재 | 개선 후 |
|------|------|---------|
| Provider 교체 | 코드 수정 필요 | 설정 1줄 |
| API 장애 대응 | 서비스 중단 | 자동 Fallback |
| 비용 파악 | 불가 | 도구별 추적 |
| 테스트 | 실제 API 호출 | Mock Provider |
| 도구 추가 | 4개 파일 수정 | registry.py만 |
| 코드 복잡도 | if-elif 늘어남 | Registry가 관리 |

---

## 7. 결론

Tool Registry 도입은 **코드 품질 개선**에 초점을 맞춘 리팩토링입니다.

당장 새로운 기능이 추가되는 것은 아니지만:
- 향후 Provider 추가/교체가 쉬워지고
- API 장애에 대한 복원력이 생기며
- 비용 최적화의 기반이 마련됩니다

"지금 잘 돌아가니까 나중에 하자"가 아니라, **확장을 앞두고 기반을 다지는 작업**입니다.
