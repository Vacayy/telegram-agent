"""Session Memory - 사용자별 대화 맥락 유지

슬라이딩 윈도우 + TTL 기반 인메모리 세션 관리.
LangChain chat_history 형식으로 변환하여 Agent에 주입.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


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


class SessionMemory:
    """인메모리 세션 관리자

    - 사용자별 최근 N개 메시지 유지 (슬라이딩 윈도우)
    - TTL 경과 시 세션 자동 만료
    - LangChain BaseMessage 형식으로 변환
    """

    def __init__(
        self,
        max_messages: int = 10,
        ttl_seconds: int = 1800,  # 30분
    ):
        self._sessions: dict[int, UserSession] = {}
        self._lock = asyncio.Lock()
        self._max_messages = max_messages
        self._ttl_seconds = ttl_seconds

    async def add(self, user_id: int, role: Literal["human", "ai"], content: str) -> None:
        """메시지 추가 (슬라이딩 윈도우)"""
        async with self._lock:
            # 세션 없으면 생성
            if user_id not in self._sessions:
                self._sessions[user_id] = UserSession(user_id=user_id)

            session = self._sessions[user_id]

            # 만료된 세션이면 초기화
            if self._is_expired(session):
                session.messages = []
                session.created_at = datetime.now()

            # 메시지 추가
            session.messages.append(
                SessionMessage(role=role, content=content)
            )

            # 슬라이딩 윈도우 - 최대 개수 초과 시 오래된 것 삭제
            if len(session.messages) > self._max_messages:
                session.messages = session.messages[-self._max_messages :]

            # 마지막 활동 시간 갱신
            session.last_active = datetime.now()

    async def get_history(self, user_id: int) -> list[BaseMessage]:
        """LangChain 형식으로 히스토리 반환"""
        async with self._lock:
            session = self._sessions.get(user_id)

            if not session or self._is_expired(session):
                return []

            messages: list[BaseMessage] = []
            for msg in session.messages:
                if msg.role == "human":
                    messages.append(HumanMessage(content=msg.content))
                else:
                    messages.append(AIMessage(content=msg.content))

            return messages

    async def clear(self, user_id: int) -> None:
        """특정 사용자 세션 초기화"""
        async with self._lock:
            if user_id in self._sessions:
                del self._sessions[user_id]

    async def cleanup_expired(self) -> int:
        """만료된 세션 정리, 삭제된 세션 수 반환"""
        async with self._lock:
            expired_users = [
                user_id
                for user_id, session in self._sessions.items()
                if self._is_expired(session)
            ]

            for user_id in expired_users:
                del self._sessions[user_id]

            return len(expired_users)

    def _is_expired(self, session: UserSession) -> bool:
        """세션 만료 여부 확인"""
        elapsed = (datetime.now() - session.last_active).total_seconds()
        return elapsed > self._ttl_seconds

    @property
    def session_count(self) -> int:
        """현재 활성 세션 수"""
        return len(self._sessions)

    def get_session_info(self, user_id: int) -> Optional[dict]:
        """세션 정보 조회 (디버깅용)"""
        session = self._sessions.get(user_id)
        if not session:
            return None

        return {
            "user_id": session.user_id,
            "message_count": len(session.messages),
            "created_at": session.created_at.isoformat(),
            "last_active": session.last_active.isoformat(),
            "is_expired": self._is_expired(session),
        }


# 글로벌 인스턴스
_session_memory: Optional[SessionMemory] = None


def get_session_memory() -> SessionMemory:
    """글로벌 SessionMemory 인스턴스 반환"""
    global _session_memory
    if _session_memory is None:
        _session_memory = SessionMemory()
    return _session_memory


def reset_session_memory() -> None:
    """글로벌 인스턴스 리셋 (테스트용)"""
    global _session_memory
    _session_memory = None
