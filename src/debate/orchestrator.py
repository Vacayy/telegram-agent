"""Orchestrator - AI 토론 진행 총괄"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from google import genai

import config
from src.debate.persona import Persona, PersonaGenerator


@dataclass
class Statement:
    """토론 발언"""
    persona_id: str
    round_number: int
    round_type: str          # "opening", "question", "rebuttal", "refinement", "closing"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DebateSession:
    """토론 세션"""
    id: str
    query: str
    personas: list[Persona]
    statements: list[Statement] = field(default_factory=list)
    status: str = "preparing"  # "preparing", "debating", "completed"
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None


@dataclass
class DebateReport:
    """토론 결과 리포트"""
    query: str
    personas: list[Persona]
    consensus: list[str]        # 합의점
    disputes: list[str]         # 쟁점
    conclusion: str             # 종합 결론
    recommendations: list[str]  # 실행 제안
    duration_seconds: float
    total_statements: int


# 라운드별 설정
ROUND_CONFIG = {
    "opening": {
        "name": "입장 발표",
        "emoji": "📢",
        "instruction": """질문에 대한 당신의 입장을 밝히세요.

형식:
- 핵심 주장 (1문장)
- 근거 (2-3개)

500자 이내로 답변하세요."""
    },
    "question": {
        "name": "교차 질문",
        "emoji": "❓",
        "instruction": """다른 참가자들의 입장을 읽었습니다:

{other_statements}

각 참가자에게 논리적 허점이나 불확실한 가정을 지적하는 질문을 1개씩 던지세요.
"왜?", "어떻게?", "근거는?" 형태의 날카로운 질문으로.

500자 이내로 답변하세요."""
    },
    "rebuttal": {
        "name": "반박 및 방어",
        "emoji": "🛡️",
        "instruction": """당신에게 다음 질문이 제기되었습니다:

{questions_to_me}

각 질문에 구체적으로 답변하고, 필요하면 추가 근거로 입장을 보강하세요.
상대방의 지적이 타당하다면 인정하되, 전체 논지는 유지하세요.

500자 이내로 답변하세요."""
    },
    "refinement": {
        "name": "입장 조율",
        "emoji": "🤝",
        "instruction": """지금까지의 토론을 바탕으로:

1. 다른 참가자 의견 중 타당한 부분을 인정하세요
2. 자신의 초기 입장에서 수정/보완할 부분이 있다면 밝히세요
3. 세 사람이 동의할 수 있는 공통점을 제안하세요

자기 입장을 무조건 고수하지 말고, 토론의 결과로 입장이 진화할 수 있습니다.

500자 이내로 답변하세요."""
    },
    "closing": {
        "name": "최종 정리",
        "emoji": "📝",
        "instruction": """토론을 마무리하며:

1. 토론을 통해 도달한 최종 입장
2. 사용자에게 전달할 핵심 인사이트 1가지
3. 구체적인 제안이나 행동 지침

명확하고 실용적으로 정리하세요.

