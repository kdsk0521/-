"""
Lorekeeper TRPG Bot - Simulation Manager Module
경험치, 성장, 훈련, 인벤토리, 상태이상 관리를 담당합니다.
"""

import random
from typing import Dict, Any, Tuple, List, Union, Optional

# =========================================================
# 상수 정의
# =========================================================
# D&D 스타일 레벨업 XP 테이블
DND_XP_TABLE = {
    1: 300,
    2: 900,
    3: 2700,
    4: 6500,
    5: 14000,
    6: 23000,
    7: 34000,
    8: 48000,
    9: 64000,
    10: 85000,
    11: 100000,
    12: 120000,
    13: 140000,
    14: 165000,
    15: 195000,
    16: 225000,
    17: 265000,
    18: 305000,
    19: 355000,
    20: 999999  # 만렙
}

# 헌터 랭크 테이블
HUNTER_RANK_TABLE = [
    (5, "F급 (일반인)"),
    (10, "E급 (하급 헌터)"),
    (20, "D급 (중급 헌터)"),
    (30, "C급 (숙련 헌터)"),
    (40, "B급 (정예 헌터)"),
    (50, "A급 (초인)"),
    (999, "S급 (국가권력급)")
]

# 성장 시스템 타입
GROWTH_SYSTEM_STANDARD = "standard"
GROWTH_SYSTEM_DND = "dnd"
GROWTH_SYSTEM_HUNTER = "hunter"
GROWTH_SYSTEM_CUSTOM = "custom"

# 기본 성장 배율
STANDARD_GROWTH_MULTIPLIER = 1.2

# 훈련 관련 상수
BASE_TRAINING_FAIL_CHANCE = 0.1
STRESS_FAIL_MODIFIER = 0.005
TRAINING_STRESS_SUCCESS_MIN = 5
TRAINING_STRESS_SUCCESS_MAX = 10
TRAINING_STRESS_FAIL_MIN = 10
TRAINING_STRESS_FAIL_MAX = 20

# 휴식 관련 상수
REST_RECOVERY_MIN = 20
REST_RECOVERY_MAX = 40

# 휴식으로 회복 가능한 상태이상
RECOVERABLE_CONDITIONS = ["지침", "피로", "가벼운 부상"]

# 레벨업 시 보너스 스탯 후보
LEVEL_UP_BONUS_STATS = ["근력", "지능", "매력"]

# =========================================================
# 상태이상 분류 시스템
# world_manager의 doom 계산에 사용됨
# =========================================================

# 부정적 상태이상 (doom 증가 요인)
NEGATIVE_STATUS_EFFECTS = {
    # 신체적 부상 (심각도별)
    "중상": 3,
    "부상": 2,
    "가벼운 부상": 1,
    "출혈": 2,
    "골절": 3,
    "화상": 2,
    "동상": 2,
    "중독": 2,
    "질병": 2,
    "감염": 2,
    
    # 정신적/심리적
    "공포": 2,
    "패닉": 3,
    "혼란": 1,
    "광기": 3,
    "절망": 2,
    "트라우마": 2,
    "악몽": 1,
    
    # 신체 상태
    "피로": 1,
    "탈진": 2,
    "지침": 1,
    "굶주림": 2,
    "갈증": 2,
    "수면 부족": 1,
    "기절": 2,
    "마비": 2,
    "실명": 3,
    "청각 상실": 2,
    
    # 저주/마법적 (판타지용)
    "저주": 2,
    "마력 고갈": 1,
    "영혼 손상": 3,
    "빙의": 3,
    
    # 사회적
    "수배": 2,
    "추적당함": 2,
    "배신당함": 1,
}

# 긍정적 상태 (doom 감소 요인)
POSITIVE_STATUS_EFFECTS = {
    # 신체적 버프
    "치료됨": 1,
    "회복 중": 1,
    "강화": 1,
    "축복": 2,
    "보호막": 1,
    "재생": 2,
    
    # 정신적/심리적
    "집중": 1,
    "평온": 1,
    "용기": 1,
    "결의": 1,
    "영감": 1,
    "희망": 2,
    
    # 신체 상태
    "휴식함": 1,
    "포만감": 1,
    "숙면": 1,
    "활력": 1,
    
    # 마법적 (판타지용)
    "마력 충전": 1,
    "신의 가호": 2,
    "투명화": 1,
    
    # 사회적
    "은신 중": 1,
    "보호받음": 2,
    "동맹": 1,
}


