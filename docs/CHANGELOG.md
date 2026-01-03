# 개선 내역 (Changelog)

프로젝트 개발 과정에서 발견된 문제들과 해결 과정을 정리한 문서입니다.

---

## 1. AI 기반 의도 분류 시스템 도입

### 문제
- 키워드 매칭 방식(`detect_command_intent()`)으로 사용자 의도를 파악
- "저장해줘", "저장해", "기억해줘" 등 다양한 표현을 모두 하드코딩해야 함
- 새로운 표현이 추가될 때마다 코드 수정 필요
- 한국어의 다양한 어미 변화에 대응하기 어려움

### 문제 파악
```python
# 기존 방식: 키워드 매칭
if any(keyword in message for keyword in ["저장해", "기억해", "메모해"]):
    return "save_message"
```
- 유연성 부족: "이거 좀 저장해줄래?" 같은 표현 인식 불가
- 유지보수 비용 증가: 표현마다 키워드 추가 필요

### 해결
**2단계 AI 처리 구조 도입**

```
사용자 메시지
    ↓
[1단계] 의도 분류 (Gemini 2.0 Flash - 무료)
    ↓
┌─────────────────────────────────────────┐
│ save_message → DB 저장                  │
│ list_messages → 메시지 목록 조회         │
│ delete_message → 메시지 삭제            │
│ clear_messages → 전체 삭제              │
│ help → 도움말 표시                      │
│ question → [2단계] AI Agent 호출        │
└─────────────────────────────────────────┘
    ↓ (question인 경우만)
[2단계] AI Agent (Grok - 유료)
```

- Gemini 2.0 Flash (무료)로 의도 분류
- 7가지 의도: `save_message`, `list_messages`, `list_all`, `clear_messages`, `delete_message`, `help`, `question`
- 단순 명령은 Agent 호출 없이 직접 처리

### 성과
- 자연어 인식률 향상: 다양한 표현을 AI가 자동 이해
- 비용 절감: 단순 명령은 무료 모델로 처리, 복잡한 질문만 유료 모델 사용
- 유지보수 간소화: 새로운 표현 추가 시 코드 수정 불필요

---

## 2. 포워딩 메시지 컨텍스트 인식 개선

### 문제
- 사용자가 메시지를 포워딩한 후 "이거 분석해줘"라고 질문
- AI가 "이거"가 무엇을 가리키는지 인식하지 못함
- "방금 거", "위에 거" 등 지시어 해석 실패

### 문제 파악
```python
# 기존: 메시지를 단순 나열
context = "\n".join([msg["content"] for msg in messages])
```
- 모든 메시지가 동등하게 취급됨
- 어떤 것이 "가장 최근" 메시지인지 구분 불가

### 해결
**가장 최근 메시지에 특별 레이블 추가**

```python
# 개선: 최근 메시지 명시
if idx == total_count - 1:
    context_parts.append(
        f"[가장 최근 저장된 메시지] {source} ({time_str})\n{msg['content']}"
    )
```

**시스템 프롬프트에 지시어 해석 규칙 추가**

```
[중요: 대명사 및 지시어 해석]
사용자가 다음과 같은 표현을 사용하면, [가장 최근 저장된 메시지]를 참조하세요:
- "이거", "이것", "이 메시지", "이 내용"
- "방금 거", "방금 것", "방금 보낸 거"
- "위에 거", "위에 것", "위 메시지"
```

### 성과
- "이거 분석해줘" → 가장 최근 포워딩된 메시지 분석
- "방금 거 요약해줘" → 정확한 컨텍스트 참조
- 자연스러운 대화 흐름 지원

---

## 3. 메시지 관리 명령어 체계화

### 문제
- 저장된 메시지를 관리할 방법이 부족
- 전체 목록 조회, 개별 삭제 기능 없음
- 메시지가 많아지면 관리 불가

### 문제 파악
- `/list`만 존재 (최근 10개만 표시)
- 삭제는 `/clear`로 전체 삭제만 가능
- 특정 메시지만 삭제하거나 전체 목록을 볼 수 없음

### 해결
**새로운 명령어 추가**

| 명령어 | 설명 |
|--------|------|
| `/list` | 최근 10개 메시지 (기존) |
| `/listall` | 전체 메시지 목록 (신규) |
| `/delete <번호>` | 특정 메시지 삭제 (신규) |

**자연어로도 동일 기능 사용 가능**

| 자연어 | 동작 |
|--------|------|
| "저장된 거 보여줘" | `/list` |
| "전체 목록" | `/listall` |
| "1번 삭제해줘" | `/delete 1` |

### 성과
- 세밀한 메시지 관리 가능
- 명령어와 자연어 모두 지원
- 텔레그램 메시지 길이 제한(4096자) 대응

---

## 4. 도구 사용 상태 피드백

### 문제
- AI가 웹 검색이나 X 검색을 수행할 때 사용자에게 아무 피드백 없음
- "생각 중..." 메시지 후 긴 침묵
- 사용자가 봇이 작동 중인지 알 수 없음

### 문제 파악
- Agent가 도구를 호출해도 사용자에게 알림 없음
- 검색에 수 초가 걸리면 사용자 경험 저하

### 해결
**LangChain 콜백 핸들러로 실시간 상태 전송**

```python
class ToolStatusCallback(AsyncCallbackHandler):
    async def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get("name")
        if tool_name == "web_search":
            await self.status_callback("🌐 웹 검색 중...")
        elif tool_name == "x_search":
            await self.status_callback("🐦 X 검색 중...")
```

