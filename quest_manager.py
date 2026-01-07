import domain_manager
import json
import time
import asyncio
import logging
import re
from google.genai import types

# =========================================================
# AI 유틸리티
# =========================================================
async def call_gemini_api(client, model_id, prompt, system_instruction=""):
    if not client: return None
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        temperature=0.1 # 판단 로직이므로 온도를 낮춤
    )
    
    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=config
            )
            clean_text = re.sub(r"```(json)?", "", response.text).strip()
            return json.loads(clean_text)
        except Exception:
            await asyncio.sleep(1)
    return None

# =========================================================
# 컨텍스트 생성 (Context Generation)
# =========================================================
def get_objective_context(channel_id):
    """현재 퀘스트와 메모 상태를 AI가 읽기 좋은 텍스트로 변환"""
    board = domain_manager.get_quest_board(channel_id)
    if not board: return "No active quests or memos."
    
    active = board.get("active", [])
    memos = board.get("memos", [])
    archives = board.get("archive", []) # 보관된 정보도 컨텍스트에 일부 반영
    
    txt = "### [QUESTS & MEMOS]\n"
    if active:
        txt += "**Active Objectives:**\n" + "\n".join([f"- {q}" for q in active]) + "\n"
    else:
        txt += "- No active quests.\n"
        
    if memos:
        txt += "**Active Memos:**\n" + "\n".join([f"- {m}" for m in memos]) + "\n"
    else:
        txt += "- No active memos.\n"

    # 보관된 메모 중 최근 3개만 보여주어 맥락 유지
    if archives:
        txt += "**Archived Info (Reference):**\n" + "\n".join([f"- {m}" for m in archives[-3:]])
        
    return txt

def get_active_quests_text(channel_id):
    board = domain_manager.get_quest_board(channel_id) or {}
    active = board.get("active", [])
    if not active: return "📭 현재 진행 중인 퀘스트가 없습니다."
    return "🔥 **진행 중인 퀘스트:**\n" + "\n".join([f"{i+1}. {q}" for i, q in enumerate(active)])

def get_memos_text(channel_id):
    board = domain_manager.get_quest_board(channel_id) or {}
    memos = board.get("memos", [])
    if not memos: return "📭 저장된 메모가 없습니다."
    return "📝 **메모 목록:**\n" + "\n".join([f"- {m}" for m in memos])

def get_status_message(channel_id):
    """퀘스트와 메모 상태를 한 번에 보여줌"""
    q_text = get_active_quests_text(channel_id)
    m_text = get_memos_text(channel_id)
    return f"{q_text}\n\n{m_text}"

# =========================================================
# 퀘스트 & 메모 관리 (CRUD)
# =========================================================
def _get_board(cid):
    d = domain_manager.get_domain(cid)
    if "quest_board" not in d or not isinstance(d["quest_board"], dict):
        d["quest_board"] = {"active": [], "completed": [], "memos": [], "archive": [], "lore": []}
    
    # 키가 없을 경우 보정
    if "memos" not in d["quest_board"]: d["quest_board"]["memos"] = []
    if "archive" not in d["quest_board"]: d["quest_board"]["archive"] = []
    if "lore" not in d["quest_board"]: d["quest_board"]["lore"] = []
    
    return d["quest_board"]

def _save_board(cid, board):
    domain_manager.update_quest_board(cid, board)

def add_quest(channel_id, content):
    if not content: return None
    board = _get_board(channel_id)
    if content not in board["active"]:
        board["active"].append(content)
        _save_board(channel_id, board)
        return f"🔥 **퀘스트 등록:** {content}"
    return "⚠️ 이미 등록된 퀘스트입니다."

def complete_quest(channel_id, content):
    if not content: return None
    board = _get_board(channel_id)
    
    target = None
    for q in board["active"]:
        if content in q or q in content:
            target = q
            break
            
    if target:
        board["active"].remove(target)
        if "completed" not in board: board["completed"] = []
        board["completed"].append(target)
        _save_board(channel_id, board)
        return f"✅ **퀘스트 완료:** {target}"
    return "⚠️ 해당 퀘스트를 찾을 수 없습니다."

def add_memo(channel_id, content):
    if not content: return None
    board = _get_board(channel_id)
    if content not in board["memos"]:
        board["memos"].append(content)
        _save_board(channel_id, board)
        return f"📝 **메모 추가:** {content}"
    return "⚠️ 이미 있는 메모입니다."

