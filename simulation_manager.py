"""
Lorekeeper TRPG Bot - Simulation Manager Module
패시브, 적응, 상태이상, 인벤토리 관리를 담당합니다.
"""

import random
from typing import Dict, Any, Tuple, List, Union, Optional

# =========================================================
# 상수 정의
# =========================================================

# 성장 시스템 타입
GROWTH_SYSTEM_STANDARD = "standard"  # 패시브/칭호 기반 (기본)
GROWTH_SYSTEM_CUSTOM = "custom"      # 사용자 정의 룰

# =========================================================
# 상태이상 시스템 (AI 자율 판단)
# AI가 서사에 맞게 상태이상을 부여/해제
# =========================================================

# AI 참고용 가이드라인 (하드코딩 아님)
STATUS_EFFECT_GUIDELINES = """
[상태이상 가이드라인 - AI가 자유롭게 판단]

## 부정적 상태 (서사적 위기 요소)
신체적: 부상, 중상, 출혈, 골절, 화상, 동상, 중독, 피로, 기절, 마비
정신적: 공포, 공황, 혼란, 분노, 절망, 트라우마, 광기
환경적: 질식, 실명, 청각상실, 굶주림, 갈증, 수면부족
사회적: 수배, 추적당함, 오명, 빚, 배신당함
마법적: 저주, 마력고갈, 영혼손상, 빙의

## 긍정적 상태 (서사적 이점)
신체적: 보호, 회복중, 강화, 재생, 은신, 가속
정신적: 집중, 영감, 평온, 용기, 결의, 희망
사회적: 보호받음, 동맹, 신뢰받음
마법적: 축복, 마력충전, 신의가호

## AI 판단 기준
1. 서사적 맥락에서 자연스러운가?
2. 캐릭터의 행동/상황에 적합한가?
3. 플레이어에게 의미 있는 영향을 주는가?
4. 기존 상태와 중복/상충되지 않는가?

## Doom 영향 (AI가 심각도 판단)
- 경미한 상태: Doom 영향 없음
- 중간 상태: Doom +1~2
- 심각한 상태: Doom +2~3
- 긍정적 상태: Doom -1~2
"""


def get_status_context_for_ai(user_data: Dict[str, Any]) -> str:
    """AI에게 전달할 상태이상 컨텍스트를 생성합니다."""
    effects = user_data.get("status_effects", [])
    
    if not effects:
        return ""
    
    return (
        f"### [현재 상태이상]\n"
        f"{', '.join(effects)}\n"
        f"*상태이상의 서사적 영향을 자연스럽게 반영하세요.*\n"
    )


def add_status_effect(
    user_data: Dict[str, Any],
    effect_name: str,
    reason: str = ""
) -> Tuple[Dict[str, Any], str]:
    """
    상태이상을 추가합니다.
    
    Args:
        user_data: 사용자 데이터
        effect_name: 상태이상 이름
        reason: 부여 사유
    
    Returns:
        (업데이트된 user_data, 메시지)
    """
    effects = user_data.get("status_effects", [])
    
    if effect_name in effects:
        return user_data, f"⚠️ 이미 '{effect_name}' 상태입니다."
    
    effects.append(effect_name)
    user_data["status_effects"] = effects
    
    msg = f"⚡ **상태 부여:** {effect_name}"
    if reason:
        msg += f" ({reason})"
    
    return user_data, msg


def remove_status_effect(
    user_data: Dict[str, Any],
    effect_name: str,
    reason: str = ""
) -> Tuple[Dict[str, Any], str]:
    """
    상태이상을 제거합니다.
    
    Args:
        user_data: 사용자 데이터
        effect_name: 상태이상 이름
        reason: 해제 사유
    
    Returns:
        (업데이트된 user_data, 메시지)
    """
    effects = user_data.get("status_effects", [])
    
    if effect_name not in effects:
        return user_data, f"⚠️ '{effect_name}' 상태가 없습니다."
    
    effects.remove(effect_name)
    user_data["status_effects"] = effects
    
    msg = f"✨ **상태 해제:** {effect_name}"
    if reason:
        msg += f" ({reason})"
    
    return user_data, msg