### 성과
- 실시간 상태 피드백: "🌐 웹 검색 중... ('비트코인 뉴스')"
- 사용자가 진행 상황 파악 가능
- 향상된 사용자 경험

---

## 5. 검색 API 에러 핸들링

### 문제
- xAI 검색 API 호출 실패 시 일반적인 에러 메시지만 표시
- 사용자가 무엇이 잘못되었는지 알 수 없음
- 디버깅 어려움

### 문제 파악
```python
# 기존: 일반 Exception
except Exception as e:
    return f"오류: {e}"
```
- API 응답 코드, 에러 메시지 등 상세 정보 손실

### 해결
**커스텀 예외 클래스와 상세 에러 처리**

```python
class SearchError(Exception):
    """검색 도구 관련 예외"""
    pass

# API 응답 확인
if response.status_code != 200:
    raise SearchError(
        f"API 오류 ({response.status_code}): {response.text}"
    )
```

### 성과
- 상세한 에러 메시지로 빠른 디버깅
- 사용자에게 명확한 실패 원인 전달
- API 할당량 초과 등 특정 에러 식별 가능

---

## 기술 스택 변화

| 변경 전 | 변경 후 | 이유 |
|---------|---------|------|
| 키워드 매칭 | Gemini 2.0 Flash | 자연어 유연성 |
| 단일 모델 | 2단계 모델 | 비용 최적화 |
| 기본 에러 처리 | 커스텀 예외 | 디버깅 용이성 |

---

## 6. 텔레그램 메시지 인라인 업데이트

### 문제
- AI 응답 시 새 메시지가 계속 생성되어 채팅창이 지저분해짐
- "생각 중..." 메시지와 최종 응답이 별도 메시지로 표시

### 문제 파악
```python
# 기존: 새 메시지 생성
await update.message.reply_text("생각 중...")
await update.message.reply_text(response)  # 새 메시지 추가
```
- 매번 새 메시지가 생성되어 채팅 히스토리가 길어짐

### 해결
**`edit_text()`를 사용한 인라인 메시지 업데이트**

```python
# 개선: 같은 메시지 내용 업데이트
status_msg = await update.message.reply_text("🤔 생각 중...")
# ... 처리 후 ...
await status_msg.edit_text(response)  # 같은 메시지 수정
```

### 성과
- 하나의 메시지에서 상태가 변경됨
- 깔끔한 채팅 히스토리 유지
- 사용자 경험 향상

---

## 7. 도구 상태 스택 표시

### 문제
- 여러 검색 도구가 호출될 때 마지막 상태만 표시
- 이전 검색 상태가 덮어씌워짐

### 문제 파악
```python
# 기존: 단일 상태만 표시
message = f"🌐 웹 검색 중... ('{query}')"
await self.status_callback(message)  # 이전 상태 덮어씌움
```

### 해결
**상태 메시지를 스택으로 쌓아 누적 표시**

```python
class ToolStatusCallback(AsyncCallbackHandler):
    def __init__(self, ...):
        self.status_lines = []  # 상태 메시지 스택

    async def on_tool_start(self, ...):
        status_line = f"🌐 웹 검색 중... ('{query}')"
        self.status_lines.append(status_line)  # 스택에 추가

        # 전체 상태를 줄바꿈으로 조합하여 표시
        await self.status_callback("\n".join(self.status_lines))
```

### 성과
```
🌐 웹 검색 중... ('서울 날씨')
🌐 웹 검색 중... ('인디애나 날씨')
```
- 모든 진행 상황을 한눈에 확인 가능
- 최종 응답으로 한 번에 대체됨

---

## 8. 도구 입력 파싱 개선

### 문제
- 도구 호출 시 검색어가 `{'query': '서울 날씨'}` 형태로 표시됨
- JSON과 Python dict repr 형태가 혼재

### 문제 파악
```python
# LangChain이 전달하는 input_str 형태가 다양함
input_str = "{'query': '서울 날씨'}"  # Python dict repr (작은따옴표)
input_str = '{"query": "서울 날씨"}'  # JSON 문자열 (큰따옴표)
```
- `json.loads()`는 큰따옴표만 인식

### 해결
**JSON과 Python dict repr 모두 파싱**

```python
def _extract_query(self, input_str: str) -> str:
    try:
        # Case 1: JSON 문자열
        parsed = json.loads(input_str)
        if isinstance(parsed, dict) and "query" in parsed:
            return parsed["query"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Case 2: Python dict repr
    try:
        parsed = ast.literal_eval(input_str)
        if isinstance(parsed, dict) and "query" in parsed:
            return parsed["query"]
    except (ValueError, SyntaxError):
        pass

    return input_str
```

### 성과
- `🌐 웹 검색 중... ('서울 날씨')` 형태로 깔끔하게 표시
- 다양한 입력 형태 대응

---

## 기술 스택 변화

| 변경 전 | 변경 후 | 이유 |
|---------|---------|------|
| 키워드 매칭 | Gemini 2.0 Flash | 자연어 유연성 |
| 단일 모델 | 2단계 모델 | 비용 최적화 |
| 기본 에러 처리 | 커스텀 예외 | 디버깅 용이성 |
| 새 메시지 생성 | edit_text() | UX 개선 |
| 단일 상태 표시 | 스택 기반 표시 | 진행 상황 가시성 |

---

## 9. 복합 의도 처리 시스템 (Task Planner)

### 문제
기존 의도 분류 시스템은 **단일 의도**만 파악하며, 복합적인 작업 요청을 처리하지 못함.

