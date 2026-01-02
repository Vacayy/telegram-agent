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
    print(f"\n{'─'*40}")
    print(f"[LLM translate] 시작")
    print(f"[LLM translate] 대상 언어: {to}")
    print(f"[LLM translate] 입력 텍스트 길이: {len(text)}자")
    print(f"[LLM translate] 입력 미리보기: {text[:100]}...")
    print(f"[LLM translate] 모델: gemini-2.0-flash")

    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    language_map = {
        "ko": "한국어",
        "en": "영어",
        "ja": "일본어",
        "zh": "중국어",
    }
    target_lang = language_map.get(to, to)
    print(f"[LLM translate] 대상 언어명: {target_lang}")

    prompt = f"""다음 텍스트를 {target_lang}로 번역해주세요.
원문의 의미를 정확히 전달하되, 자연스러운 표현을 사용하세요.
번역문만 출력하세요.

텍스트:
{text}

번역:"""

    try:
        print(f"[LLM translate] API 호출 중...")
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        result = response.text.strip()
        print(f"[LLM translate] 완료: {len(result)}자")
        print(f"[LLM translate] 결과 미리보기: {result[:100]}...")
        print(f"{'─'*40}\n")
        return result
    except Exception as e:
        print(f"[LLM translate] 오류: {type(e).__name__}: {e}")
        print(f"{'─'*40}\n")
        return f"번역 실패: {str(e)}"


async def summarize(text: str, language: str = "same") -> str:
    """텍스트 요약

    Args:
        text: 요약할 텍스트
        language: 출력 언어
            - "same": 입력 텍스트와 동일한 언어로 출력 (기본값)
            - "ko": 한국어로 요약
            - "en": 영어로 요약
            - "ja": 일본어로 요약
            - "zh": 중국어로 요약

    Returns:
        요약된 텍스트
    """
    print(f"\n{'─'*40}")
    print(f"[LLM summarize] 시작")
    print(f"[LLM summarize] 출력 언어: {language}")
    print(f"[LLM summarize] 입력 텍스트 길이: {len(text)}자")
    print(f"[LLM summarize] 입력 미리보기: {text[:100]}...")
    print(f"[LLM summarize] 모델: gemini-2.0-flash")

    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    # 언어 지시문 생성
    language_map = {
        "same": "입력 텍스트와 동일한 언어로",
        "ko": "한국어로",
        "en": "영어로",
        "ja": "일본어로",
        "zh": "중국어로",
    }
    lang_instruction = language_map.get(language, "입력 텍스트와 동일한 언어로")
    print(f"[LLM summarize] 언어 지시문: '{lang_instruction}'")

    prompt = f"""다음 텍스트를 핵심 내용 위주로 간결하게 요약해주세요.
중요한 정보를 빠뜨리지 않으면서 짧게 정리하세요.
{lang_instruction} 요약문만 출력하세요.

텍스트:
{text}

요약:"""

    try:
        print(f"[LLM summarize] API 호출 중...")
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        result = response.text.strip()
        print(f"[LLM summarize] 완료: {len(result)}자")
        print(f"[LLM summarize] 결과 미리보기: {result[:100]}...")
        print(f"{'─'*40}\n")
        return result
    except Exception as e:
        print(f"[LLM summarize] 오류: {type(e).__name__}: {e}")
        print(f"{'─'*40}\n")
        return f"요약 실패: {str(e)}"


async def analyze(text: str, question: str = None) -> str:
    """텍스트 분석

    Args:
        text: 분석할 텍스트
        question: 분석 관점이나 질문 (선택)

    Returns:
        분석 결과
    """
    print(f"\n{'─'*40}")
    print(f"[LLM analyze] 시작")
    print(f"[LLM analyze] 질문: {question}")
    print(f"[LLM analyze] 입력 텍스트 길이: {len(text)}자")
    print(f"[LLM analyze] 입력 미리보기: {text[:100]}...")
    print(f"[LLM analyze] 모델: gemini-2.0-flash")

    client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    if question:
        print(f"[LLM analyze] 모드: 질문 기반 분석")
        prompt = f"""다음 텍스트를 분석하고 질문에 답변해주세요.

텍스트:
{text}

질문: {question}

분석:"""
    else:
        print(f"[LLM analyze] 모드: 일반 분석")
        prompt = f"""다음 텍스트의 핵심 내용과 의미를 분석해주세요.
주요 포인트, 맥락, 의미를 설명하세요.

텍스트:
{text}

분석:"""

    try:
        print(f"[LLM analyze] API 호출 중...")
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        result = response.text.strip()
        print(f"[LLM analyze] 완료: {len(result)}자")
        print(f"[LLM analyze] 결과 미리보기: {result[:100]}...")
        print(f"{'─'*40}\n")
        return result
    except Exception as e:
        print(f"[LLM analyze] 오류: {type(e).__name__}: {e}")
        print(f"{'─'*40}\n")
        return f"분석 실패: {str(e)}"