def remove_memo(channel_id, content):
    """메모를 단순히 삭제합니다 (수동 삭제용)."""
    if not content: return None
    board = _get_board(channel_id)
    memos = board.get("memos", [])
    
    target = None
    for m in memos:
        if content in m: # 부분 일치 허용
            target = m
            break
            
    if target:
        memos.remove(target)
        board["memos"] = memos
        _save_board(channel_id, board)
        return f"🗑️ **메모 삭제:** {target}"
    return "⚠️ 해당 메모를 찾을 수 없습니다."

def resolve_memo_auto(channel_id, content):
    """
    AI(좌뇌)가 'Memo Remove' 명령을 내렸을 때 호출됩니다.
    안전을 위해 바로 삭제하지 않고 '보관함'으로 보냅니다.
    """
    board = _get_board(channel_id)
    memos = board.get("memos", [])
    
    target = None
    if str(content).isdigit():
        idx = int(content) - 1
        if 0 <= idx < len(memos): target = memos[idx]
    else:
        for m in memos:
            if content in m: target = m; break
            
    if target:
        memos.remove(target)
        if "archive" not in board: board["archive"] = []
        board["archive"].append(target)
        
        _save_board(channel_id, board)
        return f"🗄️ **[메모 해결]** '{target}' (보관함 이동)"
    return None

# =========================================================
# AI 연동 기능
# =========================================================
async def archive_memo_with_ai(client, model_id, channel_id, content_or_index):
    """
    [AI] 메모의 내용을 분석하여 '영구 보관(장비/관계)'할지 '완전 삭제(소모품)'할지 결정합니다.
    """
    board = _get_board(channel_id)
    memos = board.get("memos", [])
    
    target = None
    if str(content_or_index).isdigit():
        idx = int(content_or_index) - 1
        if 0 <= idx < len(memos): target = memos[idx]
    else:
        for m in memos:
            if content_or_index in m: target = m; break
            
    if not target: return "❌ 해당 메모를 찾을 수 없습니다."

    system_prompt = (
        "You are a Data Librarian. Analyze the memo content and categorize it.\n"
        "**Rules:**\n"
        "1. **DELETE:** Consumables, temporary status, trivial noise.\n"
        "2. **ARCHIVE:** Equipment, Appearance changes, Relationships, Story Clues.\n\n"
        "Output JSON: {\"action\": \"DELETE\" or \"ARCHIVE\", \"reason\": \"Short explanation in Korean\"}"
    )
    user_prompt = f"Memo Content: {target}"
    
    decision = await call_gemini_api(client, model_id, user_prompt, system_prompt)
    
    memos.remove(target)
    board["memos"] = memos
    
    msg = ""
    if decision and decision.get("action") == "ARCHIVE":
        if "archive" not in board: board["archive"] = []
        board["archive"].append(target)
        msg = f"🗄️ **[보관됨]** {target}\n(사유: {decision.get('reason')})"
    else:
        reason = decision.get("reason") if decision else "소모성/임시 데이터"
        msg = f"🗑️ **[삭제됨]** {target}\n(사유: {reason})"
    
    _save_board(channel_id, board)
    return msg

async def generate_character_info_view(client, model_id, channel_id, user_id, current_desc, inventory_dict):
    """[AI] 캐릭터 요약 정보 생성"""
    inv_text = ", ".join([f"{k} x{v}" for k, v in inventory_dict.items()]) if inventory_dict else "(빈털터리)"
    history_logs = domain_manager.get_domain(channel_id).get('history', [])[-20:]
    history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history_logs])

    system_prompt = (
        "You are a UI Generator for a TRPG status window.\n"
        "Analyze the character's description, inventory, and recent history.\n"
        "Output JSON: {"
        "  \"appearance_summary\": \"Concise 1-sentence visual summary.\","
        "  \"assets_summary\": \"Summarize wealth/power based on inventory.\","
        "  \"relationships\": [\"NPC_Name: Relationship_Keyword (max 3 words)\"]"
        "}"
    )
    user_prompt = f"Desc:\n{current_desc}\n\nInv:\n{inv_text}\n\nHistory:\n{history_text}"
    return await call_gemini_api(client, model_id, user_prompt, system_prompt)

async def generate_chronicle_from_history(client, model_id, channel_id):
    """[AI] 연대기(요약본) 생성"""
    domain = domain_manager.get_domain(channel_id)
    board = _get_board(channel_id)
    history = domain.get('history', [])
    if not history: return "기록된 역사가 없습니다."
    
    full_text = "\n".join([f"{h['role']}: {h['content']}" for h in history[-50:]])
    system_prompt = (
        "You are the Chronicler. Summarize the provided RPG session log into a compelling narrative summary.\n"
        "Focus on key events, decisions, and outcomes. Write in Korean."
    )
    system_prompt_json = system_prompt + "\nOutput JSON: {\"title\": \"Title\", \"summary\": \"Content...\"}"
    
    res = await call_gemini_api(client, model_id, f"Log:\n{full_text}", system_prompt_json)
    
    if res and "summary" in res:
        entry = {
            "title": res.get("title", "기록"),
            "content": res.get("summary"),
            "timestamp": time.time()
        }
        board["lore"].append(entry)
        _save_board(channel_id, board)
        return f"📜 **[연대기 기록됨]** {entry['title']}\n{entry['content'][:100]}..."
    return "연대기 생성 실패"