### 문제 상황
```
사용자: "X에서 @elon_musk 의 가장 최신 글을 검색한 다음,
        이걸 한글로 번역해서 저장해줘."

기대 동작:
1. X 검색 (@elon_musk 최신 글)
2. 한글 번역
3. DB 저장

실제 동작 (이전):
- 의도 분류: "save_message" (저장해줘 키워드만 인식)
- 결과: ✅ 메시지가 저장되었습니다.
        저장된 내용: X에서 @elon_musk 의 가장 최신 글을 검색한 다음...
```

### 해결
**Task Planner + Executor 구조 도입**

```
사용자 메시지
    ↓
[1단계] 의도 분류 (Gemini 2.0 Flash)
    ↓
┌─────────────────────────────────────────┐
│ 단순 의도 (7개) → 직접 처리 (기존)       │
│ 복합 의도 (COMPLEX) → Task Planner      │
└─────────────────────────────────────────┘
    ↓ (복합 의도인 경우)
[2단계] Task Planner - 작업 분해 (Gemini 2.0 Flash)
    ↓
[3단계] Task Executor - 순차 실행
```

**새로 추가된 의도: `COMPLEX`**
```python
class UserIntent(str, Enum):
    SAVE_MESSAGE = "save_message"
    LIST_MESSAGES = "list_messages"
    # ... 기존 의도들 ...
    QUESTION = "question"      # 단순 질문 (AI Agent)
    COMPLEX = "complex"        # 복합 작업 (Task Planner)
```

**Task Planner 출력 형식**
```json
{
    "steps": [
        {"action": "x_search", "params": {"query": "@elon_musk"}, "output_key": "result1"},
        {"action": "translate", "params": {"text": "$result1", "to": "ko"}, "output_key": "result2"},
        {"action": "save_message", "params": {"content": "$result2"}}
    ],
    "summary": "X에서 검색 후 번역하여 저장"
}
```

**사용 가능한 작업 (Actions)**
| Action | 설명 | 파라미터 |
|--------|------|----------|
| `web_search` | 웹 검색 | `query` |
| `x_search` | X(트위터) 검색 | `query` |
| `translate` | 텍스트 번역 | `text`, `to` (ko/en/ja/zh) |
| `summarize` | 텍스트 요약 | `text` |
| `analyze` | 텍스트 분석 | `text`, `question` (선택) |
| `save_message` | DB 저장 | `content` |

**Context Chain ($변수 참조)**
- 이전 단계의 결과를 다음 단계에서 참조 가능
- `$output_key` 형태로 이전 결과 사용
- 예: `{"text": "$result1"}` → result1의 값으로 치환

### 구현 파일

| 파일 | 역할 |
|------|------|
| `src/agent.py` | `COMPLEX` 의도 추가, 프롬프트 수정 |
| `src/planner.py` | Task Planner (작업 분해) |
| `src/executor.py` | Task Executor (순차 실행) |
| `src/tools/llm.py` | LLM 도구 (번역, 요약, 분석) |

### 성과
```
사용자: "X에서 @elon_musk 검색해서 한글로 번역 후 저장해줘"

실제 동작 (개선 후):
🤔 작업 계획 중...
🐦 X 검색 중... ('@elon_musk')
🌍 번역 중...
💾 저장 중...
✅ X에서 검색 후 번역하여 저장

(검색 결과가 한글로 번역되어 DB에 저장됨)
```

- 복합 작업 요청 자동 처리
- 실시간 진행 상황 표시
- 단계별 결과 체이닝

---

## [문제] Task Planner 세부 조건 누락

### 문제
Task Planner가 사용자 요청의 세부 조건(개수, 언어 등)을 제대로 반영하지 못함.

### 문제 상황 예시
```
사용자: "X에서 @elon_musk 의 가장 최신 글 3개를 검색한 다음,
        이걸 요약하고 한글로 번역해서 저장해줘."

Task Planner 출력:
{
    "steps": [
        {"action": "x_search", "params": {"query": "@elon_musk"}, ...},
        {"action": "summarize", "params": {"text": "$search_result"}, ...},
        {"action": "translate", "params": {"text": "$summarized", "to": "ko"}, ...},
        {"action": "save_message", "params": {"content": "$translated"}}
    ]
}

문제점:
1. 사용자가 "3개"를 요청했으나, x_search에 count 파라미터가 없음
   → 사용자 의도와 무관하게, 실제로는 5개 게시물이 반환됨

2. summarize가 이미 한국어로 요약을 반환
   → translate 단계가 "한국어 → 한국어" 불필요한 번역 수행
```

### 실제 로그 분석
```
[Step 2 입력] summarize with {'text': '**Elon Musk (@elonmusk)**...'}
[Step 2 출력] '2026년 1월 2일 기준, Elon Musk는 2억 3천만 명...' (172자)
             ↑ 이미 한국어로 요약됨

[Step 3 입력] translate with {'text': '2026년 1월 2일 기준...', 'to': 'ko'}
[Step 3 출력] '2026년 1월 2일 현재, 일론 머스크는...' (203자)
             ↑ 한국어 → 한국어 번역 (불필요)
```

### 근본 원인

1. **검색 도구의 파라미터 제한**
   - `x_search`가 `query`만 받고 `count` 파라미터를 지원하지 않음
   - Task Planner가 개수 조건을 반영할 방법이 없음

2. **LLM 도구의 언어 비명시**
   - `summarize()`가 출력 언어를 지정하지 않음
   - Gemini가 입력 언어와 무관하게 한국어로 요약하는 경향

