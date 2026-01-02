# Telegram AI Agent Bot

텔레그램 메시지를 저장하고, AI 기반 Q&A와 실시간 웹/X(트위터) 검색을 제공하는 개인 비서 봇입니다.

## 주요 기능

- **메시지 저장**: 포워딩된 메시지 자동 저장, 직접 작성한 메시지 저장
- **컨텍스트 기반 Q&A**: 저장된 메시지를 참조하여 AI가 답변
- **실시간 웹 검색**: 최신 뉴스, 정보 검색
- **X(트위터) 검색**: 트렌드, 실시간 반응 검색

## 기술 스택

| 구분 | 기술 |
|------|------|
| Language | Python 3.9+ |
| Bot Framework | python-telegram-bot 20+ |
| AI Framework | LangChain |
| AI Model (Agent) | xAI Grok (grok-4-1-fast-reasoning) |
| AI Model (Intent/Planner) | Google Gemini 2.0 Flash |
| Database | SQLite (aiosqlite) |
| Deployment | Railway |

## 아키텍처

### 3단계 AI 처리 구조

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
│ complex → [3단계] Task Planner 호출     │
└─────────────────────────────────────────┘
    ↓ (question인 경우)
[2단계] AI Agent (Grok - 유료)
    ↓
웹 검색 / X 검색 / 컨텍스트 분석

    ↓ (complex인 경우)
[3단계] Task Planner (Gemini - 무료)
    ↓
작업 분해 → 순차 실행 (검색 → 번역 → 저장 등)
```

### 왜 3단계 구조인가?

1. **비용 절감**: 단순 명령(저장, 삭제, 목록)은 무료 모델로 처리
2. **빠른 응답**: 의도가 명확한 요청은 Agent 호출 없이 즉시 처리
3. **자연어 지원**: 키워드 매칭 대신 AI가 의도를 파악하여 유연한 처리
4. **복합 작업 처리**: "검색해서 번역 후 저장" 같은 다단계 작업 지원

## AI 모델 선택 가이드

이 프로젝트는 **xAI Grok API**와 **Google Gemini API**를 함께 사용합니다.

### 모델 역할

| 모델 | 역할 | 비용 |
|------|------|------|
| Gemini 2.0 Flash | 의도 분류 (8가지), Task Planner, LLM 도구 | 무료 |
| Grok grok-4-1-fast-reasoning | AI Agent (검색, 분석) | 유료 |

### 왜 Grok인가?

1. **내장 검색 도구**: Grok API는 `web_search`와 `x_search` 도구를 기본 제공합니다.
   - 별도의 검색 API (Tavily, SerpAPI 등) 구독 불필요
   - X(트위터) 검색은 Grok만 지원하는 고유 기능

2. **비용 효율성**:
   - grok-4-1-fast-reasoning: $0.20/1M input, $0.50/1M output
   - 검색 도구: 현재 무료 프로모션 중 (정가 $5/1,000 calls)

3. **OpenAI 호환 API**: LangChain과 완벽 호환

### 다른 모델 사용 시 고려사항

| 모델 | 웹 검색 | X 검색 | 비고 |
|------|---------|--------|------|
| xAI Grok | 내장 | 내장 | 권장 |
| OpenAI GPT | Tavily 등 필요 | 불가 | 추가 비용 발생 |
| Anthropic Claude | Tavily 등 필요 | 불가 | 추가 비용 발생 |

**X(트위터) 실시간 검색이 필요하다면 Grok이 유일한 선택입니다.**

## 설치 및 실행

### 1. 저장소 클론

```bash
git clone https://github.com/Vacayy/telegram-agent.git
cd telegram-agent
```

### 2. 가상환경 설정

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 실제 값으로 수정:

```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
XAI_API_KEY=xai-your_api_key
GOOGLE_AI_API_KEY=your_google_ai_api_key
```

### 4. 봇 실행

```bash
python main.py
```

## API 키 발급 방법

### Telegram Bot Token

1. Telegram에서 [@BotFather](https://t.me/BotFather) 검색
2. `/newbot` 명령어로 봇 생성
3. 봇 이름과 사용자명 입력 (사용자명은 `_bot`으로 끝나야 함)
4. 발급된 토큰 복사

### xAI Grok API Key

1. [xAI Console](https://console.x.ai/) 접속
2. X(Twitter) 계정으로 로그인
3. API Keys 메뉴에서 새 키 생성
4. 발급된 키 복사 (다시 볼 수 없으니 안전하게 보관)

### Google AI API Key (Gemini)

1. [Google AI Studio](https://aistudio.google.com/apikey) 접속
2. Google 계정으로 로그인
3. "Get API Key" 클릭하여 키 생성
4. 발급된 키 복사

## 사용 방법

### 텔레그램 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 시작 및 사용법 안내 |
| `/help` | 명령어 목록 |
| `/save <메시지>` | 메시지 저장 |
| `/list` | 저장된 메시지 목록 (최근 10개) |
| `/listall` | 저장된 메시지 전체 목록 |
| `/delete <번호>` | 특정 메시지 삭제 |
| `/clear` | 저장된 메시지 전체 삭제 |
| `/search <검색어>` | 웹 검색 |
| `/x <검색어>` | X(트위터) 검색 |

### 자연어 명령 (AI 의도 분류)

명령어 없이도 자연어로 대부분의 기능을 사용할 수 있습니다:

| 자연어 예시 | 동작 |
|-------------|------|
| "'안녕하세요' 저장해줘" | 메시지 저장 |
| "저장된 거 보여줘" | 메시지 목록 조회 |
| "1번 삭제해줘" | 특정 메시지 삭제 |
| "다 지워줘" | 전체 메시지 삭제 |
| "어떻게 써?" | 도움말 표시 |
| "이거 분석해줘" | AI Agent 호출 |
| "검색해서 번역 후 저장해줘" | 복합 작업 (Task Planner) |

### 메시지 저장 방법

- **포워딩**: 다른 채널/그룹의 메시지를 포워딩하면 자동 저장
- **명령어**: `/save 저장할 내용`
- **자연어**: "'내용' 저장해줘", "기억해줘: 내용", "메모해줘 내용"

### 사용 예시

```
사용자: (다른 채널에서 뉴스 기사 포워딩)
봇: ✅ 메시지가 저장되었습니다 (출처: 경제뉴스)

