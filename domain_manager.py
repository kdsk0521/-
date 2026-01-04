import os
import json
import logging

# =========================================================
# 기본값 및 경로 설정
# =========================================================
DEFAULT_LORE = "[장르: 잔혹한 다크 판타지 느와르]"
DEFAULT_RULES = """
[게임 규칙: 표준 TRPG 시스템]
1. 판정: 모든 행동은 !r 1d20 (20면체 주사위)을 통해 결정됩니다.
2. 난이도(DC): 보통 10 / 어려움 15 / 매우 어려움 20 / 불가능 25
3. 전투: 주사위 값이 높을수록 더 효율적이고 치명적인 공격을 성공시킵니다.
4. 성장: 캐릭터는 행동과 선택을 통해 경험치를 얻고 레벨업하며 스탯을 올립니다.
"""

DATA_DIR = "data"
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
LORE_DIR = os.path.join(DATA_DIR, "lores")
RULES_DIR = os.path.join(DATA_DIR, "rules")

def initialize_folders():
    for path in [SESSIONS_DIR, LORE_DIR, RULES_DIR]:
        if not os.path.exists(path):
            os.makedirs(path)

def get_session_file_path(channel_id):
    return os.path.join(SESSIONS_DIR, f"{channel_id}.json")

def get_lore_file_path(channel_id):
    return os.path.join(LORE_DIR, f"lore_{channel_id}.txt")

def get_rules_file_path(channel_id):
    return os.path.join(RULES_DIR, f"rules_{channel_id}.txt")

def _create_new_domain():
    return {
        "history": [],        
        "participants": {},   
        "settings": {
            "mode": "auto",              
            "growth_system": "standard", 
            "session_locked": False,
            "bot_disabled": False,
            "is_prepared": False
        },
        "fief": {             
            "name": "시작의 영지", "gold": 1000, "supplies": 100, 
            "population": 50, "buildings": [], "security": 60
        },
        "ai_notes": {"observations": [], "requests": []},
        "world_state": {
            "day": 1, "time_slot": "오전", "weather": "맑음", "doom": 0
        },
        "quest_board": {
            "active": [], "memo": [], "archive": []
        }
    }

