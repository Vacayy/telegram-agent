# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

텔레그램 AI 비서 봇. 메시지 저장, 컨텍스트 기반 Q&A, 실시간 웹/X(트위터) 검색을 제공한다.

## 명령어

```bash
# 실행
python main.py

# 의존성 설치
pip install -r requirements.txt

# Railway 배포 (Procfile 사용)
web: python main.py
```

## 환경 변수

```bash
TELEGRAM_BOT_TOKEN=xxx    # @BotFather에서 발급
XAI_API_KEY=xai-xxx       # xAI Console에서 발급
GOOGLE_AI_API_KEY=xxx     # Google AI Studio에서 발급
```

## 아키텍처

### 3단계 AI 처리 파이프라인

```
사용자 메시지
    ↓
[1단계] 의도 분류 (Gemini 2.0 Flash - 무료)
    ↓
┌─────────────────────────────────────────────────────┐
│ save_message, list_messages, get_message, etc.     │ → 직접 처리
│ question                                            │ → [2단계] AI Agent
│ complex                                             │ → [3단계] Task Planner
└─────────────────────────────────────────────────────┘
    ↓ (question)
[2단계] AI Agent (Grok grok-4-1-fast-reasoning)
    └─ web_search, x_search (Grok 내장 도구)
    ↓ (complex)
[3단계] Task Planner (Gemini) → Executor
    └─ 작업 분해 → 순차 실행 (검색 → 번역 → 저장 등)
```

### 핵심 모듈

| 모듈 | 역할 |
|------|------|
| `src/bot.py` | 텔레그램 핸들러, 의도별 라우팅 |
| `src/agent.py` | 의도 분류 (`classify_intent`), LangChain Agent 생성 |
| `src/planner.py` | 복합 작업 분해 (JSON 출력) |
| `src/executor.py` | 단계별 작업 실행, `$변수` 참조 치환 |
| `src/registry.py` | Tool Registry - Provider 추상화, Fallback, 비용 추적 |
| `src/database.py` | SQLite CRUD (aiosqlite) |
| `src/tools/xai_tools.py` | xAI Grok API 호출 (web_search, x_search) |
| `src/tools/llm.py` | Gemini 기반 도구 (translate, summarize, analyze) |
| `src/debate/` | AI 토론 기능 (3명 페르소나, 5라운드) |

### 의도 분류 (UserIntent)

`src/agent.py`의 `classify_intent()`가 메시지를 10가지 의도로 분류:
- 단순 의도: `save_message`, `list_messages`, `list_all`, `get_message`, `delete_message`, `clear_messages`, `help`, `usage`
- 복합 의도: `question` (AI Agent), `complex` (Task Planner)

### Tool Registry 패턴

`src/registry.py`가 모든 도구를 중앙 관리:
- 도구 등록: `registry.register(action, provider, handler, cost_config)`
- 도구 실행: `registry.execute(action, params)` - Fallback 자동 처리
- 비용 추적: 토큰 기반 예상 비용 계산, `/usage` 명령어로 조회

새 도구 추가 시 `_register_default_tools()`에만 등록하면 Executor가 자동으로 사용 가능.

### Task Planner 출력 형식

`src/planner.py`가 복합 요청을 JSON으로 분해:
```json
{
    "steps": [
        {"action": "x_search", "params": {"query": "..."}, "output_key": "result1"},
        {"action": "summarize", "params": {"text": "$result1"}, "output_key": "result2"}
    ],
    "summary": "X 검색 후 요약"
}
```
- `$변수명`으로 이전 단계 결과 참조
- Executor가 `output_key`를 `context_chain`에 저장

## AI 모델 선택

| 용도 | 모델 | 비용 |
|------|------|------|
| 의도 분류, Task Planner, 번역/요약/분석 | Gemini 2.0 Flash | 무료 |
| AI Agent (검색 포함) | Grok grok-4-1-fast-reasoning | $0.20/1M in, $0.50/1M out |
| 검색 도구 (web_search, x_search) | Grok 내장 | 현재 무료 (프로모션) |

X(트위터) 검색은 Grok만 지원 - 대체 불가.

## 데이터베이스

SQLite `data.db` - 단일 테이블:
```sql
messages (id, user_id, content, is_forwarded, forward_from, created_at)
```

## 텔레그램 명령어

| 명령어 | 설명 |
|--------|------|
| `/save <메시지>` | 저장 |
| `/list`, `/listall` | 목록 조회 |
| `/delete <번호>` | 삭제 |
| `/clear` | 전체 삭제 |
| `/search <검색어>` | 웹 검색 |
| `/x <검색어>` | X 검색 |
| `/usage` | API 사용량 |
| `/debate <주제>` | AI 토론 |

## 주의사항

- Grok API는 OpenAI 호환 (`base_url="https://api.x.ai/v1"`)
- 삭제 명령(`delete_message`, `clear_messages`)은 확인 안내 후 명시적 `/delete`, `/clear` 입력 필요
- ExpandableBlockQuote로 긴 메시지 접기 지원 (python-telegram-bot 21.3+)
- 메시지 목록 번호는 최신순 (1번 = 가장 최근)
