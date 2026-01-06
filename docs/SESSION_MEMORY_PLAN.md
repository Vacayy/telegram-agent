# Session Memory 구현 계획서

## 요구사항 요약

### 기능 요구사항 (FR)
- **FR-1**: user_id별로 최근 N개(기본 10개)의 대화 메시지를 메모리에 유지
- **FR-2**: TTL(기본 30분) 경과 시 세션 자동 만료
- **FR-3**: AI Agent 호출 시 chat_history에 세션 메모리 주입
- **FR-4**: 사용자/AI 응답 모두 세션에 기록

### 비기능 요구사항 (NFR)
- **NFR-1**: 메모리 효율성 - 최대 메시지 수 제한으로 무한 증가 방지
- **NFR-2**: 스레드 안전성 - 동시 요청 시 race condition 방지
- **NFR-3**: 성능 - 세션 조회/저장 O(1) 시간 복잡도

### 제약 조건
- 인메모리 구현 (Redis 등 외부 의존성 없음)
- 봇 재시작 시 세션 초기화 (영속성 불필요)
- 기존 코드 최소 변경

### 가정
- 동시 사용자 수가 수백 명 이하 (메모리 충분)
- 단일 프로세스 환경 (Railway 기본 배포)

---

## 현재 상태 분석

### 문제점

```python
# src/agent.py:376 - chat_history가 항상 빈 배열
result = await agent_executor.ainvoke(
    {
        "input": user_message,
        "context": context,
        "chat_history": []  # ← 문제: 대화 맥락 없음
    },
    ...
)
```

**결과**: "방금 뭐라고 했어?", "그거 더 자세히 알려줘" 같은 맥락 참조 불가

### 영향 범위

| 파일/모듈 | 변경 타입 | 설명 |
|-----------|----------|------|
| `src/memory.py` | **NEW** | SessionMemory 클래스 구현 |
| `src/agent.py` | MODIFY | chat_history에 세션 메모리 주입 |
| `src/bot.py` | MODIFY | 응답 후 세션에 기록 |

### 의존성 분석
- **의존**: `src/agent.py` → `src/memory.py` (신규)
- **피의존**: `src/bot.py` → `src/agent.py` (기존)

---

## 기술 설계

### 아키텍처

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│   bot.py    │────▶│  SessionMemory  │────▶│  agent.py   │
│             │     │                 │     │             │
│ 1. 메시지   │     │ - sessions{}    │     │ chat_history│
│    수신     │     │ - add()         │     │ 에 주입     │
│ 2. 응답 후  │     │ - get()         │     │             │
│    기록     │     │ - cleanup()     │     │             │
└─────────────┘     └─────────────────┘     └─────────────┘
```

### 데이터 모델

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage

@dataclass
class SessionMessage:
    """세션 내 단일 메시지"""
    role: Literal["human", "ai"]
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class UserSession:
    """사용자별 세션"""
    user_id: int
    messages: list[SessionMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
```

### SessionMemory 클래스 설계

```python
class SessionMemory:
    """인메모리 세션 관리자"""

    def __init__(
        self,
        max_messages: int = 10,      # 세션당 최대 메시지 수
        ttl_seconds: int = 1800,     # 30분
        cleanup_interval: int = 300  # 5분마다 정리
    ):
        self._sessions: dict[int, UserSession] = {}
        self._lock = asyncio.Lock()
        ...

    async def add(self, user_id: int, role: str, content: str) -> None:
        """메시지 추가 (슬라이딩 윈도우)"""
        ...

    async def get_history(self, user_id: int) -> list[BaseMessage]:
        """LangChain 형식으로 히스토리 반환"""
        ...

    async def clear(self, user_id: int) -> None:
        """특정 사용자 세션 초기화"""
        ...

    async def _cleanup_expired(self) -> None:
        """만료된 세션 정리 (백그라운드)"""
        ...
```

### LangChain 연동

```python
# agent.py 수정
from src.memory import get_session_memory

async def get_ai_response(user_id: int, user_message: str, ...) -> str:
    memory = get_session_memory()

    # 현재 세션 히스토리 가져오기
    chat_history = await memory.get_history(user_id)

    result = await agent_executor.ainvoke(
        {
            "input": user_message,
            "context": context,
            "chat_history": chat_history  # ← 세션 메모리 주입
        },
        ...
    )

    return result.get("output", "...")
```

---

## 구현 단계

### Step 1: SessionMemory 모듈 생성

#### [NEW] `src/memory.py`

```python
# 구현 내용:
# 1. SessionMessage, UserSession 데이터클래스
# 2. SessionMemory 클래스
#    - __init__: 설정값, 세션 딕셔너리, asyncio.Lock
#    - add(): 메시지 추가 + 슬라이딩 윈도우
#    - get_history(): LangChain BaseMessage 리스트 반환
#    - clear(): 세션 초기화
#    - _cleanup_expired(): TTL 기반 정리
#    - _is_expired(): 만료 여부 체크
# 3. 글로벌 인스턴스 + get_session_memory() 함수
```

### Step 2: Agent에 세션 메모리 연동

#### [MODIFY] `src/agent.py`

- `get_ai_response()` 함수 수정
- `get_session_memory()` import
- `chat_history` 파라미터에 세션 히스토리 전달

### Step 3: Bot에서 세션 기록

#### [MODIFY] `src/bot.py`

- `handle_regular_message()` 수정
- 사용자 메시지 → 세션에 추가
- AI 응답 → 세션에 추가
- `/clear` 명령어에 세션 초기화 옵션 추가 (선택)

### Step 4: 백그라운드 정리 태스크

#### [MODIFY] `main.py`

- `post_init()`에서 cleanup 태스크 시작

---

## ⚠️ 리스크 및 고려사항

### Breaking Changes
- 없음 (기존 동작 유지, chat_history만 채워짐)

### 메모리 사용량
- 예상: 사용자 100명 × 메시지 10개 × 500자 = 약 500KB
- 최악: 1000명 × 10개 × 2000자 = 약 20MB
- **결론**: 문제없음

### 대안 검토

| 방안 | 장점 | 단점 |
|------|------|------|
| **인메모리 (선택)** | 간단, 외부 의존성 없음 | 재시작 시 초기화 |
| Redis | 영속성, 분산 환경 지원 | 추가 인프라 필요 |
| SQLite | 영속성, 이미 사용 중 | 복잡도 증가, I/O |

현재 규모에서는 인메모리가 적합. 확장 시 Redis 전환 고려.

---

## 검증 계획

### 자동 테스트
- [ ] `test_session_memory.py`: 단위 테스트
  - 메시지 추가/조회
  - 슬라이딩 윈도우 동작
  - TTL 만료 처리
  - 동시성 테스트

### 수동 검증
- [ ] "안녕" → "방금 뭐라고 했어?" → "안녕이라고 하셨습니다" 확인
- [ ] 10개 초과 메시지 시 오래된 것 삭제 확인
- [ ] 30분 후 세션 초기화 확인
- [ ] `/clear` 후 세션 초기화 확인

---

## 예상 결과

### Before
```
사용자: 서울 날씨 알려줘
봇: 서울은 현재 맑고 기온은 5도입니다.

사용자: 그럼 내일은?
봇: 무엇에 대해 물어보시는 건가요? (맥락 없음)
```

### After
```
사용자: 서울 날씨 알려줘
봇: 서울은 현재 맑고 기온은 5도입니다.

사용자: 그럼 내일은?
봇: 서울 내일 날씨는 흐리고 기온은 3도입니다. (맥락 유지)
```
