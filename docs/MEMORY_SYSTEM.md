# Agent 메모리 시스템 설계

## 1. 왜 메모리가 필요한가?

### 현재 문제

현재 봇은 **상태 비저장(Stateless)** 방식으로 동작한다:

```
사용자: 비트코인 가격 알려줘
봇: 비트코인은 현재 $95,000입니다.

사용자: 그거 왜 올랐어?
봇: "그거"가 무엇인지 알 수 없습니다. ← 문제!
```

매 요청이 독립적이라 **대화 맥락**을 유지하지 못한다.

### 코드에서의 문제점

```python
# src/agent.py:376
result = await agent_executor.ainvoke(
    {
        "input": user_message,
        "context": context,         # 저장된 메시지 (장기 기억)
        "chat_history": []          # ← 항상 빈 배열 (단기 기억 없음)
    },
    ...
)
```

`chat_history`가 항상 빈 배열이라 LLM은 이전 대화를 전혀 모른다.

---

## 2. 메모리 유형 분류

AI Agent의 메모리는 크게 4가지로 분류된다:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Memory                              │
├────────────────┬────────────────┬────────────────┬──────────────┤
│   Short-term   │   Long-term    │    Episodic    │  External    │
│   (단기 기억)   │   (장기 기억)   │   (일화 기억)   │   (외부)      │
├────────────────┼────────────────┼────────────────┼──────────────┤
│ 현재 대화       │ 사용자 프로필   │ 과거 대화 요약  │ 웹 검색      │
│ 세션 컨텍스트   │ 선호도/습관     │ 중요 이벤트    │ DB 조회      │
│ 작업 상태       │ 패턴 학습       │ 하이라이트     │ 벡터 스토어   │
├────────────────┼────────────────┼────────────────┼──────────────┤
│ 휘발성          │ 영구 저장       │ 선택적 저장    │ 실시간 조회   │
│ 세션 종료 시    │ 사용자별 누적   │ 중요도 기반    │ 필요 시 호출  │
│ 삭제           │                │ 압축/요약      │              │
└────────────────┴────────────────┴────────────────┴──────────────┘
```

### 각 메모리의 역할

| 유형 | 용도 | 예시 |
|------|------|------|
| **Short-term** | 현재 대화 흐름 유지 | "그거 뭐야?", "더 자세히" |
| **Long-term** | 사용자 맞춤화 | "전에 말했듯이 저는...", "매번 한글로 답해줘" |
| **Episodic** | 과거 참조 | "지난주에 비트코인 얘기했을 때..." |
| **External** | 실시간 정보 | 웹 검색, DB 조회, 문서 RAG |

---

## 3. 현재 프로젝트 상태

| 메모리 유형 | 구현 여부 | 현재 상태 |
|------------|----------|----------|
| **Short-term** | ❌ 미구현 | `chat_history=[]` 고정 |
| **Long-term** | ⚠️ 부분 구현 | `messages` 테이블 (수동 저장만) |
| **Episodic** | ❌ 미구현 | 대화 요약/기록 없음 |
| **External** | ✅ 구현됨 | web_search, x_search, DB 조회 |

### 우선순위

```
1. Short-term (세션 메모리) ← 가장 급함
   - ROI 높음: 간단한 구현으로 큰 UX 개선
   - 비용 낮음: 인메모리, 외부 의존성 없음

2. Episodic (대화 요약)
   - 세션 종료 시 Gemini로 요약 저장
   - 장기 맥락 유지에 도움

3. Long-term (사용자 프로필)
   - 명시적 설정 + 암묵적 학습
   - 개인화 기능 확장 시 필요

4. Vector Store (RAG 강화)
   - 저장된 메시지가 많아지면 필요
   - 현재 규모에서는 과잉
