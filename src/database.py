import aiosqlite
from datetime import datetime
from typing import Optional
from pathlib import Path

DATABASE_PATH = Path("data.db")


async def init_db():
    """데이터베이스 초기화 및 테이블 생성"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                is_forwarded BOOLEAN DEFAULT FALSE,
                forward_from TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id ON messages(user_id)
        """)
        await db.commit()


async def save_message(
    user_id: int,
    content: str,
    is_forwarded: bool = False,
    forward_from: Optional[str] = None
) -> int:
    """메시지 저장"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO messages (user_id, content, is_forwarded, forward_from, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, content, is_forwarded, forward_from, datetime.now())
        )
        await db.commit()
        return cursor.lastrowid


async def get_messages(user_id: int, limit: int = 50) -> list[dict]:
    """사용자의 저장된 메시지 조회 (최신순)"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, content, is_forwarded, forward_from, created_at
            FROM messages
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_all_messages_as_context(user_id: int, limit: int = 20) -> str:
    """LLM 컨텍스트용 메시지 포맷팅

    가장 최근 메시지를 명확히 표시하여 "이거", "방금 거" 등의 지시어가
    올바르게 해석될 수 있도록 합니다.
    """
    messages = await get_messages(user_id, limit)

    if not messages:
        return "저장된 메시지가 없습니다."

    context_parts = []
    # messages는 최신순(DESC)이므로, reversed하면 오래된 것부터 시간순
    messages_chronological = list(reversed(messages))
    total_count = len(messages_chronological)

    for idx, msg in enumerate(messages_chronological):
        source = f"[포워딩: {msg['forward_from']}]" if msg['is_forwarded'] else "[직접 작성]"
        time_str = msg['created_at'][:16] if msg['created_at'] else ""

        # 가장 최근 메시지(마지막)에 특별 표시
        if idx == total_count - 1:
            context_parts.append(
                f"[가장 최근 저장된 메시지] {source} ({time_str})\n{msg['content']}"
            )
        else:
            context_parts.append(f"{source} ({time_str})\n{msg['content']}")

    return "\n\n---\n\n".join(context_parts)


async def clear_messages(user_id: int) -> int:
    """사용자의 모든 메시지 삭제"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM messages WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
        return cursor.rowcount


async def get_message_count(user_id: int) -> int:
    """저장된 메시지 개수 조회"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ?",
            (user_id,)
        )
        result = await cursor.fetchone()
        return result[0] if result else 0


async def get_message_by_index(user_id: int, index: int) -> Optional[dict]:
    """인덱스(1부터 시작)로 메시지 조회 (최신순 기준)"""
    messages = await get_messages(user_id, limit=1000)

    if not messages or index < 1 or index > len(messages):
        return None

    # 인덱스는 1부터 시작, 리스트는 0부터
    return messages[index - 1]


async def delete_message_by_index(user_id: int, index: int) -> bool:
    """인덱스(1부터 시작)로 메시지 삭제 (최신순 기준)"""
    messages = await get_messages(user_id, limit=1000)

    if not messages or index < 1 or index > len(messages):
        return False

    # 인덱스는 1부터 시작, 리스트는 0부터
    message_id = messages[index - 1]["id"]

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM messages WHERE id = ? AND user_id = ?",
            (message_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0