3. **Task Planner 프롬프트 한계**
   - 사용자 요청의 세부 조건을 파라미터로 매핑하는 규칙 부족

### 필요한 개선 방향

**Option 1: 검색 도구에 count 파라미터 추가**
```python
# xai_tools.py
async def search_x(query: str, count: int = 5) -> str:
    prompt = f"Search X for: {query}. Return {count} most recent posts."

# planner.py 프롬프트 수정
- x_search: X 검색 (params: query, count - 기본값 5)
```

**Option 2: LLM 도구에 언어 파라미터 추가**
```python
# llm.py
async def summarize(text: str, language: str = "same") -> str:
    # language="same": 입력과 동일한 언어로 출력
    # language="ko": 한국어로 요약
    # language="en": 영어로 요약
```

**Option 3: Task Planner 프롬프트 개선**
```
[파라미터 매핑 규칙]
- 사용자가 "N개"를 요청하면 count: N 파라미터 추가
- "한글로", "영어로" 요청 시 to 파라미터에 반영
- 요약 후 번역이 필요한 경우, summarize의 언어와 translate의 to가 다른지 확인
```

### 해결

**3계층 동기화 원칙을 적용하여 모든 계층을 수정:**

#### Layer 3: 실행 코드 수정

**xai_tools.py** - count 파라미터 추가
```python
def _call_xai_with_tool(query: str, tool_name: str, count: int = None) -> str:
    if count is not None and count > 0:
        query = f"{query} (Return exactly {count} most recent results)"
    ...

async def search_x(query: str, count: int = None) -> str:
    return _call_xai_with_tool(query, "x_search", count)
```

**llm.py** - language 파라미터 추가
```python
async def summarize(text: str, language: str = "same") -> str:
    language_map = {
        "same": "입력 텍스트와 동일한 언어로",
        "ko": "한국어로",
        "en": "영어로",
        ...
    }
    lang_instruction = language_map.get(language, "입력 텍스트와 동일한 언어로")
    prompt = f"...{lang_instruction} 요약문만 출력하세요."
```

#### Layer 2: Executor 수정

**executor.py** - 새 파라미터 전달
```python
elif action == "x_search":
    return await search_x(
        query=params.get("query", ""),
        count=params.get("count")  # 추가
    )

elif action == "summarize":
    return await summarize(
        text=params.get("text", ""),
        language=params.get("language", "same")  # 추가
    )
```

#### Layer 1: 프롬프트 수정

**planner.py** - 파라미터 설명 및 규칙 추가
```python
TASK_PLANNER_PROMPT = """
[사용 가능한 작업]
- x_search: X(트위터)에서 검색
  params: query (검색어), count (결과 개수, 선택)
- summarize: 텍스트 요약
  params: text (요약할 텍스트), language (출력 언어: same/ko/en/ja/zh, 선택)

[규칙]
...
6. 사용자가 지정한 조건은 반드시 params에 반영:
   - "3개", "5개" 등 개수 → count 파라미터
   - "한글로", "영어로" 등 언어 → language 또는 to 파라미터
7. 요약+번역이 필요하면 summarize의 language로 처리 (별도 translate 불필요)
8. 요약 없이 번역만 필요하면 translate 사용
"""
```

### 성과
```
사용자: "X에서 @elon_musk 의 가장 최신 글 3개를 검색한 다음,
        이걸 요약하고 한글로 번역해서 저장해줘."

개선 전 Task Planner 출력:
{
    "steps": [
        {"action": "x_search", "params": {"query": "@elon_musk"}},
        {"action": "summarize", "params": {"text": "$search_result"}},
        {"action": "translate", "params": {"text": "$summarized", "to": "ko"}},
        {"action": "save_message", "params": {"content": "$translated"}}
    ]
}
→ count 누락, 불필요한 translate 단계

개선 후 Task Planner 출력:
{
    "steps": [
        {"action": "x_search", "params": {"query": "@elon_musk", "count": 3}},
        {"action": "summarize", "params": {"text": "$search_result", "language": "ko"}},
        {"action": "save_message", "params": {"content": "$summarized"}}
    ]
}
→ count 반영, summarize에서 직접 한국어 출력 (translate 불필요)
```

- 사용자 조건이 파라미터로 정확히 반영됨
- 불필요한 단계 자동 제거 (요약+번역 → summarize(language="ko"))
- 3계층 동기화로 프롬프트-스키마-코드 일치

---

## 교훈: AI 구조화 출력(Structured Output) 설계

위 문제는 **LLM 기반 시스템에서 구조화된 출력을 설계할 때 흔히 발생하는 이슈**입니다.
Function Calling, Tool Use, JSON Mode 등을 사용하는 모든 AI 시스템에 적용되는 교훈을 정리합니다.

### 핵심 원칙: "LLM에게 선택지가 없으면, 선택할 수 없다"

```
사용자 요청: "3개만 검색해줘"
     ↓
프롬프트 스키마: {"action": "search", "params": {"query": "..."}}
     ↓
LLM 출력: {"action": "search", "params": {"query": "..."}}
          ↑ count를 넣을 곳이 없음!
```

LLM이 아무리 "3개"라는 조건을 이해해도, **스키마에 `count` 필드가 없으면 반영할 방법이 없습니다**.

### 3계층 동기화 법칙

AI 구조화 출력 시스템은 3개 계층이 **완벽히 동기화**되어야 합니다:

```
┌─────────────────────────────────────────────────────────────┐
│  [1] 프롬프트 (Prompt)                                       │
│      - 사용 가능한 파라미터 설명                              │
│      - 예: "count: 결과 개수 (선택, 기본값 5)"                │
├─────────────────────────────────────────────────────────────┤
│  [2] 스키마 (Schema)                                         │
│      - JSON/Function 정의                                    │
│      - 예: {"query": str, "count": int}                     │
├─────────────────────────────────────────────────────────────┤
│  [3] 실행 코드 (Implementation)                              │
│      - 실제 함수 시그니처                                     │
│      - 예: def search(query: str, count: int = 5)           │
└─────────────────────────────────────────────────────────────┘
```

**하나라도 불일치하면 문제 발생:**

| 불일치 유형 | 증상 |
|------------|------|
| 프롬프트 ≠ 스키마 | LLM이 파라미터를 알아도 출력 못함 |
| 스키마 ≠ 코드 | JSON 파싱 후 실행 오류 |
| 프롬프트 ≠ 코드 | LLM이 존재하지 않는 기능 호출 |

### 현재 프로젝트의 불일치 사례

**문제 1: count 파라미터**
```
[프롬프트] x_search: X 검색 (params: query)     ← count 설명 없음
[스키마]  {"query": "..."}                      ← count 필드 없음
[코드]    search_x(query: str)                  ← count 파라미터 없음
```

**문제 2: 언어 파라미터**
```
[프롬프트] summarize: 요약 (params: text)       ← language 설명 없음
[스키마]  {"text": "..."}                       ← language 필드 없음
[코드]    summarize(text: str)                  ← 암시적으로 한국어 출력
```

### 올바른 설계 예시

```python
# [1] 프롬프트
"""
[사용 가능한 작업]
- x_search: X(트위터) 검색
  params:
    - query (필수): 검색어
    - count (선택): 결과 개수 (기본값 5, 최대 20)

- summarize: 텍스트 요약
  params:
    - text (필수): 요약할 텍스트
    - language (선택): 출력 언어 (기본값: 입력과 동일)
      - "same": 입력 언어 유지
      - "ko": 한국어
      - "en": 영어
"""

# [2] 스키마 (JSON 예시)
{
    "action": "x_search",
    "params": {
        "query": "@elon_musk",
        "count": 3
    }
}

# [3] 실행 코드
async def search_x(query: str, count: int = 5) -> str:
    prompt = f"Search X for: {query}. Return {count} most recent posts."
    ...
```

### 체크리스트: 구조화 출력 설계 시

- [ ] **파라미터 완전성**: 사용자가 지정할 수 있는 모든 조건이 파라미터로 존재하는가?
- [ ] **프롬프트 명시성**: 각 파라미터의 용도, 타입, 기본값이 프롬프트에 설명되어 있는가?
- [ ] **스키마 일치**: 프롬프트에 설명된 파라미터가 스키마에 모두 정의되어 있는가?
- [ ] **코드 동기화**: 스키마의 필드를 실행 코드가 모두 처리하는가?
- [ ] **암시적 동작 제거**: 코드가 프롬프트에 설명되지 않은 동작을 하지 않는가?

### 적용 범위

이 원칙은 다음 기술에 모두 적용됩니다:
- OpenAI Function Calling
- Anthropic Tool Use
- Google Gemini Function Declarations
- LangChain Tools / Agents
- 커스텀 JSON 출력 파싱

---

## 11. 상세 로깅 시스템 추가

### 배경
AI 시스템의 동작을 이해하고 디버깅하기 위해 각 모듈에 상세한 로깅이 필요했습니다.
- AI의 사고 과정 추적
- 도구 호출 흐름 파악
- 변수 치환 및 파라미터 전달 확인
- 오류 발생 시 원인 분석

### 해결

**6개 파일에 일관된 로깅 패턴 적용:**

| 파일 | 로깅 내용 |
|------|----------|
| agent.py | 의도 분류 과정, LLM 응답, Agent 생성, 도구 호출 상태 |
| planner.py | Task 분해 과정, JSON 파싱, 단계별 계획 출력 |
| executor.py | 단계별 실행, 변수 치환($var → 값), 결과 미리보기 |
| xai_tools.py | xAI API 호출, 쿼리 변환, 응답 추출 |
| llm.py | translate/summarize/analyze 호출, 언어 설정, 결과 |
| bot.py | 메시지 수신, 의도 분류 결과, 처리 경로 |

**로깅 패턴:**
```python
print(f"\n{'='*60}")           # 섹션 시작 (주요 모듈)
print(f"[모듈명] 작업 시작")
print(f"[모듈명] 입력: '{value}'")
print(f"[모듈명] 결과: {len(result)}자")
print(f"{'─'*40}")             # 하위 섹션 구분
print(f"{'='*60}\n")           # 섹션 종료
```

