import domain_manager
import json
import time
import asyncio
import logging
import re
from google.genai import types

async def call_gemini_api(client, model_id, prompt, system_instruction=""):
    if not client: return "CRITICAL_ERROR: AI 클라이언트가 연결되지 않았습니다."
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json"
    )
    
    last_error = ""
    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=config
            )
            
            if not response.candidates: continue
            
            try: raw_text = response.text
            except ValueError: continue

            clean_text = re.sub(r"```(json)?", "", raw_text).strip()
            return json.loads(clean_text)
            
        except Exception as e:
            last_error = str(e)
            await asyncio.sleep(1)
            
    return f"ERROR_FAIL: {last_error}"

# ... (기존 함수들 유지: get_objective_context ~ evaluate_custom_growth) ...
# 코드 길이상 중복되는 기존 함수들은 생략하지 않고 모두 포함해야 파일이 깨지지 않습니다.
# 아래 코드는 전체 코드를 포함하고 있습니다.

def get_objective_context(channel_id):
    board = domain_manager.get_quest_board(channel_id)
    active_quests = board.get("active", [])
    memos = board.get("memo", [])
    lore = board.get("lore", []) 
    context = "### [SYSTEM MEMORY: QUEST BOARD & ARCHIVES]\n"
    if lore:
        context += "\n[Chronicles (Long-term Memory)]\n"
        for entry in lore[-5:]: context += f"- {entry.get('title')}: {entry.get('content')}\n"
    if active_quests:
        context += "\n[Active Quests (Objectives)]\n"
        for q in active_quests: context += f"- [QUEST] {q}\n"
    if memos:
        context += "\n[Memos (Clues & Notes)]\n"
        for m in memos: context += f"- [NOTE] {m}\n"
    return context

def add_quest(channel_id, content):
    board = domain_manager.get_quest_board(channel_id)
    if content not in board["active"]:
        board["active"].append(content)
        domain_manager.update_quest_board(channel_id, board)
        return f"⚔️ **[퀘스트 수주]** {content}"
    return None

def complete_quest(channel_id, content):
    board = domain_manager.get_quest_board(channel_id)
    active_quests = board.get("active", [])
    if not active_quests: return "❌ 현재 진행 중인 퀘스트가 없습니다."

    inputs = re.split(r'[,\s]+', content.strip())
    targets_to_complete = []
    
    for inp in inputs:
        if not inp: continue
        target = None
        if inp.isdigit():
            idx = int(inp) - 1
            if 0 <= idx < len(active_quests): target = active_quests[idx]
        else:
            for q in active_quests:
                if inp in q: target = q; break
        if target and target not in targets_to_complete: targets_to_complete.append(target)

    if not targets_to_complete: return "❌ 해당하는 퀘스트를 찾을 수 없습니다."

    completed_titles = []
    for item in targets_to_complete:
        if item in board["active"]:
            board["active"].remove(item)
            completed_titles.append(item)
            lore_entry = {"title": f"달성: {item}", "content": f"파티는 '{item}'의 과업을 완수하였다.", "timestamp": time.time()}
            if "lore" not in board: board["lore"] = []
            board["lore"].append(lore_entry)

    domain_manager.update_quest_board(channel_id, board)
    summary = "\n".join([f"- ~~{t}~~" for t in completed_titles])
    return f"🏆 **[퀘스트 완료]** 총 {len(completed_titles)}건 처리됨\n{summary}"

def add_memo(channel_id, content):
    board = domain_manager.get_quest_board(channel_id)
    if "memo" not in board: board["memo"] = []
    if content not in board["memo"]:
        board["memo"].append(content)
        domain_manager.update_quest_board(channel_id, board)
        return f"📝 **[메모 기록]** {content}"
    return None

def remove_memo(channel_id, content):
    board = domain_manager.get_quest_board(channel_id)
    memos = board.get("memo", [])
    if not memos: return "❌ 기록된 메모가 없습니다."
    inputs = re.split(r'[,\s]+', content.strip())
    targets = []
    for inp in inputs:
        if not inp: continue
        target = None
        if inp.isdigit():
            idx = int(inp) - 1
            if 0 <= idx < len(memos): target = memos[idx]
        else:
            for m in memos:
                if inp in m: target = m; break
        if target and target not in targets: targets.append(target)
    
    if not targets: return "❌ 해당 메모 없음"
    for t in targets: 
        if t in board["memo"]: board["memo"].remove(t)
    domain_manager.update_quest_board(channel_id, board)
    return f"🗑️ **[메모 삭제]** {len(targets)}건"

