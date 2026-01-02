import asyncio
import logging

from src.bot import create_bot_application
from src.database import init_db

# 로깅 설정
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application):
    """봇 초기화 후 실행되는 콜백"""
    await init_db()
    print("🤖 봇이 시작되었습니다...")


def main():
    """메인 진입점"""
    logger.info("TeleBot 시작 중...")

    # 봇 애플리케이션 생성
    application = create_bot_application()

    # post_init 콜백 등록
    application.post_init = post_init

    # 봇 실행
    application.run_polling()


if __name__ == "__main__":
    main()