**로그 출력 예시:**
```
##############################################################
[Bot] 새 메시지 수신
[Bot] user_id: 12345
[Bot] 메시지: 'X에서 @elon_musk 검색해서 한글로 요약 후 저장해줘'
##############################################################

============================================================
[의도 분류] 시작
[의도 분류] 입력 메시지: 'X에서 @elon_musk 검색해서...'
[의도 분류] LLM 원본 응답: 'complex'
[의도 분류] 최종 결과: intent=complex, arg=None
============================================================

[Bot] COMPLEX 의도 감지 - Task Planner 경로

============================================================
[Task Planner] 시작
[Task Planner] 분해된 단계: 3개
[Task Planner]   Step 1: x_search
[Task Planner]     params: {"query": "@elon_musk", "count": 3}
[Task Planner]   Step 2: summarize
[Task Planner]   Step 3: save_message
============================================================

============================================================
[Executor] 실행 시작
[Executor] Step 1/3: x_search
────────────────────────────────────────
[xAI Tool] x_search 호출
[xAI Tool] 결과 미리보기: Elon Musk tweeted...
────────────────────────────────────────

[Executor] Step 2/3: summarize
[Executor] 변수 치환: $search_result → (1523자)
────────────────────────────────────────
[LLM summarize] 시작
[LLM summarize] 출력 언어: ko
[LLM summarize] 완료: 245자
────────────────────────────────────────

[Executor] Step 3/3: save_message
[Executor] 변수 치환: $summarized → (245자)
[Executor] DB 저장 완료

────────────────────────────────────────
[Executor] 전체 실행 완료
[Executor] 성공: 3/3
============================================================
```

### 성과
- AI 처리 흐름을 실시간으로 확인 가능
- 디버깅 시간 대폭 단축
- 변수 치환 문제 즉시 발견 가능

---

## 12. Task Planner 변수 참조 버그 수정

### 문제
Task Planner가 `$summarized` 대신 `summarized`로 출력하여 변수 치환이 실패하는 문제 발생.

**문제 로그:**
```
[Executor] Step 3/3: save_message
[Executor] 원본 params: {"content": "summarized"}  ← $ 기호 누락!
[Executor] save_message 호출: content길이=10자
[Executor] DB 저장 완료
저장된 내용: "summarized"  ← 요약 결과가 아닌 문자열 저장
```

### 원인 분석
LLM이 프롬프트의 `$변수명` 규칙을 가끔 무시하고 `$` 기호 없이 출력.

### 해결

**1. 프롬프트 강화 (planner.py)**
```python
[규칙]
1. [중요] 이전 단계 결과를 참조할 때 반드시 "$" 기호를 붙여야 함
   - 올바른 예: "$search_result", "$summarized"
   - 잘못된 예: "search_result", "summarized" ($ 없으면 변수 참조 안됨!)
```

**2. 방어 로직 추가 (executor.py)**
```python
def _resolve_params(self, params: dict) -> dict:
    for key, value in params.items():
        if isinstance(value, str):
            # Case 1: $변수명 형태 (정상)
            if value.startswith("$"):
                var_name = value[1:]
                if var_name in self.context_chain:
                    resolved[key] = self.context_chain[var_name]
                    print(f"[Executor] 변수 치환: ${var_name} → ...")
            # Case 2: $ 없이 변수명만 있는 경우 (LLM 오류 방어)
            elif value in self.context_chain:
                resolved[key] = self.context_chain[value]
                print(f"[Executor] 변수 치환 ($ 누락 보정): {value} → ...")
```

**수정 후 로그:**
```
[Executor] Step 3/3: save_message
[Executor] 원본 params: {"content": "summarized"}
[Executor] 변수 치환 ($ 누락 보정): summarized → (245자)
[Executor] save_message 호출: content길이=245자
[Executor] DB 저장 완료
```

### 교훈
- LLM 출력은 100% 신뢰할 수 없음
- 중요한 문법 규칙은 프롬프트에서 강조 + 코드에서 방어 로직 구현
- **이중 방어 원칙**: 프롬프트 개선 + 코드 폴백

---

## 13. 의도 분류 오류: "N번 메시지" 조회 vs 삭제 혼동

### 문제
"1번 메시지 내용 알려줘"가 `delete_message`로 잘못 분류되는 문제 발생.

### 문제 상황
```
사용자: "1번 메시지 내용 알려줘"

기대 동작: 1번 메시지의 내용을 조회하여 보여줌

실제 동작:
[의도 분류] LLM 원본 응답: 'delete_message'
→ 1번 메시지가 삭제됨!
```

### 원인 분석

**1. `get_message` 의도 부재**
- 현재 8개 의도: save, list, list_all, clear, delete, help, question, complex
- 특정 메시지 조회(get) 의도가 없음
- "N번 메시지"라는 표현이 delete_message로 오분류

**2. 프롬프트 모호성**
```python
# 현재 프롬프트
- delete_message: 특정 메시지 삭제 (예: "1번 삭제해줘", "첫번째 거 지워")
```
- "N번 메시지" 패턴이 delete_message 예시에만 언급됨
- "알려줘", "보여줘" 등 조회 동사가 있어도 숫자 패턴으로 delete_message 매칭

**3. 동사 구분 실패**
| 표현 | 동사 | 기대 의도 | 실제 분류 |
|------|------|-----------|-----------|
| "1번 삭제해줘" | 삭제하다 | delete_message | delete_message ✓ |
| "1번 지워줘" | 지우다 | delete_message | delete_message ✓ |
| "1번 메시지 알려줘" | 알려주다 | get_message | delete_message ✗ |
| "1번 내용 보여줘" | 보여주다 | get_message | delete_message ✗ |

### 해결
`get_message` 의도 추가 및 프롬프트에서 조회/삭제 동사 명확히 구분.

**변경 전 (8개 의도):**
```python
class UserIntent(str, Enum):
    SAVE_MESSAGE = "save_message"
    LIST_MESSAGES = "list_messages"
    LIST_ALL_MESSAGES = "list_all"
    CLEAR_MESSAGES = "clear_messages"
    DELETE_MESSAGE = "delete_message"
    HELP = "help"
    QUESTION = "question"
    COMPLEX = "complex"
```