def resolve_memo_auto(channel_id, content):
    board = domain_manager.get_quest_board(channel_id)
    memos = board.get("memo", [])
    target = None
    if content.isdigit():
        idx = int(content) - 1
        if 0 <= idx < len(memos): target = memos[idx]
    else:
        for m in memos:
            if content in m or m in content: target = m; break
    if target:
        memos.remove(target)
        board["memo"] = memos
        board.setdefault("lore", []).append({"title": "사건 해결", "content": f"단서 해결: {target}", "timestamp": time.time()})
        domain_manager.update_quest_board(channel_id, board)
        return f"📂 **[메모 해결]** '{target}' -> 연대기 이동"
    return "❌ 해당 메모 없음"

async def archive_memo_with_ai(client, model_id, channel_id, content_or_index):
    board = domain_manager.get_quest_board(channel_id)
    memos = board.get("memo", [])
    target = None
    if str(content_or_index).isdigit():
        idx = int(content_or_index) - 1
        if 0 <= idx < len(memos): target = memos.pop(idx)
    else:
        for m in memos:
            if content_or_index in m: target = m; memos.remove(m); break
    if not target: return "❌ 메모 없음"

    current_genres = domain_manager.get_active_genres(channel_id)
    current_lore = domain_manager.get_lore(channel_id)
    
    system_prompt = (
        "Chronicler Task. 1.Archive(worthy=true) 2.GenreShift(Fundamentally alters genre?). JSON only."
        f"Current: {current_genres}"
    )
    user_prompt = f"Lore: {current_lore[:200]}...\nMemo: {target}"
    
    analysis = await call_gemini_api(client, model_id, user_prompt, system_prompt)
    if isinstance(analysis, str) and "ERROR" in analysis: return f"⚠️ AI 오류: {analysis}"

    msg = f"📂 **보관:** {target}"
    if analysis:
        if analysis.get("genres"):
            new_g = [g for g in analysis["genres"] if g in ['noir', 'sf', 'wuxia', 'cyberpunk', 'high_fantasy', 'low_fantasy', 'cosmic_horror', 'post_apocalypse', 'urban_fantasy', 'steampunk', 'school_life', 'superhero']]
            if new_g and set(new_g) != set(current_genres):
                domain_manager.set_active_genres(channel_id, new_g)
                msg += f"\n🎨 **분위기 전환:** {new_g}"
        if analysis.get("worthy"):
            board.setdefault("lore", []).append({"title": "기록", "content": analysis.get("summary", target), "timestamp": time.time()})
            msg += "\n✨ **연대기 등재됨**"
        else:
            board.setdefault("archive", []).append(target)
    
    domain_manager.update_quest_board(channel_id, board)
    return msg

def get_status_message(channel_id):
    board = domain_manager.get_quest_board(channel_id)
    msg = ""
    if board.get("active"): msg += "⚔️ **퀘스트**\n" + "\n".join([f"{i+1}. {q}" for i, q in enumerate(board["active"])]) + "\n\n"
    if board.get("memo"): msg += "📝 **메모**\n" + "\n".join([f"{i+1}. {m}" for i, m in enumerate(board["memo"])])
    return msg if msg else "📭 비어있음"

def get_active_quests_text(channel_id):
    board = domain_manager.get_quest_board(channel_id)
    quests = board.get("active", [])
    if not quests: return "📭 **현재 수행 중인 퀘스트가 없습니다.**"
    return "⚔️ **[현재 퀘스트 목록]**\n" + "\n".join([f"{i+1}. {q}" for i, q in enumerate(quests)])

def get_memos_text(channel_id):
    board = domain_manager.get_quest_board(channel_id)
    memos = board.get("memo", [])
    if not memos: return "📭 **기록된 메모가 없습니다.**"
    return "📝 **[메모 목록]**\n" + "\n".join([f"{i+1}. {m}" for i, m in enumerate(memos)])

def get_lore_book(channel_id):
    board = domain_manager.get_quest_board(channel_id)
    lore = board.get("lore", [])
    if not lore: return "📖 기록 없음"
    return "📖 **[연대기]**\n" + "\n".join([f"{i+1}. {l['content']}" for i, l in enumerate(lore)])

async def generate_chronicle_from_history(client, model_id, channel_id):
    domain = domain_manager.get_domain(channel_id)
    board = domain_manager.get_quest_board(channel_id)
    history = domain.get('history', [])
    if not history or len(history) < 2: return "⚠️ 대화 기록 부족"
    history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history[-30:]])
    
    recent_events = "\n".join([f"- {l['content']}" for l in board.get("lore", [])[-5:]])
    context = f"[Quests]: {board.get('active', [])}\n[Memos]: {board.get('memo', [])}"

    system_prompt = "Chronicler. Summarize history+events. JSON: {title, content}"
    user_prompt = f"History:\n{history_text}\n\nRecent Events:\n{recent_events}\n\nContext:\n{context}"
    
    res = await call_gemini_api(client, model_id, user_prompt, system_prompt)
    if isinstance(res, dict) and res.get("title"):
        board.setdefault("lore", []).append({"title": res.get("title"), "content": res.get("content"), "timestamp": time.time()})
        domain_manager.update_quest_board(channel_id, board)
        return f"✨ **연대기 생성:** {res.get('title')}\n> {res.get('content')}"
    return "⚠️ 생성 실패"