def get_domain(channel_id):
    path = get_session_file_path(channel_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "settings" not in data: data["settings"] = _create_new_domain()["settings"]
                if "is_prepared" not in data["settings"]: data["settings"]["is_prepared"] = False
                if "world_state" not in data: data["world_state"] = _create_new_domain()["world_state"]
                if "quest_board" not in data: data["quest_board"] = _create_new_domain()["quest_board"]
                return data
        except:
            return _create_new_domain()
    return _create_new_domain()

def save_domain(channel_id, data):
    try:
        with open(get_session_file_path(channel_id), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"저장 실패: {e}")

# =========================================================
# 참가자 이탈 및 중간 참가 (Join / Leave)
# =========================================================
def leave_participant(channel_id, uid):
    """플레이어를 이탈 상태(Away)로 변경합니다."""
    d = get_domain(channel_id)
    uid = str(uid)
    if uid in d["participants"]:
        d["participants"][uid]["status"] = "away"
        save_domain(channel_id, d)
        return d["participants"][uid]["mask"]
    return None

def update_participant(channel_id, user):
    """참가자 정보를 업데이트하거나 새로 등록합니다."""
    d = get_domain(channel_id)
    uid = str(user.id)
    
    if uid in d["participants"]:
        p = d["participants"][uid]
        p["name"] = user.display_name
        # 이탈 상태였다면 자동으로 활동 상태로 복구
        if p.get("status") == "away":
            p["status"] = "active"
        save_domain(channel_id, d)
        return True
    
    # 세션이 잠겨있으면 새로운 유저의 참가를 막음 (마스터가 열어줘야 함)
    if d["settings"].get("session_locked", False):
        return False
        
    # 신규 참가자 등록
    d["participants"][uid] = {
        "name": user.display_name, "mask": user.display_name,
        "level": 1, "xp": 0, "next_xp": 100, "stats": {"근력":10,"지능":10,"매력":10,"스트레스":0},
        "relations":{}, "inventory":{}, "status_effects": [], "description": "", "status":"active"
    }
    save_domain(channel_id, d)
    return True

# =========================================================
# 세션 잠금 및 해제 (Lock / Unlock)
# =========================================================
def set_session_lock(channel_id, status: bool):
    """세션 잠금 상태를 명시적으로 설정합니다."""
    d = get_domain(channel_id)
    d["settings"]["session_locked"] = status
    save_domain(channel_id, d)
    return status

def toggle_session_lock(channel_id):
    """세션 잠금 상태를 반전시킵니다."""
    d = get_domain(channel_id)
    cur = d["settings"].get("session_locked", False)
    d["settings"]["session_locked"] = not cur
    save_domain(channel_id, d)
    return d["settings"]["session_locked"]

# =========================================================
# 기타 상태 조회 함수들
# =========================================================
def get_world_state(channel_id):
    return get_domain(channel_id).get("world_state")

def update_world_state(channel_id, new_state):
    d = get_domain(channel_id)
    d["world_state"] = new_state
    save_domain(channel_id, d)

def get_quest_board(channel_id):
    return get_domain(channel_id).get("quest_board")

def update_quest_board(channel_id, new_board):
    d = get_domain(channel_id)
    d["quest_board"] = new_board
    save_domain(channel_id, d)

def get_party_status_context(channel_id):
    d = get_domain(channel_id)
    participants = [p for p in d["participants"].values() if p.get("status") == "active"]
    if not participants: return "No active players."
    all_effects = [e for p in participants for e in p.get("status_effects", [])]
    status_summary = "Healthy" if not all_effects else f"Suffering from {', '.join(set(all_effects))}"
    return f"Party Condition: {status_summary}"

def is_prepared(channel_id):
    return get_domain(channel_id)["settings"].get("is_prepared", False)

def set_prepared(channel_id, status: bool):
    d = get_domain(channel_id)
    d["settings"]["is_prepared"] = status
    save_domain(channel_id, d)

def is_bot_disabled(channel_id):
    return get_domain(channel_id)["settings"].get("bot_disabled", False)

def set_bot_disabled(channel_id, disabled: bool):
    d = get_domain(channel_id); d["settings"]["bot_disabled"] = disabled; save_domain(channel_id, d)

def get_user_mask(channel_id, uid):
    p = get_domain(channel_id)["participants"].get(str(uid))
    return p.get("mask", "Unknown") if p else "Unknown"

def set_user_mask(channel_id, uid, mask):
    d = get_domain(channel_id); uid = str(uid)
    if uid in d["participants"]: d["participants"][uid]["mask"] = mask; save_domain(channel_id, d)

def set_user_description(channel_id, uid, desc):
    d = get_domain(channel_id); uid = str(uid)
    if uid in d["participants"]:
        if desc.strip() in ["초기화", "reset"]: d["participants"][uid]["description"] = ""
        else:
            cur = d["participants"][uid].get("description", "")
            d["participants"][uid]["description"] = f"{cur} {desc}".strip()
        save_domain(channel_id, d)

def get_user_description(channel_id, uid):
    return get_domain(channel_id)["participants"].get(str(uid), {}).get("description", "")

def get_active_participants_summary(channel_id):
    d = get_domain(channel_id)
    active = [f"{p['mask']}({p['description']})" if p.get('description') else p['mask'] 
              for p in d["participants"].values() if p.get("status") == "active"]
    return ", ".join(active)

def get_lore(channel_id):
    path = get_lore_file_path(channel_id)
    if os.path.exists(path):
        content = open(path, "r", encoding="utf-8").read().strip()
        if content: return content
    return DEFAULT_LORE

def append_lore(channel_id, text):
    path = get_lore_file_path(channel_id)
    if text.strip() in ["초기화", "reset"]: 
        if os.path.exists(path): os.remove(path)
    else:
        cur = ""
        if os.path.exists(path): cur = open(path, "r", encoding="utf-8").read().strip()
        with open(path, 'w', encoding='utf-8') as f: f.write(f"{cur}\n{text}".strip())

def get_rules(channel_id):
    path = get_rules_file_path(channel_id)
    if os.path.exists(path):
        content = open(path, "r", encoding="utf-8").read().strip()
        if content: return content
    return DEFAULT_RULES

def append_rules(channel_id, text):
    path = get_rules_file_path(channel_id)
    if text.strip() in ["초기화", "reset"]:
        if os.path.exists(path): os.remove(path)
    else:
        cur = ""
        if os.path.exists(path): cur = open(path, "r", encoding="utf-8").read().strip()
        with open(path, 'w', encoding='utf-8') as f: f.write(f"{cur}\n{text}".strip())

def reset_domain(channel_id):
    for f in [get_session_file_path(channel_id), get_lore_file_path(channel_id), get_rules_file_path(channel_id)]:
        if os.path.exists(f): os.remove(f)

def append_history(channel_id, role, content):
    d = get_domain(channel_id); d['history'].append({"role": role, "content": content})
    if len(d['history']) > 40: d['history'] = d['history'][-40:]
    save_domain(channel_id, d)