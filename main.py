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


def main():
    """메인 진입점"""
    logger.info("TeleBot 시작 중...")

    # DB 초기화 (동기적으로)
    asyncio.get_event_loop().run_until_complete(init_db())

    # 봇 애플리케이션 생성
    application = create_bot_application()

    print("🤖 봇이 시작되었습니다...")

    # 봇 실행 (run_polling이 자체 이벤트 루프 관리)
    application.run_polling()


if __name__ == "__main__":
    main()