```

---

## 4. Session Memory 설계

### 핵심 개념

```
┌─────────────────────────────────────────────────────────────┐
│                    Session Memory                            │
│                                                              │
│  user_123: [msg1, msg2, msg3, ..., msg10] ← 슬라이딩 윈도우  │
│  user_456: [msg1, msg2]                                      │
│  user_789: [msg1, msg2, msg3, msg4, msg5]                   │
│                                                              │
│  - 최대 N개 메시지 (기본 10개)                                │
│  - TTL 30분 (마지막 활동 기준)                                │
│  - 봇 재시작 시 초기화                                        │
└─────────────────────────────────────────────────────────────┘
```

### 슬라이딩 윈도우

```python
# 메시지 추가 시
session.messages.append(new_message)

# 최대 개수 초과 시 오래된 것 삭제
if len(session.messages) > max_messages:
    session.messages = session.messages[-max_messages:]
```

### TTL (Time To Live)

```python
# 마지막 활동 시간 기록
session.last_active = datetime.now()

# 만료 체크
is_expired = (datetime.now() - session.last_active).seconds > ttl_seconds
```

### LangChain 연동

```python
# SessionMemory → LangChain 형식 변환
def get_history(user_id: int) -> list[BaseMessage]:
    session = self._sessions.get(user_id)
    if not session:
        return []

    messages = []
    for msg in session.messages:
        if msg.role == "human":
            messages.append(HumanMessage(content=msg.content))
        else:
            messages.append(AIMessage(content=msg.content))
    return messages
```

---

## 5. 향후 확장 계획

### Phase 1: Session Memory (현재)
- 인메모리 세션 관리
- 슬라이딩 윈도우 + TTL
- LangChain chat_history 연동

### Phase 2: Conversation Summary
```python
# 세션 종료 시 요약 저장
conversation_summaries (
    user_id INTEGER,
    summary TEXT,           # "비트코인 투자 상담, 보수적 접근 선호"
    topics TEXT[],          # ["crypto", "investment"]
    created_at TIMESTAMP
)
```

### Phase 3: User Profile
```python
# 사용자 선호도 저장
user_profiles (
    user_id INTEGER,
    preferences JSON,       # {"language": "ko", "style": "concise"}
    interests TEXT[],       # 자주 검색하는 주제
    updated_at TIMESTAMP
)
```

### Phase 4: Vector Memory (선택)
```python
# 저장된 메시지 벡터화
from langchain.vectorstores import Chroma

class VectorMemory:
    async def add(self, content: str, metadata: dict):
        self.store.add_texts([content], metadatas=[metadata])

    async def search(self, query: str, k: int = 5) -> list:
        return self.store.similarity_search(query, k=k)
```

---

## 6. 저장소 선택 가이드

### 메모리 유형별 적합한 저장소

| 메모리 유형 | SQLite | 인메모리 | Redis | 벡터 DB | PostgreSQL |
|------------|--------|---------|-------|---------|------------|
| **Short-term** | ❌ | ✅ 최적 | ✅ 확장 시 | ❌ | ❌ |
| **Long-term** | ✅ 현재 | ❌ | ❌ | ❌ | ✅ 확장 시 |
| **Episodic** | ✅ | ❌ | ❌ | ⚠️ 대량 시 | ✅ |
| **External/RAG** | ❌ | ❌ | ❌ | ✅ 필수 | ⚠️ pgvector |

### 대화 맥락에 벡터 DB가 필요한가?

**Short-term (현재 대화)**: 벡터 DB **불필요**
```python
# 최근 10개 대화를 "순서대로" 전달
chat_history = [
    HumanMessage("비트코인 가격 알려줘"),
    AIMessage("현재 $95,000입니다"),
    HumanMessage("그거 왜 올랐어?"),  # ← "그거"는 바로 위 맥락
]
# LLM에 전체 전달 → 검색 필요 없음
```

**Episodic (과거 대화)**: 수천 개일 때 벡터 DB **필요**
```
대화 1000개 중에서 "비트코인 관련 대화"만 찾아야 할 때
→ 전체를 LLM에 넣을 수 없음 (토큰 한계)
→ 의미 기반 검색으로 관련 대화만 추출
```

---

## 7. PostgreSQL vs MongoDB

### AI/Agent에서 PostgreSQL이 선호되는 이유

| 항목 | PostgreSQL | MongoDB |
|------|-----------|---------|
| **pgvector** | ✅ 벡터 검색 확장 | ❌ 별도 Atlas Vector Search 필요 |
| **ACID** | ✅ 완벽한 트랜잭션 | ⚠️ 제한적 |
| **JSON 지원** | ✅ JSONB (인덱싱 가능) | ✅ 네이티브 |
| **SQL** | ✅ 표준 SQL | ❌ 자체 쿼리 언어 |
| **생태계** | Supabase, Neon, Railway | MongoDB Atlas |

### pgvector - 관계형 + 벡터 올인원

```sql
-- PostgreSQL + pgvector
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(1536)  -- OpenAI 임베딩 차원
);

