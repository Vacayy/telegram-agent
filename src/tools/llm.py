"""LLM 기반 도구 - 번역, 요약, 분석 (Gemini 사용)"""

from google import genai
import config


async def translate(text: str, to: str = "ko") -> str:
    """텍스트 번역

    Args:
        text: 번역할 텍스트
        to: 대상 언어 (기본값: ko - 한국어)

    Returns:
        번역된 텍스트
    """
    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    language_map = {
        "ko": "한국어",
        "en": "영어",
        "ja": "일본어",
        "zh": "중국어",
    }
    target_lang = language_map.get(to, to)

    prompt = f"""다음 텍스트를 {target_lang}로 번역해주세요.
원문의 의미를 정확히 전달하되, 자연스러운 표현을 사용하세요.
번역문만 출력하세요.

텍스트:
{text}

번역:"""

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"[번역 오류] {type(e).__name__}: {e}")
        return f"번역 실패: {str(e)}"


async def summarize(text: str) -> str:
    """텍스트 요약

    Args:
        text: 요약할 텍스트

    Returns:
        요약된 텍스트
    """
    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    prompt = f"""다음 텍스트를 핵심 내용 위주로 간결하게 요약해주세요.
중요한 정보를 빠뜨리지 않으면서 짧게 정리하세요.
요약문만 출력하세요.

텍스트:
{text}

요약:"""

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"[요약 오류] {type(e).__name__}: {e}")
        return f"요약 실패: {str(e)}"


async def analyze(text: str, question: str = None) -> str:
    """텍스트 분석

    Args:
        text: 분석할 텍스트
        question: 분석 관점이나 질문 (선택)

    Returns:
        분석 결과
    """
    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    if question:
        prompt = f"""다음 텍스트를 분석하고 질문에 답변해주세요.

텍스트:
{text}

질문: {question}

분석:"""
    else:
        prompt = f"""다음 텍스트의 핵심 내용과 의미를 분석해주세요.
주요 포인트, 맥락, 의미를 설명하세요.

텍스트:
{text}

분석:"""

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"[분석 오류] {type(e).__name__}: {e}")
        return f"분석 실패: {str(e)}"