def get_status_doom_modifier(status_effects: List[str]) -> Tuple[int, int, List[str], List[str]]:
    """
    상태이상 목록에서 doom 수정치를 계산합니다.
    
    Args:
        status_effects: 현재 상태이상 목록
    
    Returns:
        (increase, decrease, negative_list, positive_list)
    """
    increase = 0
    decrease = 0
    negative_found = []
    positive_found = []
    
    for effect in status_effects:
        effect_lower = effect.lower()
        
        # 부정적 상태 체크
        for neg_effect, value in NEGATIVE_STATUS_EFFECTS.items():
            if neg_effect in effect_lower or effect_lower in neg_effect:
                increase += value
                negative_found.append(f"{effect} (+{value})")
                break
        else:
            # 긍정적 상태 체크
            for pos_effect, value in POSITIVE_STATUS_EFFECTS.items():
                if pos_effect in effect_lower or effect_lower in pos_effect:
                    decrease += value
                    positive_found.append(f"{effect} (-{value})")
                    break
    
    return increase, decrease, negative_found, positive_found


# =========================================================
# 헌터 랭크 시스템
# =========================================================
def get_hunter_rank(level: int) -> str:
    """레벨 숫자를 헌터 등급으로 변환합니다."""
    for threshold, rank_name in HUNTER_RANK_TABLE:
        if level < threshold:
            return rank_name
    return HUNTER_RANK_TABLE[-1][1]


# =========================================================
# 성장 시스템
# =========================================================
def _apply_level_up_bonus(user_data: Dict[str, Any]) -> None:
    """레벨업 시 랜덤 스탯 보너스를 적용합니다."""
    bonus_stat = random.choice(LEVEL_UP_BONUS_STATS)
    
    if "stats" not in user_data:
        user_data["stats"] = {}
    
    if bonus_stat in user_data["stats"]:
        user_data["stats"][bonus_stat] += 1


def _calc_standard_growth(
    user_data: Dict[str, Any],
    amount: int
) -> Tuple[Dict[str, Any], bool]:
    """
    표준 성장: 경험치통이 1.2배씩 늘어나는 방식입니다.
    
    Args:
        user_data: 사용자 데이터
        amount: 획득 경험치
    
    Returns:
        (업데이트된 사용자 데이터, 레벨업 여부)
    """
    user_data["xp"] += amount
    leveled_up = False
    
    if not isinstance(user_data.get("level"), int):
        return user_data, False
    
    while user_data["xp"] >= user_data["next_xp"]:
        user_data["xp"] -= user_data["next_xp"]
        user_data["level"] += 1
        user_data["next_xp"] = int(user_data["next_xp"] * STANDARD_GROWTH_MULTIPLIER)
        leveled_up = True
        _apply_level_up_bonus(user_data)
    
    return user_data, leveled_up


def _calc_dnd_growth(
    user_data: Dict[str, Any],
    amount: int
) -> Tuple[Dict[str, Any], bool]:
    """
    D&D 스타일 성장: 고정된 XP 테이블을 사용합니다.
    
    Args:
        user_data: 사용자 데이터
        amount: 획득 경험치
    
    Returns:
        (업데이트된 사용자 데이터, 레벨업 여부)
    """
    user_data["xp"] += amount
    
    if not isinstance(user_data.get("level"), int):
        return user_data, False
    
    current_lv = user_data["level"]
    target_xp = DND_XP_TABLE.get(current_lv, 999999)
    
    leveled_up = False
    if user_data["xp"] >= target_xp:
        user_data["xp"] -= target_xp
        user_data["level"] += 1
        user_data["next_xp"] = DND_XP_TABLE.get(
            user_data["level"],
            int(target_xp * STANDARD_GROWTH_MULTIPLIER)
        )
        leveled_up = True
        _apply_level_up_bonus(user_data)
    
    return user_data, leveled_up


