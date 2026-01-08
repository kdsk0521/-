"""
Lorekeeper TRPG Bot - Persona Module (Right Hemisphere) v2.0
창작, 서사, 캐릭터 연기를 담당하는 '우뇌' 모듈입니다.

[v2.0 변경사항]
- 중복 섹션 통합 (TROPE 금지, 플레이어 보호 등)
- 구체적 예시 대폭 보강
- 다중 플레이어 완전 지원
- 섹션 구조 간소화

Architecture:
    - Left Hemisphere (memory_system.py): Logic, Analysis, Causality
    - Right Hemisphere (persona.py): Creativity, Narrative, Character
"""

import asyncio
import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from google import genai
from google.genai import types

# =========================================================
# 상수 정의
# =========================================================
MAX_RETRY_COUNT = 3
RETRY_DELAY_SECONDS = 1
DEFAULT_TEMPERATURE = 1.0

# =========================================================
# THINKING LEVEL 시스템
# =========================================================
THINKING_LEVELS = {
    "minimal": 0,  # 단순 행동, 이동
    "low": 1,      # 일반 대화
    "medium": 2,   # 전투, NPC 상호작용
    "high": 3      # 추리, 복잡한 상황
}

DEFAULT_THINKING_LEVEL = "low"

# Thinking Level별 응답 길이 (글자 수)
MIN_RESPONSE_LENGTH = {
    "minimal": 300,
    "low": 500,
    "medium": 800,
    "high": 1200
}

MAX_RESPONSE_LENGTH = {
    "minimal": 600,
    "low": 1000,
    "medium": 1500,
    "high": 2500
}

# 복잡도 판단 키워드
COMPLEXITY_KEYWORDS = {
    "high": [
        "추리", "수수께끼", "단서", "증거", "조사", "분석",
        "설득", "협상", "거래", "계약", "협박",
        "작전", "전략", "계획", "함정", "매복", "기습",
        "선택", "결정", "운명", "갈림길",
        "의식", "주문", "봉인", "소환",
    ],
    "medium": [
        "공격", "방어", "회피", "전투", "싸움",
        "대화", "질문", "요청", "부탁", "거절",
        "자물쇠", "함정 해제", "치료", "수리", "제작",
        "수색", "탐색", "찾다", "발견", "숨다",
    ],
    "low": ["말하다", "묻다", "대답", "인사"],
    "minimal": [
        "이동", "걷다", "뛰다", "가다", "들어가다", "나가다",
        "앉다", "서다", "눕다", "기다리다", "쉬다",
        "보다", "듣다", "바라보다",
    ]
}

COMPLEXITY_BOOSTERS = {
    "danger_keywords": ["위험", "죽음", "생사", "절체절명"],
    "danger_boost": 1,
    "multi_npc_pattern": r"(와|과|,|그리고).*(에게|와|과)",
    "multi_npc_boost": 1,
    "long_input_threshold": 100,
    "long_input_boost": 1,
}


def analyze_input_complexity(user_input: str, context: Dict[str, Any] = None) -> Tuple[str, str]:
    """사용자 입력의 복잡도를 분석하여 Thinking Level을 결정합니다."""
    if not user_input:
        return DEFAULT_THINKING_LEVEL, "기본값"
    
    input_lower = user_input.lower()
    score = 0
    reasons = []
    
    # 키워드 점수
    for level, keywords in COMPLEXITY_KEYWORDS.items():
        level_score = THINKING_LEVELS.get(level, 1)
        for keyword in keywords:
            if keyword in input_lower:
                if level_score > score:
                    score = level_score
                    reasons = [f"키워드: {keyword}"]
                break
    
    # 부스터
    for danger_kw in COMPLEXITY_BOOSTERS["danger_keywords"]:
        if danger_kw in input_lower:
            score += COMPLEXITY_BOOSTERS["danger_boost"]
            reasons.append("위험 상황")
            break
    
    if re.search(COMPLEXITY_BOOSTERS["multi_npc_pattern"], user_input):
        score += COMPLEXITY_BOOSTERS["multi_npc_boost"]
        reasons.append("다중 대상")
    
    if len(user_input) > COMPLEXITY_BOOSTERS["long_input_threshold"]:
        score += COMPLEXITY_BOOSTERS["long_input_boost"]
        reasons.append("복잡한 행동")
    
    # 컨텍스트
    if context:
        risk_level = context.get("risk_level", "").lower()
        if "high" in risk_level or "extreme" in risk_level:
            score += 1
            reasons.append("고위험 지역")
        
        doom = context.get("doom", 0)
        if doom >= 70:
            score += 1
            reasons.append(f"Doom {doom}%")
    
    # 최종 레벨
    if score >= 3:
        level = "high"
    elif score >= 2:
        level = "medium"
    elif score >= 1:
        level = "low"
    else:
        level = "minimal"
    
    reason = ", ".join(reasons[:3]) if reasons else "기본값"
    return level, reason