500자 이내로 답변하세요."""
    },
}


class DebateOrchestrator:
    """토론 진행자"""

    def __init__(self):
        self.client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)
        self.persona_generator = PersonaGenerator()
        self.session: Optional[DebateSession] = None
        self.status_callback: Optional[Callable] = None  # 상태 업데이트 (edit) - (text, entities) 튜플
        self.completed_rounds: list[tuple[str, int, list]] = []  # (round_type, round_num, statements)

    async def start_debate(
        self,
        query: str,
        status_callback: Optional[Callable] = None,
        use_dynamic_personas: bool = True
    ) -> DebateReport:
        """토론 시작 및 진행

        Args:
            query: 토론 주제
            status_callback: 상태 업데이트 콜백 (async) - (text, entities) 튜플 전달
            use_dynamic_personas: 동적 페르소나 생성 여부

        Returns:
            DebateReport: 토론 결과 리포트
        """
        self.status_callback = status_callback
        self.completed_rounds = []
        start_time = datetime.now()

        # 1. 페르소나 생성
        await self._update_status("🎭 페르소나 구성 중...")
        personas = await self.persona_generator.generate(query, use_dynamic_personas)

        # 세션 초기화
        self.session = DebateSession(
            id=f"debate_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            query=query,
            personas=personas,
            status="debating"
        )

        # 페르소나 정보 표시
        persona_info = self._format_personas_info()
        await self._update_status(f"🎭 AI Debate 시작\n\n📋 주제: {query}\n\n{persona_info}")
        await asyncio.sleep(1)  # 사용자가 읽을 시간

        # 2. 5라운드 토론 진행
        rounds = ["opening", "question", "rebuttal", "refinement", "closing"]

        for i, round_type in enumerate(rounds):
            round_config = ROUND_CONFIG[round_type]
            round_num = i + 1

            # 진행 중 상태 표시 (이전 라운드는 접힘)
            await self._update_debate_status(round_num, rounds, is_processing=True)

            # 라운드 실행
            statements = await self._run_round(round_type, round_num)

            # 완료된 라운드 저장
            self.completed_rounds.append((round_type, round_num, statements))

            # 라운드 완료 상태 표시 (현재 라운드 펼침)
            await self._update_debate_status(round_num, rounds, is_processing=False)
            await asyncio.sleep(0.5)

        # 3. 최종 리포트 생성
        await self._update_status("📊 최종 리포트 생성 중...")
        self.session.status = "completed"
        self.session.end_time = datetime.now()

        report = await self._generate_report()
        report.duration_seconds = (datetime.now() - start_time).total_seconds()
        report.total_statements = len(self.session.statements)

        return report

    async def _run_round(self, round_type: str, round_num: int) -> list[Statement]:
        """라운드 실행 (3명 병렬 처리)"""
        round_config = ROUND_CONFIG[round_type]

        # 라운드 타입별 컨텍스트 준비
        contexts = self._prepare_round_contexts(round_type)

        # 3명 동시 호출
        tasks = [
            self._get_persona_response(persona, round_type, round_num, contexts.get(persona.id, ""))
            for persona in self.session.personas
        ]

        statements = await asyncio.gather(*tasks)

        # 세션에 발언 저장
        self.session.statements.extend(statements)

        return statements

    def _prepare_round_contexts(self, round_type: str) -> dict[str, str]:
        """라운드 타입별 컨텍스트 준비"""
        contexts = {}

        if round_type == "opening":
            # 초기 입장: 컨텍스트 없음
            return contexts

        elif round_type == "question":
            # 교차 질문: 다른 사람들의 opening 발언
            opening_statements = [s for s in self.session.statements if s.round_type == "opening"]
            for persona in self.session.personas:
                others = [s for s in opening_statements if s.persona_id != persona.id]
                others_text = "\n\n".join([
                    f"{self._get_persona_by_id(s.persona_id).format_header()}:\n{s.content}"
                    for s in others
                ])
                contexts[persona.id] = others_text

        elif round_type == "rebuttal":
            # 반박: 나에게 온 질문들
            question_statements = [s for s in self.session.statements if s.round_type == "question"]
            for persona in self.session.personas:
                # 다른 사람들의 질문에서 이 페르소나에게 온 부분 추출
                questions_to_me = []
                for s in question_statements:
                    if s.persona_id != persona.id:
                        # 질문 내용에서 이 페르소나 관련 부분 찾기
                        questions_to_me.append(
                            f"{self._get_persona_by_id(s.persona_id).format_header()}의 질문:\n{s.content}"
                        )
                contexts[persona.id] = "\n\n".join(questions_to_me)

        elif round_type in ["refinement", "closing"]:
            # 조율/마무리: 전체 토론 히스토리 요약
            all_statements = self.session.statements
            summary = self._summarize_debate_history(all_statements)
            for persona in self.session.personas:
                contexts[persona.id] = summary

        return contexts

    def _summarize_debate_history(self, statements: list[Statement]) -> str:
        """토론 히스토리 요약"""
        by_persona = {}
        for s in statements:
            if s.persona_id not in by_persona:
                by_persona[s.persona_id] = []
            by_persona[s.persona_id].append(s)

        summary_parts = []
        for persona_id, stmts in by_persona.items():
            persona = self._get_persona_by_id(persona_id)
            latest = stmts[-1] if stmts else None
            if latest:
                summary_parts.append(f"{persona.format_header()}의 현재 입장:\n{latest.content[:300]}...")

        return "\n\n".join(summary_parts)

    async def _get_persona_response(
        self,
        persona: Persona,
        round_type: str,
        round_num: int,
        context: str
    ) -> Statement:
        """개별 페르소나의 응답 생성"""
        round_config = ROUND_CONFIG[round_type]

        # 프롬프트 구성
        instruction = round_config["instruction"]
        if "{other_statements}" in instruction:
            instruction = instruction.format(other_statements=context)
        elif "{questions_to_me}" in instruction:
            instruction = instruction.format(questions_to_me=context)

        prompt = f"""질문: {self.session.query}

