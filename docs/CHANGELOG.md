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

## 향후 개선 계획

- [ ] 대화 히스토리 기반 멀티턴 대화
- [ ] PDF/이미지 파일 분석
- [ ] 예약 알림 기능
- [ ] 금융 데이터 연동 (주가, 환율)