사용자: 방금 포워딩한 내용이 주가에 어떤 영향을 줄까?
봇: 🤔 생각 중...
     ↓ (같은 메시지가 업데이트됨)
봇: 🌐 웹 검색 중... ('TSMC 주가 전망')
     ↓
봇: (분석 결과)

사용자: 서울이랑 인디애나 날씨 비교해줘
봇: 🤔 생각 중...
     ↓ (검색 상태가 스택처럼 쌓임)
봇: 🌐 웹 검색 중... ('서울 날씨')
    🌐 웹 검색 중... ('인디애나 날씨')
     ↓
봇: (비교 분석 결과)

사용자: '내일 10시 미팅' 저장해줘
봇: ✅ 메시지가 저장되었습니다.
    저장된 내용: 내일 10시 미팅

사용자: /x 비트코인
봇: 🔍 X에서 '비트코인' 검색 중...
     ↓
봇: 🐦 X 검색 결과 (2026-01-02 10:00:00)
    (트위터 트렌드 및 반응)

사용자: X에서 @elon_musk 검색해서 한글로 번역 후 저장해줘
봇: 🤔 작업 계획 중...
     ↓
봇: 🐦 X 검색 중... ('@elon_musk')
    🌍 번역 중...
    💾 저장 중...
     ↓
봇: ✅ X에서 검색 후 번역하여 저장
    (번역된 검색 결과)
