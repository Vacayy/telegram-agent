"""Persona - AI 토론 참가자 정의 및 생성"""

import json
from dataclasses import dataclass, field
from typing import Optional

from google import genai

import config


@dataclass
class Persona:
    """토론 참가자 페르소나"""
    id: str                  # "optimist", "skeptic", "neutral"
    name: str                # "낙관론자"
    emoji: str               # "🐂"
    role: str                # "암호화폐 시장 전문가"
    description: str         # 상세 역할 설명
    system_prompt: str = ""  # LLM 시스템 프롬프트 (자동 생성)

    def __post_init__(self):
        """시스템 프롬프트 자동 생성"""
        if not self.system_prompt:
            self.system_prompt = f"""당신은 '{self.name}'입니다.
역할: {self.role}
특성: {self.description}

토론 규칙:
- 핵심 주장을 먼저, 근거를 뒤에 제시하세요
- 500자 이내로 간결하게 답변하세요
- 자신의 전문 분야 관점을 유지하세요
- 다른 참가자의 의견을 경청하고 건설적으로 반응하세요"""

    def format_header(self) -> str:
        """메시지 헤더 포맷"""
        return f"{self.emoji} {self.name} ({self.role})"


# 기본 페르소나 템플릿 (주제와 무관하게 사용 가능)
DEFAULT_PERSONAS = {
    "optimist": Persona(
        id="optimist",
        name="낙관론자",
        emoji="🐂",
        role="기회 분석가",
        description="긍정적 측면과 성장 가능성에 초점을 맞춥니다. 데이터에서 희망적인 신호를 찾고, 장기적 관점에서 기회를 발굴합니다."
    ),
    "skeptic": Persona(
        id="skeptic",
        name="비관론자",
        emoji="🐻",
        role="리스크 분석가",
        description="잠재적 위험과 문제점을 파악합니다. 비판적 시각으로 허점을 찾고, 최악의 시나리오를 대비합니다."
    ),
    "neutral": Persona(
        id="neutral",
        name="중립자",
        emoji="⚖️",
        role="균형 분석가",
        description="양쪽 의견을 객관적으로 평가합니다. 데이터 기반으로 균형 잡힌 시각을 제공하고, 합의점을 도출합니다."
    ),
}


class PersonaGenerator:
    """주제에 맞는 페르소나를 동적으로 생성"""

    GENERATION_PROMPT = """사용자의 질문에 대해 토론할 3명의 전문가 페르소나를 생성하세요.

질문: {query}

요구사항:
1. 서로 다른 관점을 가진 3명의 전문가
2. 한 명은 긍정적(optimist), 한 명은 비판적(skeptic), 한 명은 중립적(neutral) 관점
3. 질문 주제에 맞는 구체적인 전문 분야 설정

JSON 형식으로만 응답하세요:
{{
    "personas": [
        {{
            "id": "optimist",
            "name": "낙관론자",
            "emoji": "🐂",
            "role": "구체적 전문 분야",
            "description": "이 전문가의 특성과 관점 설명 (1-2문장)"
        }},
        {{
            "id": "skeptic",
            "name": "비관론자",
            "emoji": "🐻",
            "role": "구체적 전문 분야",
            "description": "이 전문가의 특성과 관점 설명 (1-2문장)"
        }},
        {{
            "id": "neutral",
            "name": "중립자",
            "emoji": "⚖️",
            "role": "구체적 전문 분야",
            "description": "이 전문가의 특성과 관점 설명 (1-2문장)"
        }}
    ]
}}
"""

    def __init__(self):
        self.client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)

    async def generate(self, query: str, use_dynamic: bool = True) -> list[Persona]:
        """주제에 맞는 페르소나 3명 생성

        Args:
            query: 토론 주제
            use_dynamic: True면 주제에 맞게 동적 생성, False면 기본 템플릿 사용

        Returns:
            3명의 Persona 리스트
        """
        if not use_dynamic:
            return list(DEFAULT_PERSONAS.values())

        try:
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=self.GENERATION_PROMPT.format(query=query),
                config={
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                }
            )

            result = json.loads(response.text)
            personas = []

            for p in result.get("personas", []):
                personas.append(Persona(
                    id=p["id"],
                    name=p["name"],
                    emoji=p["emoji"],
                    role=p["role"],
                    description=p["description"]
                ))

            if len(personas) == 3:
                print(f"[Persona] 동적 생성 완료: {[p.role for p in personas]}")
                return personas

        except Exception as e:
            print(f"[Persona] 동적 생성 실패, 기본 템플릿 사용: {e}")

        # Fallback: 기본 템플릿
        return list(DEFAULT_PERSONAS.values())

    def get_default_personas(self) -> list[Persona]:
        """기본 페르소나 템플릿 반환"""
        return list(DEFAULT_PERSONAS.values())
