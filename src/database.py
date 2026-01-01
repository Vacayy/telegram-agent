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
    """LLM 컨텍스트용 메시지 포맷팅"""
    messages = await get_messages(user_id, limit)

    if not messages:
        return "저장된 메시지가 없습니다."

    context_parts = []
    for msg in reversed(messages):  # 시간순으로 정렬
        source = f"[포워딩: {msg['forward_from']}]" if msg['is_forwarded'] else "[직접 작성]"
        time_str = msg['created_at'][:16] if msg['created_at'] else ""
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