-- 유사도 검색 (cosine similarity)
SELECT * FROM documents
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 5;
```

**PostgreSQL 하나로 관계형 + 벡터 검색**이 가능해서, 별도 벡터 DB 없이도 RAG 구현 가능.

### MongoDB가 적합한 경우
- 스키마가 자주 바뀌는 초기 프로토타입
- 문서 단위 저장이 많은 CMS
- 이미 MongoDB 인프라가 있는 경우

---

## 8. 벡터 DB 비교

### Pinecone이란?

**"벡터 전용 클라우드 DB"** - 텍스트를 숫자 벡터로 변환해서 유사한 것끼리 빠르게 찾아줌.

```
1. 텍스트 → 임베딩 모델 → 벡터 (숫자 배열)
   "비트코인이 올랐다" → [0.12, -0.34, 0.56, ...] (1536차원)

2. 벡터를 Pinecone에 저장

3. 검색 시:
   "암호화폐 상승" → [0.11, -0.32, 0.58, ...]
   → Pinecone이 가장 유사한 벡터 찾음
   → "비트코인이 올랐다" 반환
```

### 벡터 DB 비교표

| DB | 성능 | 비용 | 생태계 | Agent 사용 사례 |
|----|------|------|--------|----------------|
| **Pinecone** | ⭐⭐⭐⭐⭐ | 💰💰💰 | ⭐⭐⭐⭐⭐ | OpenAI 공식 파트너, GPT Actions |
| **Chroma** | ⭐⭐⭐⭐ | 무료 | ⭐⭐⭐⭐ | LangChain 기본, 로컬 개발용 |
| **Qdrant** | ⭐⭐⭐⭐⭐ | 💰 | ⭐⭐⭐⭐ | Rust 기반, 빠름, 셀프호스팅 쉬움 |
| **Weaviate** | ⭐⭐⭐⭐⭐ | 💰💰 | ⭐⭐⭐⭐ | 하이브리드 검색, GraphQL |
| **pgvector** | ⭐⭐⭐ | 💰 | ⭐⭐⭐ | PostgreSQL 확장, 기존 DB 활용 |

### 생태계 순위 (레퍼런스/튜토리얼 많은 순)
```
1. Pinecone - OpenAI, LangChain 공식 문서 대부분 예시
2. Chroma - LangChain 기본값, 빠른 프로토타이핑
3. Weaviate - 엔터프라이즈 레퍼런스 많음
4. Qdrant - 최근 급성장, 가성비 좋음
```

### 코드 예시 (Pinecone)

```python
import pinecone
from openai import OpenAI

# 1. 텍스트 → 벡터
openai = OpenAI()
response = openai.embeddings.create(
    model="text-embedding-3-small",
    input="비트코인이 올랐다"
)
vector = response.data[0].embedding

# 2. Pinecone에 저장
index = pinecone.Index("my-index")
index.upsert([("doc_1", vector, {"text": "비트코인이 올랐다"})])