def gain_experience(
    user_data: Dict[str, Any],
    amount: int,
    system_type: str = GROWTH_SYSTEM_STANDARD
) -> Tuple[Dict[str, Any], str, Union[bool, str]]:
    """
    경험치 획득 통합 함수입니다.
    
    Args:
        user_data: 사용자 데이터
        amount: 획득 경험치
        system_type: 성장 시스템 타입 ('standard', 'dnd', 'hunter', 'custom')
    
    Returns:
        (업데이트된 사용자 데이터, 결과 메시지, 레벨업 여부 또는 "CheckAI")
    """
    # 기본값 보정
    if "level" not in user_data:
        user_data["level"] = 1
    if "xp" not in user_data:
        user_data["xp"] = 0
    if "next_xp" not in user_data:
        user_data["next_xp"] = 100
    
    mask = user_data.get("mask", "Unknown")
    
    # 커스텀 모드: 계산은 AI에게 맡김
    if system_type == GROWTH_SYSTEM_CUSTOM:
        user_data["xp"] += amount
        msg = (
            f"🆙 **경험치 획득:** {mask} +{amount} XP "
            f"(현재: {user_data['xp']}, 룰에 따른 레벨업 판정 중...)"
        )
        return user_data, msg, "CheckAI"
    
    # D&D 성장
    if system_type == GROWTH_SYSTEM_DND:
        user_data, leveled_up = _calc_dnd_growth(user_data, amount)
        level_display = f"Lv.{user_data['level']}"
    
    # 표준/헌터 성장
    else:
        user_data, leveled_up = _calc_standard_growth(user_data, amount)
        
        if system_type == GROWTH_SYSTEM_HUNTER:
            level_display = f"[{get_hunter_rank(user_data['level'])}]"
        else:
            level_display = f"Lv.{user_data['level']}"
    
    # 결과 메시지 생성
    if leveled_up:
        msg = f"🎉 **레벨 업!** {mask}님이 **{level_display}**가 되었습니다!"
    else:
        msg = (
            f"🆙 **경험치 획득:** {mask} +{amount} XP "
            f"(현재: {level_display}, XP: {user_data['xp']}/{user_data['next_xp']})"
        )
    
    return user_data, msg, leveled_up


# =========================================================
# 훈련 및 휴식 (스탯 & 스트레스 관리)
# =========================================================
def train_character(
    user_data: Dict[str, Any],
    stat_type: str
) -> Tuple[Dict[str, Any], str]:
    """
    캐릭터 훈련을 수행합니다.
    
    Args:
        user_data: 사용자 데이터
        stat_type: 훈련할 스탯 종류
    
    Returns:
        (업데이트된 사용자 데이터, 결과 메시지)
    """
    stats = user_data.get("stats", {})
    
    if stat_type not in stats:
        stats[stat_type] = 0
    
    current_val = stats.get(stat_type, 0)
    stress = stats.get("스트레스", 0)
    
    # 실패 확률 계산 (스트레스가 높을수록 실패 확률 증가)
    fail_chance = BASE_TRAINING_FAIL_CHANCE + (stress * STRESS_FAIL_MODIFIER)
    is_success = random.random() > fail_chance
    
    if is_success:
        gain = random.randint(1, 2)
        stats[stat_type] = current_val + gain
        stats["스트레스"] = stress + random.randint(
            TRAINING_STRESS_SUCCESS_MIN,
            TRAINING_STRESS_SUCCESS_MAX
        )
        result_msg = f"✨ **훈련 성공!** {stat_type} +{gain} (현재: {stats[stat_type]})"
    else:
        stats["스트레스"] = stress + random.randint(
            TRAINING_STRESS_FAIL_MIN,
            TRAINING_STRESS_FAIL_MAX
        )
        result_msg = "💦 **훈련 실패...** 집중력이 흐트러졌습니다. (스트레스 대폭 상승)"
    
    user_data["stats"] = stats
    return user_data, result_msg