def get_status_list(user_data: Dict[str, Any]) -> str:
    """현재 상태이상 목록을 문자열로 반환합니다."""
    effects = user_data.get("status_effects", [])
    
    if not effects:
        return "📋 **상태이상:** 없음"
    
    return f"📋 **상태이상:** {', '.join(effects)}"


def estimate_doom_from_status(status_effects: List[str]) -> int:
    """
    상태이상 목록에서 대략적인 Doom 영향을 추정합니다.
    AI가 더 정확한 판단을 내리기 위한 참고용.
    
    Returns:
        추정 Doom 변화량
    """
    if not status_effects:
        return 0
    
    # 키워드 기반 간단한 추정
    severe_keywords = ["중상", "골절", "광기", "트라우마", "빙의", "영혼", "질식"]
    moderate_keywords = ["부상", "출혈", "중독", "공포", "절망", "저주", "수배"]
    positive_keywords = ["축복", "보호", "희망", "회복", "치료", "가호"]
    
    doom = 0
    for effect in status_effects:
        effect_lower = effect.lower()
        if any(kw in effect_lower for kw in severe_keywords):
            doom += 2
        elif any(kw in effect_lower for kw in moderate_keywords):
            doom += 1
        elif any(kw in effect_lower for kw in positive_keywords):
            doom -= 1
    
    return doom


# =========================================================
# 헌터 랭크 시스템
# =========================================================
def gain_experience(
    user_data: Dict[str, Any],
    amount: int,
    system_type: str = GROWTH_SYSTEM_STANDARD
) -> Tuple[Dict[str, Any], str, Union[bool, str]]:
    """
    경험치 획득 함수입니다. (치트 전용)
    
    기본 시스템에서는 패시브/칭호 기반이므로 경험치 수치는 참고용입니다.
    커스텀 시스템에서는 !룰에 정의한 규칙을 AI가 판단합니다.
    
    Args:
        user_data: 사용자 데이터
        amount: 획득 경험치
        system_type: 성장 시스템 타입 ('standard', 'custom')
    
    Returns:
        (업데이트된 사용자 데이터, 결과 메시지, 레벨업 여부 또는 "CheckAI")
    """
    if "xp" not in user_data:
        user_data["xp"] = 0
    
    mask = user_data.get("mask", "Unknown")
    user_data["xp"] += amount
    
    # 커스텀 모드: AI가 룰에 따라 판정
    if system_type == GROWTH_SYSTEM_CUSTOM:
        msg = (
            f"🆙 **경험치:** {mask} +{amount} "
            f"(총 {user_data['xp']}, 룰에 따른 판정 대기)"
        )
        return user_data, msg, "CheckAI"
    
    # 기본 모드: 경험치는 참고용, 패시브/칭호가 실제 성장
    msg = (
        f"🆙 **경험치:** {mask} +{amount} "
        f"(총 {user_data['xp']}) — 패시브/칭호로 성장 반영"
    )
    return user_data, msg, False


# =========================================================
# 인벤토리 관리
# =========================================================
def update_inventory(
    user_data: Dict[str, Any],
    action: str,
    item_name: str,
    count: int = 1
) -> Tuple[Dict[str, Any], str]:
    """
    인벤토리를 업데이트합니다.
    
    Args:
        user_data: 사용자 데이터
        action: "add" 또는 "remove"
        item_name: 아이템 이름
        count: 수량 (기본값: 1)
    
    Returns:
        (업데이트된 사용자 데이터, 결과 메시지)
    """
    inv = user_data.get("inventory", {})
    current_qty = inv.get(item_name, 0)
    
    if action == "add":
        inv[item_name] = current_qty + count
        msg = f"🎒 **획득:** {item_name} x{count} (현재: {inv[item_name]})"
    
    elif action == "remove":
        if current_qty < count:
            msg = f"❌ **사용 실패:** {item_name} 부족 (보유: {current_qty})"
        else:
            inv[item_name] = current_qty - count
            
            if inv[item_name] <= 0:
                del inv[item_name]
                msg = f"🗑️ **사용/버림:** {item_name} x{count} (남음: 0)"
            else:
                msg = f"📉 **사용:** {item_name} x{count} (남음: {inv[item_name]})"
    else:
        msg = "⚠️ 알 수 없는 동작"
    
    user_data["inventory"] = inv
    return user_data, msg