**변경 후 (9개 의도):**
```python
class UserIntent(str, Enum):
    SAVE_MESSAGE = "save_message"
    LIST_MESSAGES = "list_messages"
    LIST_ALL_MESSAGES = "list_all"
    GET_MESSAGE = "get_message"      # 신규: 특정 메시지 조회
    CLEAR_MESSAGES = "clear_messages"
    DELETE_MESSAGE = "delete_message"
    HELP = "help"
    QUESTION = "question"
    COMPLEX = "complex"
```

**프롬프트 개선:**
```python
INTENT_CLASSIFIER_PROMPT = """
- get_message: 특정 메시지 내용 조회 (예: "1번 메시지 알려줘", "3번 내용 보여줘")
  [조회 동사: 알려줘, 보여줘, 뭐야, 읽어줘]
- delete_message: 특정 메시지 삭제 (예: "1번 삭제해줘", "첫번째 거 지워")
  [삭제 동사: 삭제해줘, 지워줘, 없애줘]

[중요: N번 + 동사 조합 구분]
- "N번 알려줘/보여줘/뭐야" → get_message (조회)
- "N번 삭제해줘/지워줘" → delete_message (삭제)
"""
```

### 교훈
- 의도 분류는 **동사(행위)**를 기준으로 구분해야 함
- 숫자 패턴만으로 의도를 추론하면 오분류 발생
- 새로운 기능(조회)이 필요하면 의도를 추가해야 함

---

## 14. 포괄적 의도 시스템 설계 (Future-Proof)

### 배경
현재 기능뿐 아니라 향후 기능을 고려하여 의도 시스템을 재설계.

### 현재 기능 기반 의도 분류

| 카테고리 | 의도 | 설명 |
|----------|------|------|
| **메시지 CRUD** | save_message | 메시지 저장 |
| | list_messages | 최근 메시지 목록 |
| | list_all | 전체 메시지 목록 |
| | get_message | 특정 메시지 조회 |
| | delete_message | 특정 메시지 삭제 |
| | clear_messages | 전체 메시지 삭제 |
| **검색** | web_search | 웹 검색 (명시적 요청) |
| | x_search | X 검색 (명시적 요청) |
| **AI 처리** | question | 단순 질문/분석 |
| | complex | 복합 작업 |
| **시스템** | help | 도움말 |

### 향후 기능을 고려한 의도 확장

**1. 채널 구독 및 콘텐츠 수집**
```
- subscribe: 채널/키워드 구독 ("@elonmusk 구독해줘", "비트코인 뉴스 알려줘")
- unsubscribe: 구독 취소 ("@elonmusk 구독 취소")
- list_subscriptions: 구독 목록 조회 ("뭐 구독하고 있어?")
- get_feed: 구독 피드 조회 ("오늘 뭐 올라왔어?")
```

**2. 사용자 기억 (Memory)**
```
- remember_preference: 선호도 저장 ("내가 좋아하는 색은 파란색이야")
- recall_preference: 선호도 조회 ("내가 뭐 좋아한다고 했지?")
- forget_preference: 선호도 삭제 ("내 선호도 지워줘")
```

**3. 페르소나 (Persona)**
```
- set_persona: 페르소나 설정 ("피터 린치처럼 대답해줘")
- get_persona: 현재 페르소나 확인 ("지금 어떤 페르소나야?")
- reset_persona: 기본 페르소나로 복귀 ("원래대로 돌아가줘")
```

**4. 외부 서비스 연동**
```
- export_to_notion: 노션 내보내기 ("이거 노션에 저장해줘")
- sync_calendar: 캘린더 동기화 ("내일 일정 뭐야?")
```

### 설계 원칙

**1. 동사 기반 분류**
- 조회: 알려줘, 보여줘, 뭐야 → get_* 계열
- 삭제: 삭제해줘, 지워줘, 없애줘 → delete_*, clear_* 계열
- 저장: 저장해줘, 기억해줘, 메모해줘 → save_*, remember_* 계열
- 설정: ~로 해줘, ~처럼 해줘 → set_* 계열

**2. 명사 기반 대상 구분**
- 메시지 → message 계열
- 구독 → subscription 계열
- 기억/선호도 → preference 계열
- 페르소나 → persona 계열

**3. 계층적 폴백**
```
사용자 요청
    ↓
[1차] 정확한 의도 매칭 (get_message, save_message 등)
    ↓ (매칭 실패)
[2차] 카테고리 폴백 (question → AI Agent로 처리)
    ↓ (복합 요청)
[3차] complex → Task Planner
```

### 구현 우선순위

| 단계 | 의도 | 이유 |
|------|------|------|
| Phase 1 (현재) | get_message 추가 | 즉각적인 버그 수정 |
| Phase 2 | web_search, x_search 분리 | 명시적 검색 요청 구분 |
| Phase 3 | subscribe, feed 계열 | 채널 구독 기능 |
| Phase 4 | persona 계열 | 페르소나 기능 |
| Phase 5 | export 계열 | 외부 서비스 연동 |

---

## 15. 답글 기반 메시지 저장 기능

### 문제
"이거 저장해줘"라고 입력하면 지시어 "이거"만 저장되는 문제.

### 문제 상황
```
사용자: (포워딩된 메시지)
사용자: "이거 저장해줘"

기대 동작: 포워딩된 메시지 내용 저장

실제 동작:
[의도 분류] SAVE_MESSAGE - 저장 내용 추출 시도
[의도 분류] 패턴 '(.+?)\s*저장해\s*줘?'에서 추출: '이거'
→ "이거"가 저장됨!
```