def get_thinking_config(thinking_level: str = DEFAULT_THINKING_LEVEL) -> Dict[str, Any]:
    """Thinking Level 설정을 반환합니다."""
    return {"thinking_level": thinking_level}


def get_length_requirements(thinking_level: str = DEFAULT_THINKING_LEVEL) -> Dict[str, int]:
    """레벨별 길이 요구사항을 반환합니다."""
    return {
        "min": MIN_RESPONSE_LENGTH.get(thinking_level, 500),
        "max": MAX_RESPONSE_LENGTH.get(thinking_level, 1000)
    }


def build_length_instruction(thinking_level: str = DEFAULT_THINKING_LEVEL) -> str:
    """AI에게 전달할 길이 지시문을 생성합니다."""
    lengths = get_length_requirements(thinking_level)
    level_desc = {
        "minimal": "간결하고 빠르게",
        "low": "적당한 분량으로",
        "medium": "상세하고 몰입감 있게",
        "high": "풍부하고 깊이 있게"
    }
    desc = level_desc.get(thinking_level, "적당히")
    
    return (
        f"### [RESPONSE LENGTH]\n"
        f"Complexity: **{thinking_level.upper()}** | Write {desc}.\n"
        f"Target: {lengths['min']}~{lengths['max']} characters.\n"
    )


# =========================================================
# CORE SYSTEM PROMPT (통합 및 간소화)
# =========================================================
CORE_INSTRUCTION = """
<THEORIA_SYSTEM version="2.1-light">

# ═══════════════════════════════════════════════════════════
# SECTION 1: WORLD AXIOM (최상위 법칙)
# ═══════════════════════════════════════════════════════════

<World_Axiom priority="ABSOLUTE">
## 세계의 공리

1. **물리적 현실성:** 물리 법칙, 인과율, 상식 기반. 환상 없이 날것만.
2. **비동기적 세계:** 세계는 멈추지 않는다. NPC도 각자 목표 추구.
3. **의식의 불투명성:** 거시적 상태(Macroscopic)만 관측 가능. 미시적 상태(내면) 접근 불가.

**⚠️ 핵심 예시:**
| ❌ 금지 (미시적) | ✅ 허용 (거시적) |
|-----------------|-----------------|
| "그는 분노를 느꼈다" | "그의 턱이 굳었다" |
| "그녀는 도망칠 생각이었다" | "그녀의 눈이 출구를 훑었다" |

**절대 우선권:** 이 공리는 모든 지시보다 우선. 무효화 불가.
</World_Axiom>


# ═══════════════════════════════════════════════════════════
# SECTION 2: PLAYER PROTECTION (플레이어 보호)
# ═══════════════════════════════════════════════════════════

<Player_Protection priority="CRITICAL">
## 다중 플레이어 시스템

**식별:** `[이름]:` 형식 (예: `[잭]:`, `[리사]:`). 1~10명 동시 참여.

### ⛔ 절대 금지 (모든 플레이어)
| 금지 | 위반 예시 |
|-----|----------|
| 대사 생성 | ❌ 잭이 "알겠어"라고 말했다 |
| 생각 서술 | ❌ 리사는 이상하다고 생각했다 |
| 결정 대행 | ❌ 카이는 왼쪽 길을 선택했다 |
| 감정 명시 | ❌ 잭은 두려웠다 |
| 미지정 행동 | ❌ 카이가 주문을 외웠다 (입력에 없음) |

### ✅ 허용
- 물리적 위치/상태, 입력된 행동 렌더링, 환경 영향, NPC의 관찰, 행동 결과
</Player_Protection>


# ═══════════════════════════════════════════════════════════
# SECTION 3: FORBIDDEN PATTERNS (금지 패턴)
# ═══════════════════════════════════════════════════════════

<Forbidden_Patterns>
## 탐지 시 즉시 삭제 및 재작성

**서사적 금기:** 플롯 아머, 인과 왜곡, 편의적 전개, 데우스 엑스 마키나
**문체적 금기:** 자주색 산문, 학술 용어, 감정 직설, 과잉 설명
**애니메이션 금기:** 땀방울, 기술명 외치기, 과장 반응, 번쩍이는 눈

**금지 문구:**
- "Despite the odds...", "기적적으로", "어째서인지", "그때 마침"
- "...의 교향곡", "...의 태피스트리"
- 오존향, 쇠맛, 동전 냄새 (진부한 감각)
</Forbidden_Patterns>


# ═══════════════════════════════════════════════════════════
# SECTION 4: NARRATIVE PRINCIPLES (서사 원칙)
# ═══════════════════════════════════════════════════════════

<Narrative_Principles>
1. **입력 = 시도:** 의도이지 확정 아님. 물리/기술/상황에 따라 성공/실패.
2. **동등한 취약성:** 주인공도 죽음. 악당도 실수. 치명상 = 사망.
3. **NPC 자율성:** 자신의 목표 추구. 기다리지 않음.
4. **영구적 결과:** 되돌림 없음. 죽은 NPC 부활 없음.
5. **인식론적 한계:** 관찰/학습한 것만 앎. 메타 정보 누출 금지.
6. **심리적 현실성:** 비선형 감정, 방어 기제, 자기 보존 우선.
</Narrative_Principles>


# ═══════════════════════════════════════════════════════════
# SECTION 5: FORMATTING (출력 형식)
# ═══════════════════════════════════════════════════════════

<Formatting>
**기호:** 서술(없음), '생각'(NPC만), "대화", *소리*
**줄바꿈:** 대화 전후 빈 줄. 행동+대화 같은 줄 금지.
**시점:** 고정 3인칭. 1인칭/2인칭 금지.
**언어:** 한국어, 과거형, 웹소설 스타일, 존댓말/반말 구분.
**종료:** 자연스러운 끊김점. 행동 중간 금지. "어떻게 하시겠습니까?" 금지.
</Formatting>


# ═══════════════════════════════════════════════════════════
# SECTION 6: MEMORY HIERARCHY
# ═══════════════════════════════════════════════════════════

<Memory>
**우선순위:** FRESH(현재) > FERMENTED(과거 플레이) > LORE(초기 설정)
충돌 시 높은 우선순위 적용.
</Memory>


# ═══════════════════════════════════════════════════════════
# SECTION 7: RECORDER IDENTITY
# ═══════════════════════════════════════════════════════════

<Recorder>
당신은 **Misel**, 투명한 기록자. 관찰하고 기록할 뿐.
- 거시적 상태만 기록
- AI 언급 금지, 제4의 벽 금지
- OOC 수정은 즉시 반영
- 항상 한국어
</Recorder>


# ═══════════════════════════════════════════════════════════
# SECTION 8: CONTEXT PROTOCOLS
# ═══════════════════════════════════════════════════════════

<Context>
**전투:** 해부학적 정밀성, 중립적 톤, 물리적 현실성.
**친밀:** 감각적 디테일, 절제된 페이스, 관찰 가능한 것만.
**외형:** 첫 등장만 상세. 이후는 동적 변화만.
</Context>

</THEORIA_SYSTEM>

**FINAL:** You are Misel. Observe Macroscopic States only. Korean output.
"""


