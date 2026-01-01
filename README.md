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
| AI Model | xAI Grok (grok-4-1-fast-reasoning) |
| Database | SQLite (aiosqlite) |
| Deployment | Railway |

## AI 모델 선택 가이드

이 프로젝트는 **xAI Grok API**를 사용합니다.

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

## 사용 방법

### 텔레그램 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 시작 및 사용법 안내 |
| `/help` | 명령어 목록 |
| `/list` | 저장된 메시지 목록 (최근 10개) |
| `/clear` | 저장된 메시지 전체 삭제 |
| `/search <검색어>` | 웹 검색 |
| `/x <검색어>` | X(트위터) 검색 |

### 일반 메시지

- **포워딩된 메시지**: 자동으로 저장됨
- **"저장", "기억", "메모" 포함 메시지**: 저장됨
- **일반 질문**: AI가 저장된 컨텍스트 + 검색 결과로 답변

### 사용 예시

```
사용자: (다른 채널에서 뉴스 기사 포워딩)
봇: ✅ 메시지가 저장되었습니다 (출처: 경제뉴스)

사용자: 방금 포워딩한 내용이 주가에 어떤 영향을 줄까?
봇: 🤔 생각 중...
봇: 🌐 웹 검색 중... ('TSMC 주가 전망')
봇: (분석 결과)

사용자: /x 비트코인
봇: 🔍 X에서 '비트코인' 검색 중...
봇: 🐦 X 검색 결과 (2026-01-01 21:00:00)
    (트위터 트렌드 및 반응)
```

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
│   ├── agent.py         # LangChain Agent
│   ├── database.py      # SQLite 데이터베이스
│   └── tools/
│       ├── __init__.py
│       └── xai_tools.py # xAI 검색 도구
└── docs/
    ├── PROJECT_SPEC.md  # 프로젝트 기획서
    └── IMPLEMENTATION.md # 구현 계획
```

## 예상 비용

| 항목 | 월 예상 비용 |
|------|-------------|
| Telegram Bot | 무료 |
| xAI Grok API | ~$0.5-2 (일반 사용) |
| xAI 검색 도구 | 현재 무료 |
| Railway (Free) | 무료 |
| **합계** | **~$0.5-2/월** |

## 향후 로드맵

- [ ] Phase 2: 문서 분석 (PDF, 이미지 OCR)
- [ ] Phase 3: 금융 데이터 연동 (주가, 환율)
- [ ] Phase 4: 자동화 (알림, 스케줄링)

## 라이선스

MIT License

## 기여

이슈 및 PR 환영합니다.