### 원인 분석

**1. 텔레그램 메시지 구조**
- 포워딩 메시지와 "이거 저장해줘"는 **별개의 메시지**
- 이전 메시지를 자동으로 참조하는 방법이 없음
- 텔레그램에서 답글(reply) 관계만 추적 가능

**2. 지시어 처리 부재**
- "이거", "방금 거", "위 메시지" 등 지시어를 그대로 저장
- 지시어가 실제 참조하는 대상을 파악하지 못함

### 해결

**1. 답글(reply_to_message) 기반 저장**
```python
# 답글 대상 메시지 확인
reply_message = update.message.reply_to_message
if reply_message:
    reply_content = reply_message.text or reply_message.caption
    # 답글 대상 메시지를 저장
```

**2. 지시어 감지 및 안내**
```python
pronoun_patterns = [r'^이거$', r'^이\s*메시지$', r'^방금\s*거$', r'^위\s*메시지$']
if arg and any(re.match(p, arg.strip()) for p in pronoun_patterns):
    # 사용자에게 답글 방식 안내
    "💡 저장하려는 메시지에 **답글**로 '저장해줘'라고 입력해주세요."
```

### 개선된 저장 방식

| 방식 | 예시 | 동작 |
|------|------|------|
| 답글로 저장 | (메시지에 답글) "저장해줘" | 답글 대상 메시지 저장 ✓ |
| 따옴표로 저장 | "'오늘 회의' 저장해줘" | 따옴표 안 내용 저장 ✓ |
| 지시어 사용 | "이거 저장해줘" | 안내 메시지 표시 |
| 포워딩 | (메시지 포워딩) | 자동 저장 ✓ |

### 교훈
- 텔레그램에서 이전 메시지 참조는 **답글(reply)** 관계로만 가능
- 지시어는 그대로 처리하지 말고 사용자에게 명확한 방법 안내
- 사용자 의도를 추측하기보다 올바른 사용법을 가이드

---

## 16. 메시지 목록 접기 표시 (ExpandableBlockQuote)

### 문제
`/list` 명령어로 저장된 메시지를 조회할 때, 긴 메시지가 100자로 잘려 전체 내용을 볼 수 없음.

### 문제 상황
```
📋 저장된 메시지 (최근 10개)

1. [포워딩] (2026-01-02 10:00)
삼성증권 리서치센터에서 발표한 2026년 반도체 시장 전망 보고서입니다. 주요 내용으로는...

2. [직접] (2026-01-02 09:30)
짧은 메모
```
- 긴 메시지는 `...`으로 잘림
- 전체 내용을 보려면 "1번 알려줘" 명령어 필요 → 불편함

### 해결
**텔레그램 ExpandableBlockQuote 기능 도입**

python-telegram-bot 21.3+에서 지원하는 `MessageEntity.EXPANDABLE_BLOCKQUOTE`를 활용.
100자 이상의 긴 메시지는 접힌 상태로 표시되고, 탭하면 전체 내용이 펼쳐짐.

```python
from telegram import MessageEntity

def format_message_list_with_expandable(messages: list, show_all: bool = False):
    entities = []
    # ... 텍스트 생성 ...

    # 100자 이상인 메시지에 접기 적용
    if len(content) > 100:
        entities.append(MessageEntity(
            type=MessageEntity.EXPANDABLE_BLOCKQUOTE,
            offset=current_offset,
            length=len(content)
        ))

    return text, entities

# 사용
text, entities = format_message_list_with_expandable(messages)
await update.message.reply_text(text, entities=entities)
```

### 적용 대상
| 명령어/기능 | 적용 여부 |
|-------------|-----------|
| `/list` | ✓ |
| `/listall` | ✓ |
| 자연어 "저장된 거 보여줘" | ✓ |
| 자연어 "전체 목록" | ✓ |

### 사용자 경험
```
📋 저장된 메시지 (최근 10개)

1. [포워딩] (2026-01-02 10:00)
▼ 삼성증권 리서치센터에서 발표한 2026년 반도체 시장 전망 보고서입니다...
   (탭하여 펼치기)

2. [직접] (2026-01-02 09:30)
짧은 메모
```

- 긴 메시지는 접힌 상태로 표시 (▼ 아이콘)
- 탭하면 전체 내용이 펼쳐짐
- 짧은 메시지(100자 이하)는 그대로 표시

### 주의사항
- 텔레그램 클라이언트 버전에 따라 표시가 다를 수 있음
- 구버전 클라이언트에서는 일반 텍스트로 표시됨

---

## 향후 개선 계획

- [x] **복합 의도 처리 시스템 도입** (9번에서 해결)
- [x] **Task Planner 세부 조건 처리 개선** (3계층 동기화로 해결)
- [x] **상세 로깅 시스템** (11번에서 해결)
- [x] **변수 참조 버그 수정** (12번에서 해결)
- [x] **get_message 의도 추가** (13번에서 해결)
- [x] **답글 기반 메시지 저장** (15번에서 해결)
- [ ] 대화 히스토리 기반 멀티턴 대화
- [ ] PDF/이미지 파일 분석
- [ ] 예약 알림 기능
- [ ] 금융 데이터 연동 (주가, 환율)
- [ ] 채널 구독 및 콘텐츠 수집 기능
- [ ] 사용자 기억 (Memory/RAG) 시스템
- [ ] 페르소나 기능
- [ ] 외부 서비스 연동 (Notion 등)