```

### 인라인 메시지 업데이트

봇은 텔레그램의 `edit_text()` 기능을 활용하여 하나의 메시지에서 상태를 업데이트합니다:
- "🤔 생각 중..." → "🌐 웹 검색 중..." → (최종 응답)
- 새 메시지를 생성하지 않고 기존 메시지를 수정
- 여러 도구 호출 시 상태가 스택처럼 쌓여 표시

## 디버깅 및 로깅

### 로그 출력 구조

봇 실행 시 콘솔에 상세한 로그가 출력되어 AI 처리 흐름을 추적할 수 있습니다:

```
##############################################################
[Bot] 새 메시지 수신
[Bot] user_id: 12345
[Bot] 메시지: 'X에서 @elon_musk 검색해서 요약해줘'
##############################################################

============================================================
[의도 분류] 시작
[의도 분류] LLM 원본 응답: 'complex'
[의도 분류] 최종 결과: intent=complex
============================================================

============================================================
[Task Planner] 분해된 단계: 2개
[Task Planner]   Step 1: x_search
[Task Planner]   Step 2: summarize
============================================================

============================================================
[Executor] 실행 시작
[Executor] Step 1/2: x_search
────────────────────────────────────────
[xAI Tool] x_search 호출
[xAI Tool] 결과: 1523자
────────────────────────────────────────
[Executor] Step 2/2: summarize
[Executor] 변수 치환: $search_result → (1523자)
────────────────────────────────────────
[LLM summarize] 완료: 245자
────────────────────────────────────────
[Executor] 성공: 2/2
============================================================
```

### 로깅 모듈별 역할

| 모듈 | 프리픽스 | 로깅 내용 |
|------|----------|----------|
| bot.py | `[Bot]` | 메시지 수신, 의도 분류 결과, 처리 경로 |
| agent.py | `[의도 분류]`, `[Agent]` | LLM 응답, 도구 호출 상태 |
| planner.py | `[Task Planner]` | 작업 분해, JSON 파싱 결과 |
| executor.py | `[Executor]` | 단계별 실행, 변수 치환 |
| xai_tools.py | `[xAI Tool]` | API 호출, 응답 추출 |
| llm.py | `[LLM ...]` | 번역/요약/분석 호출 및 결과 |

## 프로젝트 구조

```
telegram-agent/
├── main.py              # 진입점
├── config.py            # 환경변수 로드
├── requirements.txt     # 의존성
├── Procfile             # Railway 배포용
├── .env.example         # 환경변수 템플릿
├── src/
│   ├── bot.py           # 텔레그램 봇 핸들러
│   ├── agent.py         # 의도 분류 + LangChain Agent
│   ├── planner.py       # Task Planner (복합 작업 분해)
│   ├── executor.py      # Task Executor (순차 실행)
│   ├── database.py      # SQLite 데이터베이스
│   └── tools/
│       ├── __init__.py
│       ├── xai_tools.py # xAI 검색 도구
│       └── llm.py       # LLM 도구 (번역, 요약, 분석)
└── docs/
    ├── PROJECT_SPEC.md  # 프로젝트 기획서
    ├── IMPLEMENTATION.md # 구현 계획
    ├── CHANGELOG.md      # 개선 내역
    └── ARCHITECTURE_IMPROVEMENT.md # 아키텍처 개선 계획
```

## 예상 비용

| 항목 | 월 예상 비용 |
|------|-------------|
| Telegram Bot | 무료 |
| Google Gemini API (의도 분류) | 무료 |
| xAI Grok API (AI Agent) | ~$0.5-2 (일반 사용) |
| xAI 검색 도구 | 현재 무료 |
| Railway (Free) | 무료 |
| **합계** | **~$0.5-2/월** |

## 향후 로드맵

- [x] Phase 1: 복합 의도 처리 (Task Planner)
- [ ] Phase 2: 문서 분석 (PDF, 이미지 OCR)
- [ ] Phase 3: 금융 데이터 연동 (주가, 환율)
- [ ] Phase 4: 자동화 (알림, 스케줄링)

## 라이선스

MIT License

## 기여

이슈 및 PR 환영합니다.
