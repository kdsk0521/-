import domain_manager

def add_quest(channel_id, content):
    """퀘스트 보드에 새로운 목표를 추가합니다."""
    board = domain_manager.get_quest_board(channel_id)
    board["active"].append(content)
    domain_manager.update_quest_board(channel_id, board)
    return f"📌 **퀘스트 등록:** {content}"

def complete_quest(channel_id, target):
    """퀘스트를 완료 처리합니다."""
    board = domain_manager.get_quest_board(channel_id)
    active_quests = board["active"]
    completed_item = None
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(active_quests): completed_item = active_quests.pop(idx)
    else:
        for i, q in enumerate(active_quests):
            if target in q: 
                completed_item = active_quests.pop(i)
                break
    if completed_item:
        domain_manager.update_quest_board(channel_id, board)
        world = domain_manager.get_world_state(channel_id)
        day = world.get('day', 1) if world else 1
        log_entry = f"\n[History - Day {day}] 퀘스트 완료: {completed_item}"
        domain_manager.append_lore(channel_id, log_entry)
        return f"✅ **퀘스트 완료!** 역사에 기록되었습니다.\n(내용: {completed_item})"
    else:
        return "❌ 해당 퀘스트를 찾을 수 없습니다."

def add_memo(channel_id, content):
    """단기 메모장에 내용을 적습니다."""
    board = domain_manager.get_quest_board(channel_id)
    board["memo"].append(content)
    domain_manager.update_quest_board(channel_id, board)
    return f"📝 **메모 추가:** {content}"

def archive_memo(channel_id, target):
    """메모를 '보관함(archive)'으로 이동합니다."""
    board = domain_manager.get_quest_board(channel_id)
    memos = board["memo"]
    if "archive" not in board: board["archive"] = []
    archived_item = None
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(memos): archived_item = memos.pop(idx)
    else:
        for i, m in enumerate(memos):
            if target in m: 
                archived_item = memos.pop(i)
                break
    if archived_item:
        board["archive"].append(archived_item)
        domain_manager.update_quest_board(channel_id, board)
        return f"🗄️ **메모 보관됨:** '{archived_item}'"
    else:
        return "❌ 해당 메모를 찾을 수 없습니다."

def get_archived_memos(channel_id):
    """보관된 메모 목록을 반환합니다."""
    board = domain_manager.get_quest_board(channel_id)
    archive = board.get("archive", [])
    if not archive: return "📭 **보관함이 비어있습니다.**"
    msg = "**🗄️ [메모 보관함]**\n"
    for i, m in enumerate(archive): msg += f"{i+1}. {m}\n"
    return msg

def get_objective_context(channel_id):
    """AI 프롬프트용 문자열 생성. 보관함 내용을 포함하여 기억력을 높입니다."""
    board = domain_manager.get_quest_board(channel_id)
    if not board: return ""
    quests = board.get("active", [])
    memos = board.get("memo", [])
    archives = board.get("archive", [])[-5:] # 최근 5개 과거 기억만 참고
    q_str = "\n".join([f"- {q}" for q in quests]) if quests else "None"
    m_str = "\n".join([f"- {m}" for m in memos]) if memos else "None"
    a_str = "\n".join([f"- {a}" for a in archives]) if archives else "None"
    return (
        f"[Current Objectives & Notes]\n"
        f"**Active Quests** (High Priority):\n{q_str}\n\n"
        f"**Memo Pad** (Immediate Tasks):\n{m_str}\n\n"
        f"**Archived Records** (Past Success/Events):\n{a_str}\n"
        f"*GM Instruction: Refer to Archives to maintain consistency. Auto-archive memos when completed.*"
    )

def get_status_message(channel_id):
    """현재 퀘스트와 메모 상태 요약"""
    board = domain_manager.get_quest_board(channel_id)
    quests = board.get("active", [])
    memos = board.get("memo", [])
    msg = "**📋 [퀘스트 보드]**\n"
    if not quests: msg += "(진행 중인 퀘스트 없음)\n"
    else:
        for i, q in enumerate(quests): msg += f"{i+1}. {q}\n"
    msg += "\n**📝 [메모장]**\n"
    if not memos: msg += "(메모 없음)\n"
    else:
        for i, m in enumerate(memos): msg += f"{i+1}. {m}\n"
    return msg