# 3. 유사 검색
results = index.query(vector=query_vector, top_k=5)
```

---

## 9. 크롤링 데이터 RAG 아키텍처

### 시나리오별 추천

| 시나리오 | 추천 | 이유 |
|----------|------|------|
| **뉴스 기사 RAG** | 벡터 DB | "경제 위기 관련 기사" 의미 검색 |
| **상품 카탈로그** | 관계형 + 벡터 | 필터(가격, 카테고리) + 유사 상품 |
| **로그/메트릭** | 관계형/시계열 DB | 정확한 시간 범위 쿼리 |
| **FAQ/문서** | 벡터 DB | "환불 어떻게 해요?" → 관련 문서 |

### 크롤링 RAG 파이프라인

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  크롤러      │────▶│  전처리      │────▶│  저장소      │
│  (Scrapy)   │     │  (청킹)      │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
              ┌──────────┐             ┌──────────┐             ┌──────────┐
              │ 관계형 DB │             │ 벡터 DB  │             │ 하이브리드│
              │          │             │          │             │          │
              │ 메타데이터│             │ 임베딩   │             │PostgreSQL│
              │ 원본 텍스트│            │ 청크     │             │+ pgvector│
              └──────────┘             └──────────┘             └──────────┘
                   │                         │                         │
                   ▼                         ▼                         ▼
              정확한 필터              의미 기반 검색              둘 다 가능
              (날짜, 출처)            ("이런 느낌의 기사")
```

### 하이브리드 검색 (가장 효과적)

```python
# 1단계: 벡터 검색으로 의미상 유사한 것 찾기
similar_chunks = vector_db.search("경제 위기 영향", top_k=20)

# 2단계: 관계형 DB로 필터링
results = postgres.query("""
    SELECT * FROM documents
    WHERE id IN :chunk_ids
      AND crawled_at > '2024-01-01'
      AND source = 'reuters'
    ORDER BY crawled_at DESC
""")
```

### 데이터 모델 예시

```python
# 크롤링 원본 → 관계형 DB
class CrawledDocument:
    id: str
    url: str
    title: str
    content: str           # 원본 텍스트
    crawled_at: datetime
    source: str

# 청크 + 임베딩 → 벡터 DB (또는 pgvector)
class DocumentChunk:
    id: str
    document_id: str       # FK
    chunk_text: str
    embedding: list[float]
    chunk_index: int
```

---

## 10. 프로젝트 단계별 추천 스택

### 현재 (MVP)
```
Short-term  → 인메모리 (dict + asyncio.Lock)
Long-term   → SQLite (현재 유지)
Episodic    → SQLite (테이블 추가)
Vector      → 불필요
```
**추가 비용: $0**

### 확장 단계 (사용자 100+)
```
Short-term  → Redis (Upstash 무료 티어)
Long-term   → PostgreSQL (Supabase 무료 티어)
Episodic    → PostgreSQL
Vector      → Chroma (로컬) or Pinecone (무료 티어)
```
**추가 비용: $0~10/월**

### 프로덕션 (사용자 1000+)
```
Short-term  → Redis Cloud
Long-term   → PostgreSQL (managed)
Episodic    → PostgreSQL
Vector      → Pinecone or Qdrant Cloud
```
**추가 비용: $50~200/월**

### Agent 프레임워크별 선호 스택

| 프레임워크 | 세션 | 벡터 | 레퍼런스 |
|-----------|------|------|----------|
| **LangChain** | Redis | Pinecone, Chroma | 가장 많음 |
| **LlamaIndex** | - | Pinecone, Weaviate | RAG 특화 |
| **AutoGPT** | Redis | Pinecone | 공식 지원 |
| **CrewAI** | - | Chroma | LangChain 기반 |

**"Redis + Pinecone"** 조합이 Agent 생태계에서 가장 레퍼런스 많고 안전한 선택.

---

## 11. 참고 자료

- [LangChain Memory](https://python.langchain.com/docs/modules/memory/)
- [LangGraph Persistence](https://langchain-ai.github.io/langgraph/concepts/persistence/)
- [OpenAI Cookbook - Conversation Memory](https://cookbook.openai.com/examples/how_to_build_a_conversation_memory)
- [Pinecone Documentation](https://docs.pinecone.io/)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [Chroma Documentation](https://docs.trychroma.com/)