{instruction}"""

        try:
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={
                    "system_instruction": persona.system_prompt,
                    "temperature": 0.8,
                    "max_output_tokens": 600,
                }
            )

            content = response.text.strip()

        except Exception as e:
            print(f"[Debate] {persona.name} 응답 생성 실패: {e}")
            content = f"(응답 생성 중 오류 발생: {e})"

        return Statement(
            persona_id=persona.id,
            round_number=round_num,
            round_type=round_type,
            content=content
        )

    async def _generate_report(self) -> DebateReport:
        """최종 리포트 생성"""
        # 토론 내용 정리
        debate_summary = self._compile_debate_summary()

        prompt = f"""다음 토론을 분석하여 최종 리포트를 작성하세요.

토론 주제: {self.session.query}

참가자:
{chr(10).join([f"- {p.emoji} {p.name} ({p.role})" for p in self.session.personas])}

토론 내용:
{debate_summary}

다음 JSON 형식으로 응답하세요:
{{
    "consensus": ["합의점 1", "합의점 2"],
    "disputes": ["쟁점 1", "쟁점 2"],
    "conclusion": "종합 결론 (2-3문장)",
    "recommendations": ["제안 1", "제안 2"]
}}

- 합의점: 세 참가자 모두 동의한 내용
- 쟁점: 의견이 갈린 핵심 포인트
- 결론: 토론 결과를 종합한 균형 잡힌 판단
- 제안: 사용자를 위한 구체적 행동 지침
"""

        try:
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "temperature": 0.5,
                }
            )

            result = json.loads(response.text)

            return DebateReport(
                query=self.session.query,
                personas=self.session.personas,
                consensus=result.get("consensus", []),
                disputes=result.get("disputes", []),
                conclusion=result.get("conclusion", "결론을 도출하지 못했습니다."),
                recommendations=result.get("recommendations", []),
                duration_seconds=0,
                total_statements=0
            )

        except Exception as e:
            print(f"[Debate] 리포트 생성 실패: {e}")
            return DebateReport(
                query=self.session.query,
                personas=self.session.personas,
                consensus=["리포트 생성 중 오류 발생"],
                disputes=[],
                conclusion=str(e),
                recommendations=[],
                duration_seconds=0,
                total_statements=0
            )

    def _compile_debate_summary(self) -> str:
        """토론 내용 컴파일"""
        parts = []
        current_round = 0

        for statement in self.session.statements:
            if statement.round_number != current_round:
                current_round = statement.round_number
                round_config = ROUND_CONFIG.get(statement.round_type, {})
                parts.append(f"\n=== Round {current_round}: {round_config.get('name', '')} ===\n")

            persona = self._get_persona_by_id(statement.persona_id)
            parts.append(f"{persona.format_header()}:\n{statement.content}\n")

        return "\n".join(parts)

    def _get_persona_by_id(self, persona_id: str) -> Persona:
        """ID로 페르소나 찾기"""
        for p in self.session.personas:
            if p.id == persona_id:
                return p
        return self.session.personas[0]

    def _format_personas_info(self) -> str:
        """페르소나 정보 포맷"""
        lines = ["👥 참가자"]
        for p in self.session.personas:
            lines.append(f"• {p.emoji} {p.name} - {p.role}")
        return "\n".join(lines)

    def _format_progress(self, current: int, rounds: list) -> str:
        """진행 상황 포맷"""
        lines = []
        for i, round_type in enumerate(rounds):
            round_num = i + 1
            round_config = ROUND_CONFIG[round_type]
            if round_num < current:
                lines.append(f"✅ Round {round_num}: {round_config['name']}")
            elif round_num == current:
                lines.append(f"🔄 Round {round_num}: {round_config['name']}")
            else:
                lines.append(f"⏳ Round {round_num}: {round_config['name']}")
        return "\n".join(lines)

    def _format_round_result(self, round_type: str, round_num: int, statements: list[Statement]) -> str:
        """라운드 결과 포맷"""
        round_config = ROUND_CONFIG[round_type]
        lines = [f"{round_config['emoji']} Round {round_num}: {round_config['name']}\n"]

        for statement in statements:
            persona = self._get_persona_by_id(statement.persona_id)
            # 내용이 길면 축약
            content = statement.content
            if len(content) > 300:
                content = content[:300] + "..."
            lines.append(f"{persona.emoji} {persona.name}:\n{content}\n")

        return "\n".join(lines)

    async def _update_status(self, message: str, entities: list = None):
        """상태 업데이트 (기존 메시지 edit)"""
        if self.status_callback:
            try:
                await self.status_callback(message, entities or [])
            except Exception as e:
                print(f"[Debate] 상태 업데이트 실패: {e}")

    async def _update_debate_status(self, current_round: int, rounds: list, is_processing: bool):
        """토론 진행 상태 업데이트 (이전 라운드는 접힘, 현재는 펼침)"""
        from telegram import MessageEntity

        parts = []
        entities = []
        current_offset = 0

        # 헤더 (주제는 100자 제한)
        query_display = self.session.query[:100] + "..." if len(self.session.query) > 100 else self.session.query
        header = f"🎭 AI Debate 진행 중...\n\n📋 주제: {query_display}\n\n"
        parts.append(header)
        current_offset += len(header)

        # 진행 바
        progress = self._format_progress(current_round, rounds) + "\n\n"
        parts.append(progress)
        current_offset += len(progress)

        # 완료된 라운드들 (접힘)
        for round_type, round_num, statements in self.completed_rounds:
            round_config = ROUND_CONFIG[round_type]

            # 라운드 헤더
            round_header = f"✅ Round {round_num}: {round_config['name']}\n"
            parts.append(round_header)
            current_offset += len(round_header)

            # 라운드 내용 (ExpandableBlockQuote로 접기)
            round_content = ""
            for statement in statements:
                persona = self._get_persona_by_id(statement.persona_id)
                content = statement.content
                if len(content) > 200:
                    content = content[:200] + "..."
                round_content += f"{persona.emoji} {persona.name}:\n{content}\n\n"

            if round_content:
                # ExpandableBlockQuote entity 추가
                entities.append(MessageEntity(
                    type=MessageEntity.EXPANDABLE_BLOCKQUOTE,
                    offset=current_offset,
                    length=len(round_content) - 1  # 마지막 줄바꿈 제외
                ))
                parts.append(round_content)
                current_offset += len(round_content)

        # 현재 라운드
        round_config = ROUND_CONFIG[rounds[current_round - 1]]
        if is_processing:
            # 진행 중
            current_text = f"🔄 Round {current_round}: {round_config['name']} 진행 중...\n"
            parts.append(current_text)
        else:
            # 방금 완료 (펼쳐서 표시)
            current_text = f"📢 Round {current_round}: {round_config['name']}\n"
            parts.append(current_text)
            current_offset += len(current_text)

            # 현재 라운드 결과 (접지 않고 펼침)
            if self.completed_rounds:
                _, _, statements = self.completed_rounds[-1]
                for statement in statements:
                    persona = self._get_persona_by_id(statement.persona_id)
                    content = statement.content
                    if len(content) > 300:
                        content = content[:300] + "..."
                    stmt_text = f"{persona.emoji} {persona.name}:\n{content}\n\n"
                    parts.append(stmt_text)
                    current_offset += len(stmt_text)

        text = "".join(parts)

        # 텔레그램 메시지 길이 제한
        if len(text) > 4000:
            text = text[:4000] + "\n\n... (내용 생략)"
            # entity 범위 조정
            entities = [e for e in entities if e.offset + e.length <= 4000]

        await self._update_status(text, entities)

    def format_final_message_with_report(self, report_text: str) -> tuple[str, list]:
        """모든 라운드(접힘) + 최종 리포트를 하나의 메시지로 포맷

        Args:
            report_text: format_debate_report()로 생성된 리포트 텍스트

        Returns:
            (text, entities) 튜플
        """
        from telegram import MessageEntity

        parts = []
        entities = []
        current_offset = 0

        # 헤더 (주제는 100자 제한)
        query_display = self.session.query[:100] + "..." if len(self.session.query) > 100 else self.session.query
        header = f"🎭 AI Debate 완료!\n\n📋 주제: {query_display}\n\n"
        parts.append(header)
        current_offset += len(header)

        # 모든 라운드 (접힘)
        for round_type, round_num, statements in self.completed_rounds:
            round_config = ROUND_CONFIG[round_type]

            # 라운드 헤더
            round_header = f"✅ Round {round_num}: {round_config['name']}\n"
            parts.append(round_header)
            current_offset += len(round_header)

            # 라운드 내용 (ExpandableBlockQuote로 접기)
            round_content = ""
            for statement in statements:
                persona = self._get_persona_by_id(statement.persona_id)
                content = statement.content
                if len(content) > 200:
                    content = content[:200] + "..."
                round_content += f"{persona.emoji} {persona.name}:\n{content}\n\n"

            if round_content:
                entities.append(MessageEntity(
                    type=MessageEntity.EXPANDABLE_BLOCKQUOTE,
                    offset=current_offset,
                    length=len(round_content) - 1
                ))
                parts.append(round_content)
                current_offset += len(round_content)

        # 구분선
        separator = "━" * 20 + "\n\n"
        parts.append(separator)
        current_offset += len(separator)

        # 최종 리포트 (펼침)
        parts.append(report_text)

        return "".join(parts), entities


def format_debate_report(report: DebateReport) -> str:
    """최종 리포트를 텔레그램 메시지로 포맷"""
    lines = [
        "🎭 **AI Debate 결과 리포트**",
        "━" * 20,
        "",
        f"📋 **주제**: {report.query}",
        "",
        "👥 **참가자**",
    ]

    for p in report.personas:
        lines.append(f"• {p.emoji} {p.name} - {p.role}")

    lines.extend([
        "",
        "━" * 20,
        "",
    ])

    # 합의점
    if report.consensus:
        lines.append("🤝 **합의점**")
        for item in report.consensus:
            lines.append(f"• {item}")
        lines.append("")

    # 쟁점
    if report.disputes:
        lines.append("⚔️ **쟁점**")
        for item in report.disputes:
            lines.append(f"• {item}")
        lines.append("")

    # 결론
    lines.extend([
        "📊 **종합 결론**",
        report.conclusion,
        "",
    ])

    # 제안
    if report.recommendations:
        lines.append("💡 **실행 제안**")
        for item in report.recommendations:
            lines.append(f"• {item}")
        lines.append("")

    # 통계
    lines.extend([
        "━" * 20,
        f"⏱️ 토론 시간: {report.duration_seconds:.1f}초",
        f"💬 총 발언: {report.total_statements}개",
    ])

    return "\n".join(lines)
