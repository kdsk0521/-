import random

DND_XP_TABLE = {
    1: 300, 2: 900, 3: 2700, 4: 6500, 5: 14000, 
    6: 23000, 7: 34000, 8: 48000, 9: 64000, 10: 85000
}

def _calc_standard_growth(user_data, amount):
    user_data["xp"] += amount
    leveled_up = False
    
    if not isinstance(user_data["level"], int):
        return user_data, False

    while user_data["xp"] >= user_data["next_xp"]:
        user_data["xp"] -= user_data["next_xp"]
        user_data["level"] += 1
        user_data["next_xp"] = int(user_data["next_xp"] * 1.2)
        leveled_up = True
        
        bonus = random.choice(["근력", "지능", "매력"])
        if bonus in user_data["stats"]:
            user_data["stats"][bonus] += 1
        
    return user_data, leveled_up

def _calc_dnd_growth(user_data, amount):
    user_data["xp"] += amount
    
    if not isinstance(user_data["level"], int):
        return user_data, False

    current_lv = user_data["level"]
    target_xp = DND_XP_TABLE.get(current_lv, 999999)
    
    leveled_up = False
    if user_data["xp"] >= target_xp:
        user_data["xp"] -= target_xp
        user_data["level"] += 1
        user_data["next_xp"] = DND_XP_TABLE.get(user_data["level"], 999999)
        leveled_up = True
        
        bonus = random.choice(["근력", "지능", "매력"])
        if bonus in user_data["stats"]:
            user_data["stats"][bonus] += 1
    else:
        user_data["next_xp"] = target_xp

    return user_data, leveled_up

def _calc_milestone_growth(user_data, amount):
    user_data["xp"] += amount
    return user_data, False

def gain_experience(user_data, amount, system_type="standard"):
    if "level" not in user_data: user_data["level"] = 1
    if "xp" not in user_data: user_data["xp"] = 0
    if "next_xp" not in user_data: user_data["next_xp"] = 100

    mask = user_data["mask"]
    
    if system_type == "dnd":
        user_data, leveled_up = _calc_dnd_growth(user_data, amount)
    elif system_type == "milestone":
        user_data, leveled_up = _calc_milestone_growth(user_data, amount)
    else:
        user_data, leveled_up = _calc_standard_growth(user_data, amount)

    if leveled_up:
        return user_data, f"🎉 **레벨 업!** {mask}님이 **Lv.{user_data['level']}**가 되었습니다!", True
    else:
        lv_str = f"Lv.{user_data['level']}" if isinstance(user_data['level'], int) else f"등급: {user_data['level']}"
        return user_data, f"🆙 **경험치 획득:** {mask} +{amount} XP (현재: {user_data['xp']}, {lv_str})", False

def train_character(user_data, stat_type):
    stats = user_data.get("stats", {})
    if stat_type not in stats: stats[stat_type] = 0
        
    current_val = stats.get(stat_type, 0)
    stress = stats.get("스트레스", 0)
    
    fail_chance = 0.1 + (stress * 0.005) 
    is_success = random.random() > fail_chance

    if is_success:
        gain = random.randint(2, 5)
        stats[stat_type] = current_val + gain
        stats["스트레스"] = stress + random.randint(5, 10)
        result_msg = f"✨ **훈련 성공!** {stat_type} +{gain}"
        status = "Success"
    else:
        gain = 1
        stats[stat_type] = current_val + gain
        stats["스트레스"] = stress + random.randint(10, 20)
        result_msg = f"💦 **훈련 실수...** {stat_type} +{gain}, 스트레스 상승!"
        status = "Fail"

    user_data["stats"] = stats
    return user_data, result_msg, status

def rest_character(user_data):
    stats = user_data.get("stats", {})
    stress = stats.get("스트레스", 0)
    recovery = random.randint(20, 40)
    new_stress = max(0, stress - recovery)
    stats["스트레스"] = new_stress
    user_data["stats"] = stats
    
    # [신규] 휴식 시 일부 상태이상 회복 (예: 지침)
    status_list = user_data.get("status_effects", [])
    if "지침" in status_list:
        status_list.remove("지침")
        user_data["status_effects"] = status_list
        return user_data, f"💤 **휴식...** 스트레스 -{recovery} (상태이상 '지침' 회복)"
        
    return user_data, f"💤 **휴식...** 스트레스 -{recovery} (현재: {new_stress})"

# [수정됨] 범용 건설 함수
def build_facility(fief_data, building_name, cost_gold, effect_desc=""):
    if fief_data["gold"] < cost_gold:
        return fief_data, f"❌ **건설 실패:** 자금이 부족합니다. (필요: {cost_gold}G, 보유: {fief_data['gold']}G)", False
    
    fief_data["gold"] -= cost_gold
    fief_data["buildings"].append(f"{building_name}")
    
    if "인구" in effect_desc or "주거" in effect_desc: fief_data["population"] += 10
    if "치안" in effect_desc or "경비" in effect_desc: fief_data["security"] += 10
    if "식량" in effect_desc or "농사" in effect_desc: fief_data["supplies"] += 50
        
    return fief_data, f"🔨 **건설 완료:** {building_name} (비용: {cost_gold}G)\n효과: {effect_desc}", True

def collect_taxes(fief_data):
    pop = fief_data["population"]
    tax = int(pop * random.uniform(0.8, 1.2))
    fief_data["gold"] += tax
    fief_data["security"] -= random.randint(2, 6)
    return fief_data, f"💰 **세금 징수:** +{tax}G"

def modify_relationship(user_data, target_name, amount):
    rels = user_data.get("relations", {})
    current = rels.get(target_name, 0)
    new_val = current + amount
    rels[target_name] = new_val
    user_data["relations"] = rels
    emoji = "💖" if amount > 0 else "💔"
    return user_data, f"{emoji} **{target_name}** 관계: {amount:+} ({new_val})"

# 인벤토리 관리 로직
def update_inventory(user_data, action, item_name, count=1):
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
                msg = f"📉 **사용/버림:** {item_name} x{count} (남음: {inv[item_name]})"
    else:
        msg = "⚠️ 알 수 없는 동작"

    user_data["inventory"] = inv
    return user_data, msg

# [신규] 상태이상 관리 로직
def update_status_effect(user_data, action, effect_name):
    effects = user_data.get("status_effects", [])
    
    if action == "add":
        if effect_name not in effects:
            effects.append(effect_name)
            msg = f"💀 **상태이상 발생:** [{effect_name}]"
        else:
            msg = f"⚠️ 이미 [{effect_name}] 상태입니다."
    elif action == "remove":
        if effect_name in effects:
            effects.remove(effect_name)
            msg = f"✨ **상태 회복:** [{effect_name}] 제거됨"
        else:
            msg = f"⚠️ [{effect_name}] 상태가 아닙니다."
    else:
        msg = "⚠️ 알 수 없는 동작"
        
    user_data["status_effects"] = effects
    return user_data, msg