# =========================================================
# 관계도 관리
# =========================================================
def modify_relationship(
    user_data: Dict[str, Any],
    target_name: str,
    amount: int
) -> Tuple[Dict[str, Any], str]:
    """
    NPC와의 관계도를 수정합니다.
    
    Args:
        user_data: 사용자 데이터
        target_name: 대상 NPC 이름
        amount: 변화량 (양수: 호감도 상승, 음수: 하락)
    
    Returns:
        (업데이트된 사용자 데이터, 결과 메시지)
    """
    rels = user_data.get("relations", {})
    current = rels.get(target_name, 0)
    new_val = current + amount
    rels[target_name] = new_val
    user_data["relations"] = rels
    
    emoji = "💖" if amount > 0 else "💔"
    msg = f"{emoji} **{target_name}** 관계: {amount:+} ({new_val})"
    
    return user_data, msg


# =========================================================
# 비일상의 일상화 시스템 (Abnormal Normalization System)
# =========================================================

# 적응 단계 정의
NORMALITY_STAGES = {
    (0, 20): {
        "stage": "shock",
        "name": "충격",
        "reaction_hint": "경악, 공포, 믿을 수 없다는 반응",
        "tone": "dramatic"
    },
    (20, 40): {
        "stage": "confusion",
        "name": "당황",
        "reaction_hint": "혼란, '이게 뭐지?', 어찌할 바를 모름",
        "tone": "uncertain"
    },
    (40, 60): {
        "stage": "acceptance",
        "name": "체념",
        "reaction_hint": "'...또야?', 한숨, 피로감",
        "tone": "resigned"
    },
    (60, 80): {
        "stage": "adaptation",
        "name": "적응",
        "reaction_hint": "담담함, '알았어', 별 감흥 없음",
        "tone": "calm"
    },
    (80, 101): {
        "stage": "normalized",
        "name": "일상화",
        "reaction_hint": "아무 반응 없음, 자연스럽게 처리",
        "tone": "mundane"
    }
}

def get_normality_stage(normality: int) -> Dict[str, str]:
    """적응도에 따른 단계 정보를 반환합니다."""
    for (low, high), stage_info in NORMALITY_STAGES.items():
        if low <= normality < high:
            return stage_info
    return NORMALITY_STAGES[(80, 101)]  # 기본값: 일상화


def calculate_normality(count: int, base_threshold: int = 10) -> int:
    """
    노출 횟수에 따른 적응도를 계산합니다.
    
    Args:
        count: 노출 횟수
        base_threshold: 100% 도달에 필요한 기본 횟수
    
    Returns:
        적응도 (0-100)
    """
    if count <= 0:
        return 0
    
    # 로그 스케일로 빠르게 적응하다가 후반에 느려짐
    # 1회: ~20%, 3회: ~50%, 5회: ~70%, 10회: ~100%
    import math
    normality = min(100, int((math.log(count + 1) / math.log(base_threshold + 1)) * 100))
    return normality


def expose_to_abnormal(
    user_data: Dict[str, Any],
    abnormal_type: str,
    current_day: int = 1
) -> Tuple[Dict[str, Any], Optional[str], Optional[Dict]]:
    """
    비일상 요소에 노출되었을 때 호출합니다.
    
    Args:
        user_data: 사용자 데이터
        abnormal_type: 비일상 요소 이름 (예: "드래곤", "마법", "고백")
        current_day: 현재 게임 내 일차
    
    Returns:
        (업데이트된 user_data, 시스템 메시지 또는 None, 단계 정보)
    """
    exposure = user_data.get("abnormal_exposure", {})
    
    if abnormal_type not in exposure:
        exposure[abnormal_type] = {"count": 0, "normality": 0, "first_day": current_day}
    
    # 노출 횟수 증가
    exposure[abnormal_type]["count"] += 1
    count = exposure[abnormal_type]["count"]
    
    # 적응도 계산
    old_normality = exposure[abnormal_type]["normality"]
    new_normality = calculate_normality(count)
    exposure[abnormal_type]["normality"] = new_normality
    
    user_data["abnormal_exposure"] = exposure
    
    # 단계 변화 감지
    old_stage = get_normality_stage(old_normality)
    new_stage = get_normality_stage(new_normality)
    
    msg = None
    if old_stage["stage"] != new_stage["stage"]:
        msg = f"🌓 **[{abnormal_type}]** 적응 단계 변화: {old_stage['name']} → {new_stage['name']}"
    
    # 100% 도달 시 특별 메시지
    if old_normality < 100 and new_normality >= 100:
        msg = f"🌙 **[{abnormal_type}]** 이제 일상이 되었다. (적응도 100%)"
    
    return user_data, msg, new_stage


