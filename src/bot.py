from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
from src.database import (
    save_message,
    get_messages,
    clear_messages,
    get_message_count,
    delete_message_by_index,
)
from src.agent import get_ai_response, search_web_only, search_x_only, classify_intent, UserIntent
from src.tools.xai_tools import SearchError


# ==================== 명령어 핸들러 ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start - 봇 시작 및 사용법 안내"""
    welcome_message = """👋 안녕하세요! 저는 당신의 AI 비서입니다.

📝 **사용 방법**
1. 다른 채널/그룹의 메시지를 이 채팅방으로 포워딩하세요
2. 또는 /save 명령어로 메시지를 저장하세요
3. 저장된 내용에 대해 질문하면 답변해 드립니다

💡 **예시**
- "방금 포워딩한 내용 요약해줘"
- "이게 주가에 어떤 영향을 줄까?"
- "비트코인 최신 뉴스 검색해줘"

📋 **명령어**
/help - 도움말
/save <메시지> - 메시지 저장
/list - 저장된 메시지 목록 (최근 10개)
/listall - 저장된 메시지 전체 목록
/delete <번호> - 메시지 삭제
/clear - 저장된 메시지 전체 삭제
/search <검색어> - 웹 검색
/x <검색어> - X(트위터) 검색
"""
    await update.message.reply_text(welcome_message, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help - 명령어 목록"""
    help_message = """📋 **명령어 목록**

/start - 봇 시작 및 사용법
/help - 이 도움말 보기
/save <메시지> - 메시지 저장
/list - 저장된 메시지 목록 (최근 10개)
/listall - 저장된 메시지 전체 목록
/delete <번호> - 메시지 삭제 (list 번호 기준)
/clear - 저장된 메시지 전체 삭제
/search <검색어> - 웹 검색
/x <검색어> - X(트위터) 검색

💬 **일반 메시지**
명령어 없이 메시지를 보내면:
- 포워딩된 메시지 → 자동 저장
- 일반 질문 → AI가 저장된 컨텍스트 + 웹/X 검색으로 답변
"""
    await update.message.reply_text(help_message, parse_mode="Markdown")


async def save_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/save - 메시지 저장"""
    if not context.args:
        await update.message.reply_text("❓ 저장할 메시지를 입력해주세요.\n예: /save 오늘 미팅 내용 정리")
        return

    user_id = update.effective_user.id
    content = " ".join(context.args)

    await save_message(user_id=user_id, content=content, is_forwarded=False)
    await update.message.reply_text("✅ 메시지가 저장되었습니다.")


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/list - 저장된 메시지 목록 (최근 10개)"""
    user_id = update.effective_user.id
    messages = await get_messages(user_id, limit=10)

    if not messages:
        await update.message.reply_text("📭 저장된 메시지가 없습니다.")
        return

    count = await get_message_count(user_id)
    response = f"📋 저장된 메시지 ({count}개 중 최근 10개)\n\n"

    for i, msg in enumerate(messages, 1):
        content_preview = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
        source = "[포워딩]" if msg["is_forwarded"] else "[직접]"
        time_str = msg["created_at"][:16] if msg["created_at"] else ""
        response += f"{i}. {source} ({time_str})\n{content_preview}\n\n"

    await update.message.reply_text(response)


async def listall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/listall - 저장된 메시지 전체 목록"""
    user_id = update.effective_user.id
    messages = await get_messages(user_id, limit=1000)

    if not messages:
        await update.message.reply_text("📭 저장된 메시지가 없습니다.")
        return

    response = f"📋 저장된 메시지 전체 ({len(messages)}개)\n\n"

    for i, msg in enumerate(messages, 1):
        content_preview = msg["content"][:80] + "..." if len(msg["content"]) > 80 else msg["content"]
        source = "[포워딩]" if msg["is_forwarded"] else "[직접]"
        time_str = msg["created_at"][:16] if msg["created_at"] else ""
        response += f"{i}. {source} ({time_str})\n{content_preview}\n\n"

        # 텔레그램 메시지 길이 제한 (4096자) 대응
        if len(response) > 3800:
            response += f"... 외 {len(messages) - i}개 더 있음"
            break

    await update.message.reply_text(response)


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/delete - 메시지 삭제"""
    if not context.args:
        await update.message.reply_text("❓ 삭제할 메시지 번호를 입력해주세요.\n예: /delete 1\n\n/list 또는 /listall 에서 번호 확인")
        return

    try:
        index = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 올바른 숫자를 입력해주세요.\n예: /delete 1")
        return

    user_id = update.effective_user.id
    success = await delete_message_by_index(user_id, index)

    if success:
        await update.message.reply_text(f"🗑️ {index}번 메시지가 삭제되었습니다.")
    else:
        await update.message.reply_text(f"❌ {index}번 메시지를 찾을 수 없습니다.")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/clear - 저장된 메시지 삭제"""
    user_id = update.effective_user.id
    deleted_count = await clear_messages(user_id)

    if deleted_count > 0:
        await update.message.reply_text(f"🗑️ {deleted_count}개의 메시지가 삭제되었습니다.")
    else:
        await update.message.reply_text("📭 삭제할 메시지가 없습니다.")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/search - 웹 검색"""
    if not context.args:
        await update.message.reply_text("❓ 검색어를 입력해주세요.\n예: /search 비트코인 뉴스")
        return

    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 웹에서 '{query}' 검색 중...")

    try:
        result = await search_web_only(query)
        search_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await update.message.reply_text(f"🌐 **웹 검색 결과** ({search_time})\n\n{result}", parse_mode="Markdown")
    except SearchError as e:
        await update.message.reply_text(f"❌ **웹 검색 실패**\n\n{str(e)}")


async def x_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/x - X(트위터) 검색"""
    if not context.args:
        await update.message.reply_text("❓ 검색어를 입력해주세요.\n예: /x 비트코인")
        return

    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 X에서 '{query}' 검색 중...")

    try:
        result = await search_x_only(query)
        search_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await update.message.reply_text(f"🐦 **X 검색 결과** ({search_time})\n\n{result}", parse_mode="Markdown")
    except SearchError as e:
        await update.message.reply_text(f"❌ **X 검색 실패**\n\n{str(e)}")


# ==================== 메시지 핸들러 ====================

async def handle_forwarded_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """포워딩된 메시지 저장"""
    user_id = update.effective_user.id
    message = update.message

    # 포워딩 출처 정보 추출
    forward_from = None
    if message.forward_from:
        forward_from = message.forward_from.full_name
    elif message.forward_from_chat:
        forward_from = message.forward_from_chat.title or message.forward_from_chat.username
    elif message.forward_sender_name:
        forward_from = message.forward_sender_name

    content = message.text or message.caption or "[미디어 메시지]"

    # DB에 저장
    await save_message(
        user_id=user_id,
        content=content,
        is_forwarded=True,
        forward_from=forward_from
    )

    source_text = f" (출처: {forward_from})" if forward_from else ""
    await update.message.reply_text(f"✅ 메시지가 저장되었습니다{source_text}")


async def handle_regular_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """일반 메시지 처리 - AI 의도 분류 후 실행"""
    user_id = update.effective_user.id
    user_message = update.message.text

    # AI 기반 의도 분류 (작은 모델 사용)
    intent, arg = await classify_intent(user_message)

    # 의도별 처리
    if intent == UserIntent.SAVE_MESSAGE:
        if not arg:
            await update.message.reply_text("❓ 저장할 내용을 입력해주세요.\n예: '안녕하세요' 저장해줘")
            return
        await save_message(user_id=user_id, content=arg, is_forwarded=False)
        await update.message.reply_text(f"✅ 메시지가 저장되었습니다.\n\n저장된 내용: {arg}")
        return

    if intent == UserIntent.LIST_MESSAGES:
        messages = await get_messages(user_id, limit=10)
        if not messages:
            await update.message.reply_text("📭 저장된 메시지가 없습니다.")
            return
        count = await get_message_count(user_id)
        response = f"📋 저장된 메시지 ({count}개 중 최근 10개)\n\n"
        for i, msg in enumerate(messages, 1):
            content_preview = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            source = "[포워딩]" if msg["is_forwarded"] else "[직접]"
            time_str = msg["created_at"][:16] if msg["created_at"] else ""
            response += f"{i}. {source} ({time_str})\n{content_preview}\n\n"
        await update.message.reply_text(response)
        return

    if intent == UserIntent.LIST_ALL_MESSAGES:
        messages = await get_messages(user_id, limit=1000)
        if not messages:
            await update.message.reply_text("📭 저장된 메시지가 없습니다.")
            return
        response = f"📋 저장된 메시지 전체 ({len(messages)}개)\n\n"
        for i, msg in enumerate(messages, 1):
            content_preview = msg["content"][:80] + "..." if len(msg["content"]) > 80 else msg["content"]
            source = "[포워딩]" if msg["is_forwarded"] else "[직접]"
            time_str = msg["created_at"][:16] if msg["created_at"] else ""
            response += f"{i}. {source} ({time_str})\n{content_preview}\n\n"
            if len(response) > 3800:
                response += f"... 외 {len(messages) - i}개 더 있음"
                break
        await update.message.reply_text(response)
        return

    if intent == UserIntent.CLEAR_MESSAGES:
        deleted_count = await clear_messages(user_id)
        if deleted_count > 0:
            await update.message.reply_text(f"🗑️ {deleted_count}개의 메시지가 삭제되었습니다.")
        else:
            await update.message.reply_text("📭 삭제할 메시지가 없습니다.")
        return

    if intent == UserIntent.DELETE_MESSAGE:
        if not arg:
            await update.message.reply_text("❓ 삭제할 메시지 번호를 입력해주세요.\n예: 1번 삭제해줘")
            return
        delete_index = int(arg)
        success = await delete_message_by_index(user_id, delete_index)
        if success:
            await update.message.reply_text(f"🗑️ {delete_index}번 메시지가 삭제되었습니다.")
        else:
            await update.message.reply_text(f"❌ {delete_index}번 메시지를 찾을 수 없습니다.")
        return

    if intent == UserIntent.HELP:
        help_message = """📋 명령어 목록

/save <메시지> - 메시지 저장
/list - 저장된 메시지 목록 (최근 10개)
/listall - 저장된 메시지 전체 목록
/delete <번호> - 메시지 삭제 (list 번호 기준)
/clear - 저장된 메시지 전체 삭제
/search <검색어> - 웹 검색
/x <검색어> - X(트위터) 검색

포워딩된 메시지는 자동 저장됩니다.
일반 질문은 AI가 답변합니다."""
        await update.message.reply_text(help_message)
        return

    # QUESTION: AI Agent 호출
    await update.message.reply_text("🤔 생각 중...")

    async def send_status(message: str):
        await update.message.reply_text(message)

    try:
        response = await get_ai_response(user_id, user_message, send_status)
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ 응답 생성 실패\n\n{str(e)}")


# ==================== 봇 초기화 ====================

def create_bot_application() -> Application:
    """봇 애플리케이션 생성"""
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # 명령어 핸들러 등록
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("save", save_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("listall", listall_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("x", x_search_command))

    # 포워딩된 메시지 핸들러 (일반 메시지보다 먼저 체크)
    application.add_handler(
        MessageHandler(filters.FORWARDED & filters.TEXT, handle_forwarded_message)
    )

    # 일반 텍스트 메시지 핸들러
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_regular_message)
    )

    return application


