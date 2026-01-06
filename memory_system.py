import json
import asyncio
import logging
from google.genai import types

async def analyze_context_nvc(client, model_id, history_text, lore, rules, active_quests_text):
    """
    [THEORIA LEFT HEMISPHERE: LOGIC & CAUSALITY]
    Analyzes the 'Macroscopic State' using MECE principles.
    """
    system_instruction = (
        "[System Identity: THEORIA Left Hemisphere (Logic Core)]\n"
        "You are the Axiom Enforcer. Analyze all available information—directions, context, and accumulated details.\n"
        "**Apply the MECE principle (Mutually Exclusive, Collectively Exhaustive)** to ensure your analysis is comprehensive and non-overlapping.\n\n"
        
        "### AXIOM OF OBSERVATION\n"
        "1. **Macroscopic Only:** Existence is opaque. Analyze only what is explicitly said, done, or physically manifested. Never presume 'Microscopic States' (inner thoughts) as facts.\n"
        "2. **Causality:** The world implies strict asynchronous causality. Ensure that every 'Quest Complete' or 'Memo' update follows a logical cause-and-effect chain.\n"
        "3. **Annihilate Category Errors:** Do not use metaphors or meta-language in analysis. Report the raw, unvarnished truth.\n"
        "4. **Avatar Distinction:** Clearly distinguish between the 'User' (Player) and '{{user}}' (Character). Analyze {{user}}'s state, not the User's feelings. Do not invent goals or backstories for {{user}} not present in the History.\n\n"

        "### OUTPUT FORMAT (JSON ONLY)\n"
        "{\n"
        "  \"Observation\": \"Objective summary of visible reality (Apply MECE: distinct facts only)\",\n"
        "  \"CurrentLocation\": \"Inferred physical location\",\n"
        "  \"LocationRisk\": \"None | Low | Medium | High | Extreme\",\n"
        "  \"Need\": \"Logical narrative tension requiring resolution\",\n"
        "  \"SystemAction\": {\n"
        "      \"tool\": \"None\" | \"Memo\" | \"Quest\" | \"NPC\",\n"
        "      \"type\": \"Add\" | \"Remove\" | \"Complete\" | \"Archive\",\n"
        "      \"content\": \"Precise, dry summary of the item\"\n"
        "  }\n"
        "}"
    )

    user_prompt = (
        f"### WORLD AXIOMS (LORE)\n{lore}\n\n"
        f"### ACTIVE CAUSAL CHAINS (QUESTS)\n{active_quests_text}\n\n"
        f"### PHYSICS & RULES\n{rules}\n\n"
        f"### OBSERVED MACROSCOPIC STATE (HISTORY)\n{history_text}\n\n"
        "Execute Logic Core. Analyze Causality via MECE."
    )

    for i in range(5):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                )
            )
            result_text = response.text
            if "```" in result_text:
                import re
                result_text = re.sub(r"```(json)?", "", result_text).strip()
                
            return json.loads(result_text)
        except Exception as e:
            delay = 2 ** i
            if i == 4:
                logging.error(f"Left Brain Failure: {e}")
                return {"Observation": "Error", "SystemAction": {"tool": "None"}}
            await asyncio.sleep(delay)
    return None

async def analyze_genre_from_lore(client, model_id, lore_text):
    """[Logic Core] Analyze World Parameters"""
    system_instruction = (
        "Analyze the provided Lore to extract World Parameters (Genre & Tone).\n"
        "JSON Only: {genres: [str], custom_tone: str}"
    )
    user_prompt = f"Lore Data:\n{lore_text}"
    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(system_instruction=system_instruction, response_mime_type="application/json")
            )
            text = response.text.replace("```json", "").replace("```", "")
            res = json.loads(text)
            return {"genres": res.get("genres", ["noir"]), "custom_tone": res.get("custom_tone")}
        except: await asyncio.sleep(1)
    return {"genres": ["noir"], "custom_tone": None}

async def analyze_npcs_from_lore(client, model_id, lore_text):
    """[Logic Core] Identify Entities"""
    system_instruction = "Extract Entity Profiles (NPCs). JSON: {\"npcs\": [{\"name\": \"str\", \"description\": \"str\"}]}"
    user_prompt = f"Lore Data:\n{lore_text}"
    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(system_instruction=system_instruction, response_mime_type="application/json")
            )
            text = response.text.replace("```json", "").replace("```", "")
            return json.loads(text).get("npcs", [])
        except: await asyncio.sleep(1)
    return []

async def analyze_location_rules_from_lore(client, model_id, lore_text):
    """[Logic Core] Extract Environmental Laws"""
    system_instruction = "Extract Environmental Laws (Location Rules). JSON: {\"rules\": {\"LocName\": {\"risk\": \"High\", \"condition\": \"Night\", \"effect\": \"str\"}}}"
    user_prompt = f"Lore Data:\n{lore_text}"
    for i in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(system_instruction=system_instruction, response_mime_type="application/json")
            )
            text = response.text.replace("```json", "").replace("```", "")
            return json.loads(text).get("rules", {})
        except: await asyncio.sleep(1)
    return {}