def get_lore_book(channel_id):
    """채팅창에 연대기 목록을 간략히 표시"""
    board = _get_board(channel_id)
    lore = board.get("lore", [])
    if not lore: return "📖 기록된 연대기가 없습니다."
    
    msg = "📖 **[연대기 목록]**\n"
    for i, entry in enumerate(lore):
        date_str = time.strftime('%Y-%m-%d', time.localtime(entry.get('timestamp', 0)))
        msg += f"{i+1}. [{date_str}] {entry.get('title')}\n"
    
    msg += "\n💡 `!추출`은 대화 로그를, `!연대기 추출`은 이 요약본을 파일로 저장합니다."
    return msg

async def evaluate_custom_growth(client, model_id, current_level, current_xp, rules_text):
    """[AI] 레벨업 판정"""
    system_prompt = "Evaluate level up. JSON Output: {\"leveled_up\": bool, \"new_level\": int, \"reason\": \"str\"}"
    user_prompt = f"Rules:\n{rules_text}\n\nCurrent Level: {current_level}, XP: {current_xp}"
    return await call_gemini_api(client, model_id, user_prompt, system_prompt)

# =========================================================
# [핵심] 추출 시스템 (로그 vs 연대기)
# =========================================================
def export_chronicles_incremental(channel_id, mode=""):
    """
    [로그 추출] 대화 내역(History)을 텍스트 파일로 추출
    - mode="전체", "full": 처음부터 끝까지 추출
    - mode="" (기본): 마지막 추출 이후 내용만 추출 (증분)
    """
    domain = domain_manager.get_domain(channel_id)
    history = domain.get('history', [])
    
    if not history: return None, "❌ 기록된 대화가 없습니다."

    last_idx = domain.get('last_export_idx', 0)
    current_len = len(history)

    start_idx = 0
    export_type = "전체"

    if mode in ["전체", "full", "all"]:
        start_idx = 0
        export_type = "전체(Full)"
    else:
        start_idx = last_idx
        export_type = "증분(New Only)"

    if start_idx >= current_len and export_type != "전체(Full)":
        return None, "✅ 새로운 대화 내용이 없습니다. (이미 최신 상태입니다)\n처음부터 다시 뽑으려면 `!추출 전체`를 입력하세요."

    export_lines = [
        f"=== Lorekeeper Session Log [{export_type}] ===",
        f"Export Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Range: Msg {start_idx + 1} ~ {current_len}\n",
        "-" * 40
    ]

    target_history = history[start_idx:]
    for entry in target_history:
        role = entry.get('role', 'Unknown')
        content = entry.get('content', '')
        if role == 'User': export_lines.append(f"[Player]: {content}")
        elif role == 'Char': export_lines.append(f"[Story]: {content}")
        elif role == 'System': export_lines.append(f"[System]: {content}")
        else: export_lines.append(f"[{role}]: {content}")
        export_lines.append("")

    domain['last_export_idx'] = current_len
    domain_manager.save_domain(channel_id, domain)

    return "\n".join(export_lines), f"📜 **대화 로그 추출 완료 ({export_type})**\n(총 {len(target_history)}개의 메시지를 저장했습니다.)"

def export_lore_book_file(channel_id):
    """
    [연대기 추출] 요약된 연대기(Lore) 목록을 텍스트 파일로 추출
    """
    board = _get_board(channel_id)
    lore = board.get("lore", [])
    
    if not lore: return None, "❌ 기록된 연대기가 없습니다. `!연대기 생성`을 먼저 진행해주세요."

    export_lines = [
        "=== Lorekeeper Chronicles (Summary) ===",
        f"Export Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total Entries: {len(lore)}\n",
        "-" * 40
    ]

    for i, entry in enumerate(lore):
        title = entry.get("title", "Untitled")
        content = entry.get("content", "")
        timestamp = entry.get("timestamp", 0)
        date_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(timestamp))
        
        export_lines.append(f"#{i+1}. {title} [{date_str}]")
        export_lines.append(content)
        export_lines.append("-" * 20)
        export_lines.append("")

    return "\n".join(export_lines), f"📖 **연대기 추출 완료** (총 {len(lore)}개의 기록)"