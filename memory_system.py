import json
import asyncio
import logging
import re
from google.genai import types

# =========================================================
# [LORE COMPRESSION] 로어 압축기 (좌뇌 전처리)
# =========================================================
async def compress_lore_core(client, model_id, raw_lore_text):
    """
    [THEORIA LOGIC CORE]
    Reduces token usage by 80% while retaining critical game data.
    """
    system_instruction = (
        "[Role: Lore Archivist]\n"
        "Compress text into a dense TRPG Sourcebook summary.\n"
        "**Discard:** Fluff, poetry, repetition.\n"
        "**Keep:** Rules, Factions, NPC Motives, Conflicts, Secrets.\n"
        "**Format:** Plain text sections (World Laws, Factions, NPCs, Tension, Secrets)."
    )
    
    user_prompt = f"### RAW TEXT\n{raw_lore_text}\n\n### INSTRUCTION\nCompress into dense sourcebook summary."

    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(temperature=0.2)
            )
            return response.text.strip()
        except Exception:
            await asyncio.sleep(1)
            
    return "Error: Lore Compression Failed."

# =========================================================
# [LOGIC ANALYZER] 상황 판단 및 인과율 계산 (좌뇌 코어)
# =========================================================
async def analyze_context_nvc(client, model_id, history_text, lore, rules, active_quests_text):
    """
    [THEORIA LEFT HEMISPHERE: LOGIC & CAUSALITY]
    Analyzes 'Macroscopic State' for Alien Research Data Collection.
    """
    system_instruction = (
        "[Identity: Logic Core]\n"
        "Analyze input to extract objective facts. **Apply MECE principle.**\n\n"
        
        "### OBSERVATION PROTOCOLS\n"
        "1. **Physics Check (Hard Limits):** Verify physical/logical possibility. If impossible (e.g., flight w/o wings), state: **'Action Failed: Physics Violation'**.\n"
        "2. **Macroscopic Only:** Analyze observable actions/states (injuries, arousal, fatigue) ONLY. No mind-reading.\n"
        "3. **Knowledge Firewall:** Distinguish Player Knowledge vs Character Knowledge.\n"
        "4. **Auto-XP Calculation:**\n"
        "   - **Minor (10-30):** Skill check, smart move.\n"
        "   - **Major (50-100):** Defeated enemy, solved puzzle, survived crisis.\n"
        "   - **Critical (200+):** Boss kill, Quest complete.\n"
        "   - *Condition:* Award ONLY for Success/Victory.\n\n"

        "### OUTPUT FORMAT (JSON ONLY)\n"
        "{\n"
        "  \"CurrentLocation\": \"Location Name\",\n"
        "  \"LocationRisk\": \"None/Low/Medium/High/Extreme\",\n"
        "  \"TimeContext\": \"Time of day/flow\",\n"
        "  \"Observation\": \"Objective summary (Who, What, Reaction, Physical Outcome).\",\n"
        "  \"Need\": \"Logical next step (e.g., 'Calc damage', 'Scene transition')\",\n"
        "  \"SystemAction\": { \"tool\": \"Quest/Memo/NPC/XP\", \"type\": \"...\", \"content\": \"...\" } OR null\n"
        "}\n"
    )

    user_prompt = (
        f"### [RULES]\n{rules}\n### [QUESTS]\n{active_quests_text}\n### [HISTORY]\n{history_text}\n"
        "Analyze the current state."
    )

    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
            )
            text = re.sub(r"```(json)?", "", response.text).strip()
            return json.loads(text)
        except Exception:
            await asyncio.sleep(1)
            
    return {
        "CurrentLocation": "Unknown", "LocationRisk": "Low", 
        "Observation": "Analysis Failed", "Need": "Proceed Caution"
    }

# =========================================================
# [LORE ANALYZER] 로어 분석 도구들
# =========================================================
async def analyze_genre_from_lore(client, model_id, lore_text):
    """[Logic Core] Analyze Genre & Tone"""
    system_instruction = "Extract: 1. Key Genres (list), 2. Custom Tone (string)."
    user_prompt = f"Lore Data:\n{lore_text}"
    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            text = re.sub(r"```(json)?", "", response.text).strip()
            return json.loads(text)
        except: await asyncio.sleep(1)
    return {"genres": ["noir"], "custom_tone": "Dark and gritty"}

async def analyze_npcs_from_lore(client, model_id, lore_text):
    """[Logic Core] Extract NPC Data"""
    system_instruction = "Extract major NPCs. JSON: {'npcs': [{'name': '...', 'description': '...'}]}"
    user_prompt = f"Lore Data:\n{lore_text}"
    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            text = re.sub(r"```(json)?", "", response.text).strip()
            return json.loads(text).get("npcs", [])
        except: await asyncio.sleep(1)
    return []

async def analyze_location_rules_from_lore(client, model_id, lore_text):
    """[Logic Core] Extract Environmental Laws"""
    system_instruction = "Extract Location Rules. JSON: {\"rules\": {\"LocName\": {\"risk\": \"High\", \"condition\": \"Night\", \"effect\": \"str\"}}}"
    user_prompt = f"Lore Data:\n{lore_text}"
    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            text = re.sub(r"```(json)?", "", response.text).strip()
            return json.loads(text).get("rules", {})
        except: await asyncio.sleep(1)
    return {}