def export_chronicles_incremental(channel_id, mode="new"):
    board = domain_manager.get_quest_board(channel_id)
    lore = board.get("lore", [])
    last_export = board.get("last_export_time", 0.0)
    target = lore if mode in ["all", "전체"] else [e for e in lore if e.get('timestamp', 0) > last_export]
    if not target: return None, "🚫 신규 기록 없음"
    txt = "[ 연대기 ]\n\n" + "\n\n".join([f"[{time.strftime('%Y-%m-%d %H:%M', time.localtime(e.get('timestamp',0)))}] {e.get('content')}" for e in target])
    if mode not in ["all", "전체"]:
        board["last_export_time"] = time.time()
        domain_manager.update_quest_board(channel_id, board)
    return txt, "📜 추출 완료"

async def evaluate_custom_growth(client, model_id, lvl, xp, rule):
    if not client: return {"leveled_up": False}
    res = await call_gemini_api(client, model_id, f"Lv:{lvl}, XP:{xp}\nRule:{rule}", "Judge level up. JSON: {leveled_up:bool, new_level:int, reason:str}")
    if isinstance(res, dict): return res
    return {"leveled_up": False}

async def analyze_character_evolution(client, model_id, channel_id, user_id, current_desc):
    if not client: return None
    domain = domain_manager.get_domain(channel_id)
    history = domain.get('history', [])[-40:]
    history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history])
    board = domain_manager.get_quest_board(channel_id)
    memos = board.get("memo", [])
    recent_lore = board.get("lore", [])[-10:]
    lore_text = "\n".join([f"- {l['content']}" for l in recent_lore])
    
    system_prompt = (
        "Character Profile Editor. Update description based on events.\n"
        "Rules: PERMANENCE ONLY (scars, titles, power), PRESERVE existing traits, MERGE seamlessly.\n"
        "Output JSON: {\"description\": \"Updated text (Korean)\"}"
    )
    user_prompt = f"Desc:\n{current_desc}\n\nHistory:\n{history_text}\n\nClues:\n{memos}\n\nLore:\n{lore_text}\nTask: Update description."
    
    res = await call_gemini_api(client, model_id, user_prompt, system_prompt)
    if isinstance(res, dict) and res.get("description"): return res.get("description")
    return None

# [신규 기능] 내 정보(Info) 요약 생성
async def generate_character_info_view(client, model_id, channel_id, user_id, current_desc, inventory_dict):
    """
    [기능] AI에게 캐릭터 데이터를 주고 '외형 요약', '재산', '주요 NPC 관계'를 추출합니다.
    """
    if not client: return None
    
    # 1. 정보 수집
    domain = domain_manager.get_domain(channel_id)
    history = domain.get('history', [])[-50:] # 관계 파악을 위해 최근 대화 참조
    history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history])
    
    # NPC 목록 가져오기
    npcs = domain.get('npcs', {})
    npc_list_text = ", ".join(npcs.keys()) if npcs else "(None)"
    
    # 인벤토리 텍스트 변환
    inv_text = ", ".join([f"{k} x{v}" for k, v in inventory_dict.items()]) if inventory_dict else "(빈털터리)"

    system_prompt = (
        "You are a UI Generator for a TRPG status window. Summarize the character's current state.\n\n"
        "### OUTPUT FORMAT (JSON ONLY)\n"
        "{\n"
        "  \"appearance_summary\": \"Extract a concise 1-sentence visual summary from the Description (e.g., 'A scarred knight in worn leather armor').\",\n"
        "  \"assets_summary\": \"Summarize wealth/items. If inventory provided, list key items. If not, infer from context (e.g., '50 Gold coins, Rusty Sword').\",\n"
        "  \"relationships\": [ \n"
        "      \"NPC_Name: Relationship_Keyword (Max 3 words)\" \n"
        "  ] \n"
        "}\n\n"
        "### RULES\n"
        "1. **Relationships:** Identify 3-5 most relevant NPCs from History/NPC List. Describe the bond strictly in 3 words or less (e.g., 'Enemy', 'Old Friend', 'Business Partner').\n"
        "2. **Language:** Korean.\n"
    )
    
    user_prompt = (
        f"### Full Description\n{current_desc}\n\n"
        f"### Inventory Data\n{inv_text}\n\n"
        f"### Known NPCs\n{npc_list_text}\n\n"
        f"### Recent History (For Relationships)\n{history_text}\n\n"
        "Task: Generate Status Window View."
    )
    
    res = await call_gemini_api(client, model_id, user_prompt, system_prompt)
    
    if isinstance(res, dict):
        return res
    return None