def rest_character(user_data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    캐릭터 휴식을 수행합니다.
    
    Args:
        user_data: 사용자 데이터
    
    Returns:
        (업데이트된 사용자 데이터, 결과 메시지)
    """
    stats = user_data.get("stats", {})
    stress = stats.get("스트레스", 0)
    
    # 스트레스 회복
    recovery = random.randint(REST_RECOVERY_MIN, REST_RECOVERY_MAX)
    new_stress = max(0, stress - recovery)
    stats["스트레스"] = new_stress
    user_data["stats"] = stats
    
    # 상태이상 회복
    status_list = user_data.get("status_effects", [])
    recovered_effects = []
    
    for condition in RECOVERABLE_CONDITIONS:
        if condition in status_list:
            status_list.remove(condition)
            recovered_effects.append(condition)
    
    user_data["status_effects"] = status_list
    
    # 결과 메시지
    msg = f"💤 **휴식:** 스트레스가 {recovery}만큼 회복되었습니다. (현재: {new_stress})"
    
    if recovered_effects:
        msg += f"\n✨ **상태 회복:** {', '.join(recovered_effects)}"
    
    return user_data, msg


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
# 상태이상 관리
# =========================================================

# 상태이상 정의
STATUS_EFFECTS = {
    # === 부정적 상태 (Debuff) ===
    # 물리적 상태
    "부상": {"type": "debuff", "category": "physical", "severity": 1, "recoverable": True, "description": "가벼운 부상"},
    "중상": {"type": "debuff", "category": "physical", "severity": 2, "recoverable": False, "description": "심각한 부상, 치료 필요"},
    "출혈": {"type": "debuff", "category": "physical", "severity": 2, "tick_damage": 1, "description": "매 턴 체력 감소"},
    "골절": {"type": "debuff", "category": "physical", "severity": 3, "recoverable": False, "description": "이동/전투 불가"},
    "피로": {"type": "debuff", "category": "physical", "severity": 1, "recoverable": True, "description": "행동력 저하"},
    "지침": {"type": "debuff", "category": "physical", "severity": 1, "recoverable": True, "description": "집중력 저하"},
    "기절": {"type": "debuff", "category": "physical", "severity": 2, "duration": 1, "description": "행동 불가"},
    
    # 정신적 상태
    "공포": {"type": "debuff", "category": "mental", "severity": 2, "description": "특정 대상/상황 회피"},
    "공황": {"type": "debuff", "category": "mental", "severity": 3, "description": "판단력 상실"},
    "혼란": {"type": "debuff", "category": "mental", "severity": 2, "duration": 2, "description": "행동 예측 불가"},
    "분노": {"type": "debuff", "category": "mental", "severity": 1, "description": "이성적 판단 저하"},
    "절망": {"type": "debuff", "category": "mental", "severity": 2, "description": "의지력 저하"},
    "트라우마": {"type": "debuff", "category": "mental", "severity": 3, "recoverable": False, "description": "영구적 정신적 상처"},
    
    # 환경적 상태
    "중독": {"type": "debuff", "category": "environmental", "severity": 2, "tick_damage": 2, "description": "매 턴 피해"},
    "화상": {"type": "debuff", "category": "environmental", "severity": 2, "tick_damage": 1, "description": "화상 피해"},
    "동상": {"type": "debuff", "category": "environmental", "severity": 2, "description": "행동 둔화"},
    "질식": {"type": "debuff", "category": "environmental", "severity": 3, "tick_damage": 3, "description": "긴급 상황"},
    "실명": {"type": "debuff", "category": "environmental", "severity": 2, "description": "시야 상실"},
    "청각상실": {"type": "debuff", "category": "environmental", "severity": 1, "description": "소리 인식 불가"},
    
    # 사회적 상태
    "수배": {"type": "debuff", "category": "social", "severity": 2, "description": "당국에 추적당함"},
    "오명": {"type": "debuff", "category": "social", "severity": 1, "description": "평판 하락"},
    "빚": {"type": "debuff", "category": "social", "severity": 1, "description": "경제적 압박"},
    
    # === 긍정적 상태 (Buff) ===
    "집중": {"type": "buff", "category": "mental", "severity": 1, "description": "판정 보너스"},
    "영감": {"type": "buff", "category": "mental", "severity": 2, "duration": 3, "description": "창의적 행동 보너스"},
    "보호": {"type": "buff", "category": "physical", "severity": 2, "description": "피해 감소"},
    "은신": {"type": "buff", "category": "physical", "severity": 1, "description": "발견되기 어려움"},
    "가속": {"type": "buff", "category": "physical", "severity": 1, "duration": 2, "description": "행동 속도 증가"},
    "행운": {"type": "buff", "category": "special", "severity": 2, "duration": 1, "description": "다음 판정 유리"},
}

# 심각도별 Doom 영향
SEVERITY_DOOM_IMPACT = {
    1: 0,   # 경미: Doom 영향 없음
    2: 1,   # 중간: Doom +1
    3: 2,   # 심각: Doom +2
}


def get_status_effect_info(effect_name: str) -> Optional[Dict[str, Any]]:
    """상태이상 정보를 반환합니다."""
    return STATUS_EFFECTS.get(effect_name)


def get_all_status_effects_by_category(category: str) -> List[str]:
    """특정 카테고리의 모든 상태이상 이름을 반환합니다."""
    return [
        name for name, data in STATUS_EFFECTS.items()
        if data.get("category") == category
    ]


def get_active_debuffs(user_data: Dict[str, Any]) -> List[str]:
    """현재 활성화된 디버프 목록을 반환합니다."""
    effects = user_data.get("status_effects", [])
    return [e for e in effects if STATUS_EFFECTS.get(e, {}).get("type") == "debuff"]


def get_active_buffs(user_data: Dict[str, Any]) -> List[str]:
    """현재 활성화된 버프 목록을 반환합니다."""
    effects = user_data.get("status_effects", [])
    return [e for e in effects if STATUS_EFFECTS.get(e, {}).get("type") == "buff"]


def calculate_status_doom_contribution(user_data: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    상태이상이 Doom에 미치는 영향을 계산합니다.
    
    Returns:
        (doom_delta, reasons)
    """
    effects = user_data.get("status_effects", [])
    total_doom = 0
    reasons = []
    
    for effect_name in effects:
        effect_data = STATUS_EFFECTS.get(effect_name, {})
        if effect_data.get("type") == "debuff":
            severity = effect_data.get("severity", 1)
            doom_impact = SEVERITY_DOOM_IMPACT.get(severity, 0)
            
            if doom_impact > 0:
                total_doom += doom_impact
                reasons.append(f"💀 {effect_name} (심각도 {severity})")
    
    return total_doom, reasons


def update_status_effect(
    user_data: Dict[str, Any],
    action: str,
    effect_name: str
) -> Tuple[Dict[str, Any], str]:
    """
    상태이상을 업데이트합니다.
    
    Args:
        user_data: 사용자 데이터
        action: "add" 또는 "remove"
        effect_name: 상태이상 이름
    
    Returns:
        (업데이트된 사용자 데이터, 결과 메시지)
    """
    effects = user_data.get("status_effects", [])
    effect_info = STATUS_EFFECTS.get(effect_name, {})
    
    if action == "add":
        if effect_name not in effects:
            effects.append(effect_name)
            
            # 상태이상 타입에 따른 메시지
            if effect_info.get("type") == "buff":
                msg = f"✨ **버프 획득:** [{effect_name}]"
                if effect_info.get("description"):
                    msg += f" - {effect_info['description']}"
            else:
                severity = effect_info.get("severity", 1)
                severity_icon = "⚠️" if severity == 1 else "🔴" if severity == 2 else "💀"
                msg = f"{severity_icon} **상태이상 발생:** [{effect_name}]"
                if effect_info.get("description"):
                    msg += f" - {effect_info['description']}"
        else:
            msg = f"⚠️ 이미 [{effect_name}] 상태입니다."
    
    elif action == "remove":
        if effect_name in effects:
            effects.remove(effect_name)
            msg = f"✨ **상태 해제:** [{effect_name}] 제거됨"
        else:
            msg = f"⚠️ [{effect_name}] 상태가 아닙니다."
    else:
        msg = "⚠️ 알 수 없는 동작"
    
    user_data["status_effects"] = effects
    return user_data, msg


def process_tick_effects(user_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    턴/시간 경과 시 상태이상 효과를 처리합니다.
    
    Returns:
        (업데이트된 사용자 데이터, 메시지 목록)
    """
    effects = user_data.get("status_effects", [])
    messages = []
    effects_to_remove = []
    
    for effect_name in effects:
        effect_info = STATUS_EFFECTS.get(effect_name, {})
        
        # 틱 데미지 처리
        tick_damage = effect_info.get("tick_damage", 0)
        if tick_damage > 0:
            # 스트레스로 데미지 적용 (체력 시스템이 없으므로)
            stats = user_data.get("stats", {})
            current_stress = stats.get("스트레스", 0)
            stats["스트레스"] = current_stress + tick_damage * 5
            user_data["stats"] = stats
            messages.append(f"💔 [{effect_name}] 효과: 스트레스 +{tick_damage * 5}")
        
        # 지속시간 처리
        duration = effect_info.get("duration")
        if duration is not None:
            # duration 카운터 관리 (user_data에 별도 저장)
            duration_key = f"_duration_{effect_name}"
            remaining = user_data.get(duration_key, duration)
            remaining -= 1
            
            if remaining <= 0:
                effects_to_remove.append(effect_name)
                messages.append(f"⏰ [{effect_name}] 효과 종료")
                if duration_key in user_data:
                    del user_data[duration_key]
            else:
                user_data[duration_key] = remaining
                messages.append(f"⏳ [{effect_name}] 남은 시간: {remaining}턴")
    
    # 만료된 효과 제거
    for effect_name in effects_to_remove:
        if effect_name in effects:
            effects.remove(effect_name)
    
    user_data["status_effects"] = effects
    return user_data, messages


def get_status_summary(user_data: Dict[str, Any]) -> str:
    """
    캐릭터의 상태이상 요약을 반환합니다.
    """
    effects = user_data.get("status_effects", [])
    
    if not effects:
        return "✅ **상태:** 정상"
    
    buffs = []
    debuffs = []
    
    for effect_name in effects:
        effect_info = STATUS_EFFECTS.get(effect_name, {"type": "unknown"})
        if effect_info.get("type") == "buff":
            buffs.append(effect_name)
        else:
            debuffs.append(effect_name)
    
    result = ""
    
    if debuffs:
        result += "💀 **디버프:** " + ", ".join(debuffs) + "\n"
    
    if buffs:
        result += "✨ **버프:** " + ", ".join(buffs)
    
    return result.strip() if result else "✅ **상태:** 정상"


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
DEFAULT_PASSIVE_TRIGGERS = {
    # 전투/생존 관련
    "독_중독": {
        "threshold": 10,
        "passive": {
            "name": "독 내성",
            "effect": "독 피해 50% 감소, 독이 든 음식/음료 감지 가능",
            "category": "생존"
        }
    },
    "화상": {
        "threshold": 8,
        "passive": {
            "name": "열 저항",
            "effect": "화염 피해 30% 감소, 뜨거운 것을 맨손으로 잡을 수 있음",
            "category": "생존"
        }
    },
    "동상": {
        "threshold": 8,
        "passive": {
            "name": "한기 적응",
            "effect": "냉기 피해 30% 감소, 추위에 덜 영향받음",
            "category": "생존"
        }
    },
    "낙하": {
        "threshold": 5,
        "passive": {
            "name": "낙법",
            "effect": "낙하 피해 50% 감소, 구르기로 충격 분산",
            "category": "생존"
        }
    },
    "기절": {
        "threshold": 10,
        "passive": {
            "name": "철벽 정신",
            "effect": "기절 저항 +50%, 빠른 의식 회복",
            "category": "정신"
        }
    },
    "굶주림": {
        "threshold": 15,
        "passive": {
            "name": "소식가",
            "effect": "절반의 식량으로 버틸 수 있음, 배고픔 페널티 감소",
            "category": "생존"
        }
    },
    "수면부족": {
        "threshold": 20,
        "passive": {
            "name": "야행성",
            "effect": "수면 부족 페널티 없음, 야간 시야 향상",
            "category": "생존"
        }
    },
    
    # 사회/정신 관련
    "배신당함": {
        "threshold": 3,
        "passive": {
            "name": "의심의 눈",
            "effect": "거짓말/속임수 감지 확률 상승, 첫 인상에 속지 않음",
            "category": "정신"
        }
    },
    "고백거절": {
        "threshold": 3,
        "passive": {
            "name": "강철 멘탈",
            "effect": "정신 공격/모욕 저항, 감정적 동요 감소",
            "category": "정신"
        }
    },
    "협박당함": {
        "threshold": 5,
        "passive": {
            "name": "배짱",
            "effect": "위협/공포 효과 저항, 냉정함 유지",
            "category": "정신"
        }
    },
    "죽을고비": {
        "threshold": 3,
        "passive": {
            "name": "구사일생",
            "effect": "치명상 시 한 번 버틸 확률, 위기 상황 판단력 향상",
            "category": "생존"
        }
    },
    
    # 비일상 관련 (일상화 연동)
    "마법피격": {
        "threshold": 30,
        "passive": {
            "name": "마력 친화",
            "effect": "마법 감지 가능, 마법 저항 +20%",
            "category": "초자연"
        }
    },
    "드래곤조우": {
        "threshold": 5,
        "passive": {
            "name": "용의 기운",
            "effect": "약한 몬스터가 먼저 도망, 위압감 발산",
            "category": "초자연"
        }
    },
    "귀신목격": {
        "threshold": 10,
        "passive": {
            "name": "영시",
            "effect": "유령/영혼 존재 감지, 공포 저항",
            "category": "초자연"
        }
    },
    "차원이동": {
        "threshold": 3,
        "passive": {
            "name": "차원 적응",
            "effect": "이세계/차원 이동 부작용 감소, 공간 왜곡 감지",
            "category": "초자연"
        }
    },
    "시간왜곡": {
        "threshold": 5,
        "passive": {
            "name": "시간 감각",
            "effect": "시간 이상 감지, 시간 관련 효과 저항",
            "category": "초자연"
        }
    }
}


def increment_experience_counter(
    user_data: Dict[str, Any],
    counter_name: str,
    amount: int = 1,
    current_day: int = 1
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    경험 카운터를 증가시키고 패시브 획득 여부를 확인합니다.
    
    Args:
        user_data: 사용자 데이터
        counter_name: 카운터 이름 (예: "독_중독", "드래곤조우")
        amount: 증가량
        current_day: 현재 게임 내 일차
    
    Returns:
        (업데이트된 user_data, 패시브 획득 메시지 또는 None)
    """
    counters = user_data.get("experience_counters", {})
    passives = user_data.get("passives", [])
    
    # 카운터 증가
    current = counters.get(counter_name, 0)
    counters[counter_name] = current + amount
    user_data["experience_counters"] = counters
    
    # 패시브 획득 체크
    if counter_name in DEFAULT_PASSIVE_TRIGGERS:
        trigger_info = DEFAULT_PASSIVE_TRIGGERS[counter_name]
        threshold = trigger_info["threshold"]
        passive_info = trigger_info["passive"]
        
        # 이미 보유 중인지 확인
        has_passive = any(p["name"] == passive_info["name"] for p in passives)
        
        if not has_passive and counters[counter_name] >= threshold:
            # 패시브 획득!
            new_passive = {
                "name": passive_info["name"],
                "effect": passive_info["effect"],
                "category": passive_info["category"],
                "trigger": f"{counter_name} {threshold}회",
                "acquired_day": current_day
            }
            passives.append(new_passive)
            user_data["passives"] = passives
            
            msg = (
                f"🏆 **패시브 획득!**\n"
                f"**[{passive_info['name']}]** ({passive_info['category']})\n"
                f"_{passive_info['effect']}_\n"
                f"(조건: {counter_name} {threshold}회 달성)"
            )
            return user_data, msg
    
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
            if counter_name in DEFAULT_PASSIVE_TRIGGERS:
                trigger = DEFAULT_PASSIVE_TRIGGERS[counter_name]
                threshold = trigger["threshold"]
                passive_name = trigger["passive"]["name"]
                
                if passive_name in owned_passives:
                    result += f"  ✅ {counter_name}: {count}/{threshold} → **{passive_name}** 획득!\n"
                else:
                    progress = min(100, int((count / threshold) * 100))
                    bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
                    result += f"  • {counter_name}: {count}/{threshold} [{bar}] {progress}%\n"
            else:
                result += f"  • {counter_name}: {count}회\n"
    
    # AI가 부여한 패시브 목록
    ai_passives = [p for p in passives if p.get("source") == "AI"]
    if ai_passives:
        result += "\n**[AI 부여 패시브]**\n"
        for p in ai_passives:
            result += f"  🏆 **{p['name']}** ({p.get('category', '기타')})\n"
            result += f"     조건: {p.get('trigger', '?')}\n"
    
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
