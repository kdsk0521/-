from google.genai import types
import logging

# =========================================================
# [프롬프트] NVC + 시스템 액션 (AI 자동 메모 관리 지침 강화)
# =========================================================
NVC_ANALYSIS_PROMPT = """
[GM Internal Brain: NVC & Action Detection]

You are analyzing the narrative to manage game state and NPC logic.

1. **Observation**: What is the current narrative situation?
2. **Feeling**: Your emotional tone as a GM.
3. **Need**: What narrative goal are you pursuing?
4. **SystemAction**: Detect and trigger game mechanics.
   - **None**: No mechanic.
   - **MemoAction**: AUTOMATICALLY manage the Memo Pad.
     * **Add**: If a new important clue, NPC name, or task is discovered.
     * **Remove**: If a task is COMPLETED, a clue is solved, or a note is no longer relevant.
     * Format: `MemoAction | Type: <Add/Remove> | Content: <Text>`
   - **QuestAction**: Manage major story goals.
     * Format: `QuestAction | Type: <Add/Complete> | Content: <Text>`
   - **StatusAction**: Add/Remove status effects like 'Injured', 'Exhausted'.
     * Format: `StatusAction | Type: <Add/Remove> | Effect: <Name>`

[Output Format]
Observation: ...
Feeling: ...
Need: ...
SystemAction: ...
"""

async def analyze_context_nvc(client, model_id, history_text, lore_text, rule_text=""):
    full_prompt = (
        f"{NVC_ANALYSIS_PROMPT}\n\n"
        f"[World Lore]\n{lore_text[:500]}...\n\n"
        f"[Game Rules]\n{rule_text[:1000]}...\n\n"
        f"[Interaction]\n{history_text}"
    )
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=full_prompt,
            config=types.GenerateContentConfig(temperature=0.1)
        )
        return parse_nvc_result(response.text)
    except Exception as e:
        logging.error(f"NVC Error: {e}")
        return {"SystemAction": "None"}

def parse_nvc_result(text):
    data = {"Observation": "", "Feeling": "", "Need": "", "SystemAction": "None"}
    lines = text.split('\n')
    for line in lines:
        if line.startswith("Observation:"): data["Observation"] = line.replace("Observation:", "").strip()
        elif line.startswith("Feeling:"): data["Feeling"] = line.replace("Feeling:", "").strip()
        elif line.startswith("Need:"): data["Need"] = line.replace("Need:", "").strip()
        elif line.startswith("SystemAction:"): data["SystemAction"] = line.replace("SystemAction:", "").strip()
    return data