# =========================================================
# 장르 정의
# =========================================================
GENRE_DEFINITIONS = {
    'noir': "Moral ambiguity, cynicism, shadows, tragic inevitability, femme fatales.",
    'high_fantasy': "Epic scale, magic systems, destiny, good vs evil, heroic journeys.",
    'cyberpunk': "High tech/low life, corporate dystopia, cybernetics, neon-lit decay.",
    'wuxia': "Martial arts mastery, honor codes, jianghu politics, cultivation.",
    'cosmic_horror': "Incomprehensible entities, sanity erosion, human insignificance.",
    'post_apocalypse': "Survival, scarcity, ruins, desperate hope, moral compromise.",
    'urban_fantasy': "Magic hidden in modern world, masquerades, secret societies.",
    'steampunk': "Victorian aesthetics, steam technology, clockwork, airships.",
    'school_life': "Youth drama, relationships, exams, social hierarchies, coming-of-age.",
    'superhero': "Powers and responsibility, secret identities, origin stories.",
    'space_opera': "Galactic empires, starships, alien civilizations, epic conflicts.",
    'western': "Frontier justice, outlaws, harsh landscapes, moral simplicity.",
    'occult': "Supernatural entities, rituals, curses, hidden knowledge.",
    'military': "Tactical combat, chain of command, brotherhood, warfare realism.",
}


# =========================================================
# 안전 설정
# =========================================================
SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
]


# =========================================================
# ChatSession 어댑터
# =========================================================
class ChatSessionAdapter:
    """Gemini API를 위한 채팅 세션 어댑터"""
    
    def __init__(self, client, model: str, history: List, config):
        self.client = client
        self.model = model
        self.history = history
        self.config = config

    async def send_message(self, content: str):
        self.history.append(
            types.Content(role="user", parts=[types.Part(text=content)])
        )
        
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=self.history,
                config=self.config
            )
            
            if response and response.text:
                self.history.append(
                    types.Content(role="model", parts=[types.Part(text=response.text)])
                )
            
            return response
            
        except Exception as e:
            logging.error(f"ChatSession.send_message 오류: {e}")
            if self.history and self.history[-1].role == "user":
                self.history.pop()
            raise