def get_abnormal_context(user_data: Dict[str, Any], abnormal_types: List[str]) -> str:
    """
    현재 장면의 비일상 요소들에 대한 적응 컨텍스트를 생성합니다.
    AI에게 전달할 톤 힌트를 반환합니다.
    
    Args:
        user_data: 사용자 데이터
        abnormal_types: 현재 장면에 등장하는 비일상 요소 리스트
    
    Returns:
        AI용 컨텍스트 문자열
    """
    if not abnormal_types:
        return ""
    
    exposure = user_data.get("abnormal_exposure", {})
    contexts = []
    
    for ab_type in abnormal_types:
        if ab_type in exposure:
            normality = exposure[ab_type]["normality"]
            stage = get_normality_stage(normality)
            contexts.append(
                f"- {ab_type}: 적응도 {normality}% ({stage['name']}) → {stage['reaction_hint']}"
            )
        else:
            # 첫 노출
            contexts.append(
                f"- {ab_type}: 적응도 0% (첫 노출!) → 경악, 공포, 믿을 수 없다는 반응"
            )
    
    return "### [비일상 적응도]\n" + "\n".join(contexts) + "\n"


# =========================================================
# 패시브 성장 시스템 (Passive Growth System)
# =========================================================

# 기본 패시브 정의 (경험 기반 자동 획득)
# =========================================================
# 경험 카운터 시스템 (Experience Counter System)
# AI가 참고하는 예시 트리거 - 실제 패시브 부여는 AI가 자율적으로 결정
# =========================================================

# AI 참고용 예시 (하드코딩 아님, 가이드라인)
EXAMPLE_PASSIVE_TRIGGERS = """
[경험 기반 패시브 예시 - AI가 자유롭게 변형/창작 가능]

생존 계열:
- 독에 여러 번 노출 → "독 내성" (독 피해 감소)
- 화상/동상 반복 경험 → "온도 적응" (극한 환경 저항)
- 낙하 경험 → "낙법" (충격 분산)
- 굶주림/갈증 경험 → "소식가" (적은 자원으로 버팀)

정신 계열:
- 배신 경험 → "의심의 눈" (거짓말 감지)
- 죽을 고비 → "구사일생" (위기 대처력)
- 협박/공포 경험 → "배짱" (위협 저항)

초자연 계열:
- 마법 피격 → "마력 친화" (마법 감지/저항)
- 괴물 조우 → "용기" 또는 관련 적응
- 영적 존재 목격 → "영시" (비물질 감지)

[AI 판단 기준]
1. 반복된 경험인가? (3회 이상 유사 상황)
2. 캐릭터가 해당 상황을 극복했는가?
3. 서사적으로 자연스러운가?
"""