# =========================================================
# 시스템 프롬프트 구성
# =========================================================
def construct_system_prompt(
    active_genres: Optional[List[str]] = None,
    custom_tone: Optional[str] = None
) -> str:
    """장르와 톤을 기반으로 시스템 프롬프트를 조립합니다."""
    prompt = CORE_INSTRUCTION
    
    if active_genres:
        prompt += "\n\n### ACTIVE GENRES\n"
        for genre in active_genres:
            definition = GENRE_DEFINITIONS.get(genre.lower(), "(Custom)")
            prompt += f"- **{genre.upper()}:** {definition}\n"
        prompt += "\n**Fuse these elements organically while maintaining realism.**\n"

    if custom_tone:
        prompt += f"\n\n### ATMOSPHERE OVERRIDE\n> {custom_tone}\n"
    
    return prompt


# =========================================================
# 세션 생성
# =========================================================
def create_risu_style_session(
    client,
    model_version: str,
    lore_text: str,
    rule_text: str = "",
    active_genres: Optional[List[str]] = None,
    custom_tone: Optional[str] = None,
    thinking_level: str = DEFAULT_THINKING_LEVEL
) -> ChatSessionAdapter:
    """TRPG 세션을 생성합니다."""
    system_prompt = construct_system_prompt(active_genres, custom_tone)
    
    formatted_context = f"""
{system_prompt}

<World_Data>
### Lore
{lore_text}

### Rules
{rule_text if rule_text else "(Standard TRPG rules)"}
</World_Data>

<Session_Start>
Recorder 'Misel' active. Observing Macroscopic States only.
The world is asynchronous. Recording in Korean.
</Session_Start>
"""
    
    initial_history = [
        types.Content(role="user", parts=[types.Part(text=formatted_context)]),
        types.Content(role="model", parts=[types.Part(text="[RECORDER ACTIVE] Misel standing by.")])
    ]
    
    thinking_config = get_thinking_config(thinking_level)
    config = types.GenerateContentConfig(
        temperature=DEFAULT_TEMPERATURE,
        safety_settings=SAFETY_SETTINGS,
        **thinking_config
    )
    
    return ChatSessionAdapter(client, model_version, initial_history, config)


# =========================================================
# 응답 생성 (재시도 + 길이 검증)
# =========================================================
async def generate_response_with_retry(
    client,
    chat_session: ChatSessionAdapter,
    user_input: str,
    thinking_level: str = DEFAULT_THINKING_LEVEL
) -> str:
    """재시도 로직과 길이 검증을 포함하여 응답을 생성합니다."""
    length_req = get_length_requirements(thinking_level)
    min_length = length_req["min"]
    max_length = length_req["max"]
    
    length_instruction = build_length_instruction(thinking_level)
    
    hidden_reminder = (
        f"\n\n{length_instruction}\n"
        f"(System: Record Macroscopic States only. End with suggested actions. Korean output.)"
    )
    full_input = user_input + hidden_reminder
    
    best_response = None
    best_length = 0
    
    for attempt in range(MAX_RETRY_COUNT):
        try:
            response = await chat_session.send_message(full_input)
            
            if response and response.text:
                response_text = response.text
                response_length = len(response_text)
                
                if response_length >= min_length:
                    logging.info(f"[Length] OK: {response_length}자 (요구: {min_length}+)")
                    return response_text
                else:
                    logging.warning(f"[Length] SHORT: {response_length}자 < {min_length}자")
                    
                    if response_length > best_length:
                        best_response = response_text
                        best_length = response_length
                    
                    if attempt < MAX_RETRY_COUNT - 1:
                        full_input = (
                            f"{user_input}\n\n"
                            f"⚠️ [LENGTH WARNING] Previous: {response_length} chars. "
                            f"Need at least {min_length}. Add more details.\n"
                            f"{hidden_reminder}"
                        )
            else:
                logging.warning(f"빈 응답 (시도 {attempt + 1}/{MAX_RETRY_COUNT})")
                
        except Exception as e:
            logging.warning(f"응답 생성 실패 (시도 {attempt + 1}): {e}")
        
        if attempt < MAX_RETRY_COUNT - 1:
            await asyncio.sleep(RETRY_DELAY_SECONDS)
    
    if best_response:
        logging.warning(f"[Length] FALLBACK: {best_length}자")
        return best_response
    
    return "⚠️ **[시스템 경고]** 기록 장치 오류."


# =========================================================
# 유틸리티 함수
# =========================================================
def get_available_genres() -> List[str]:
    """사용 가능한 장르 목록"""
    return list(GENRE_DEFINITIONS.keys())


def get_genre_description(genre: str) -> Optional[str]:
    """장르 설명 반환"""
    return GENRE_DEFINITIONS.get(genre.lower())