def increment_experience_counter(
    user_data: Dict[str, Any],
    counter_name: str,
    amount: int = 1,
    current_day: int = 1
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    경험 카운터를 증가시킵니다.
    패시브 부여는 AI가 자율적으로 판단합니다.
    
    Args:
        user_data: 사용자 데이터
        counter_name: 카운터 이름 (예: "독_중독", "드래곤조우")
        amount: 증가량
        current_day: 현재 게임 내 일차
    
    Returns:
        (업데이트된 user_data, None)
    """
    counters = user_data.get("experience_counters", {})
    
    # 카운터 증가
    current = counters.get(counter_name, 0)
    counters[counter_name] = current + amount
    user_data["experience_counters"] = counters
    
    # 패시브 부여는 AI가 자율적으로 판단 (하드코딩 제거)
    return user_data, None


def get_passive_list(user_data: Dict[str, Any]) -> str:
    """보유 패시브 목록을 문자열로 반환합니다."""
    passives = user_data.get("passives", [])
    
    if not passives:
        return "📋 **보유 패시브:** 없음\n(경험을 쌓으면 패시브를 획득합니다)"
    
    # 카테고리별 분류
    by_category: Dict[str, List] = {}
    for p in passives:
        cat = p.get("category", "기타")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(p)
    
    result = "📋 **보유 패시브:**\n"
    for cat, passive_list in by_category.items():
        result += f"\n**[{cat}]**\n"
        for p in passive_list:
            result += f"  • **{p['name']}**: {p['effect']}\n"
    
    return result


def get_passive_context(user_data: Dict[str, Any]) -> str:
    """AI에게 전달할 패시브 컨텍스트를 생성합니다."""
    passives = user_data.get("passives", [])
    
    if not passives:
        return ""
    
    passive_effects = [f"[{p['name']}]: {p['effect']}" for p in passives]
    
    return (
        "### [캐릭터 패시브]\n"
        f"{chr(10).join(passive_effects)}\n"
        "*패시브 효과를 서사에 자연스럽게 반영하세요.*\n\n"
    )


def get_experience_progress(user_data: Dict[str, Any]) -> str:
    """경험 카운터 진행도를 문자열로 반환합니다."""
    counters = user_data.get("experience_counters", {})
    passives = user_data.get("passives", [])
    
    if not counters and not passives:
        return "📊 **경험 진행도:** 아직 기록된 경험이 없습니다."
    
    # 보유한 패시브 이름 목록
    owned_passives = {p["name"] for p in passives}
    
    result = "📊 **경험 진행도:**\n"
    
    # 카운터 기반 진행도 (하드코딩 폴백)
    if counters:
        result += "\n**[경험 카운터]**\n"
        for counter_name, count in sorted(counters.items()):
            result += f"  • {counter_name}: {count}회\n"
    
    # 보유 패시브 목록
    if passives:
        result += "\n**[획득한 패시브]**\n"
        for p in passives:
            source = p.get("source", "")
            source_tag = " (AI)" if source == "AI" else ""
            result += f"  🏆 **{p['name']}**{source_tag}\n"
            if p.get("trigger"):
                result += f"     _{p.get('trigger')}_\n"
    
    return result


# =========================================================
# AI 자율 패시브 시스템 (AI-Driven Passive System)
# =========================================================

def grant_ai_passive(
    user_data: Dict[str, Any],
    passive_suggestion: Dict[str, Any],
    current_day: int = 1
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    AI가 제안한 패시브를 부여합니다.
    
    Args:
        user_data: 사용자 데이터
        passive_suggestion: AI가 제안한 패시브 정보
            {
                "name": "엘프의 친구",
                "trigger": "엘프와 우호적 상호작용 10회",
                "effect": "엘프에게 호감도 보너스, 엘프어 기초 이해",
                "category": "사회",
                "reasoning": "플레이어가 엘프 NPC들과 지속적으로..."
            }
        current_day: 현재 게임 내 일차
    
    Returns:
        (업데이트된 user_data, 획득 메시지 또는 None)
    """
    if not passive_suggestion:
        return user_data, None
    
    name = passive_suggestion.get("name")
    if not name:
        return user_data, None
    
    passives = user_data.get("passives", [])
    
    # 이미 보유 중인지 확인
    if any(p["name"] == name for p in passives):
        return user_data, None
    
    # 새 패시브 생성
    new_passive = {
        "name": name,
        "effect": passive_suggestion.get("effect", "효과 미정"),
        "category": passive_suggestion.get("category", "기타"),
        "trigger": passive_suggestion.get("trigger", "AI 판단"),
        "acquired_day": current_day,
        "source": "AI",  # AI가 부여했음을 표시
        "reasoning": passive_suggestion.get("reasoning", "")
    }
    
    passives.append(new_passive)
    user_data["passives"] = passives
    
    msg = (
        f"🏆 **패시브 획득!**\n"
        f"**[{name}]** ({new_passive['category']})\n"
        f"_{new_passive['effect']}_\n"
        f"(조건: {new_passive['trigger']})"
    )
    
    return user_data, msg


def get_passives_for_context(user_data: Dict[str, Any]) -> str:
    """
    AI 분석에 전달할 현재 보유 패시브 목록을 생성합니다.
    중복 부여 방지용.
    """
    passives = user_data.get("passives", [])
    if not passives:
        return "보유 패시브: 없음"
    
    passive_names = [p["name"] for p in passives]
    return f"보유 패시브: {', '.join(passive_names)}"
