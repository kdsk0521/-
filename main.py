import discord
import os
import asyncio
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types

try:
    import persona
    import domain_manager
    import character_sheet
    import input_handler
    import simulation_manager
    import memory_system
    import session_manager
    import world_manager
    import quest_manager
except ImportError as e:
    print(f"CRITICAL ERROR: 필수 모듈을 찾을 수 없습니다. {e}")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("bot_runtime.log", encoding='utf-8'), logging.StreamHandler()]
)

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MODEL_ID = os.getenv('GEMINI_MODEL_VERSION', 'gemini-2.0-flash-exp')

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    print("Error: 토큰 정보를 확인하세요.")
    exit(1)

client_genai = genai.Client(api_key=GEMINI_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
client_discord = discord.Client(intents=intents)

@client_discord.event
async def on_ready():
    logging.info(f'Logged in: {client_discord.user}')
    domain_manager.initialize_folders()
    character_sheet.initialize_folders()

async def send_long_message(channel, text):
    last_msg = None
    if len(text) <= 2000: last_msg = await channel.send(text)
    else:
        chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
        for chunk in chunks: last_msg = await channel.send(chunk)
    return last_msg

@client_discord.event
async def on_message(message):
    if message.author == client_discord.user or not message.content: return

    try:
        channel_id = str(message.channel.id)
        if message.content.strip() == "!off":
            domain_manager.set_bot_disabled(channel_id, True)
            await message.channel.send("🔇 봇 비활성화.")
            return
        if message.content.strip() == "!on":
            domain_manager.set_bot_disabled(channel_id, False)
            await message.channel.send("🔊 봇 활성화.")
            return
        if domain_manager.is_bot_disabled(channel_id): return

        domain_manager.update_participant(channel_id, message.author)
        parsed = input_handler.parse_input(message.content)
        if not parsed: return

        system_trigger_msg = None 
        if parsed['type'] == 'command':
            cmd, args = parsed['command'], parsed['content']
            is_valid, err = session_manager.manager.validate_command_flow(channel_id, cmd, domain_manager)
            if not is_valid: return await message.channel.send(err)

            if cmd == 'reset': await session_manager.manager.execute_reset(message, client_discord, domain_manager, character_sheet)
            elif cmd in ['start', '시작']: await session_manager.manager.start_session(message, client_genai, MODEL_ID, domain_manager)
            elif cmd in ['ready', '준비']: await session_manager.manager.check_preparation(message, domain_manager)
            elif cmd in ['mask', '가면']: 
                domain_manager.set_user_mask(channel_id, message.author.id, args)
                await message.channel.send(f"🎭 **{args}**(으)로 설정됨.")
            elif cmd in ['desc', '설명']:
                if not args:
                    d = domain_manager.get_user_description(channel_id, message.author.id)
                    await message.channel.send(f"📝 현재 설명: {d if d else '없음'}")
                else:
                    domain_manager.set_user_description(channel_id, message.author.id, args)
                    await message.channel.send("📝 설명 업데이트됨.")
            elif cmd in ['memo', '메모']:
                if not args: await message.channel.send(quest_manager.get_status_message(channel_id))
                elif args == '기록': await message.channel.send(quest_manager.get_archived_memos(channel_id))
                elif args.startswith('보관'): await message.channel.send(quest_manager.archive_memo(channel_id, args[2:].strip()))
                else: await message.channel.send(quest_manager.add_memo(channel_id, args))
            elif cmd in ['next', '진행']: system_trigger_msg = "(Proceeding Story)"
            else: return 

        if parsed['type'] == 'dice': return await message.channel.send(parsed['content'])

        # AI Response
        if domain_manager.get_mode(channel_id) == 'manual' and parsed['type'] == 'chat' and not system_trigger_msg:
            domain_manager.add_to_buffer(channel_id, message.author.id, parsed['content'])
            return await message.add_reaction("✍️")

        async with message.channel.typing():
            domain = domain_manager.get_domain(channel_id)
            lore, rules = domain_manager.get_lore(channel_id), domain_manager.get_rules(channel_id)
            world_ctx, obj_ctx = world_manager.get_world_context(channel_id), quest_manager.get_objective_context(channel_id)
            
            final_input = system_trigger_msg if system_trigger_msg else f"[{domain_manager.get_user_mask(channel_id, message.author.id)}]: {parsed['content']}"
            history_text = "\n".join([f"{h['role']}: {h['content']}" for h in domain.get('history', [])[-5:]]) + f"\nUser: {final_input}"
            
            nvc = await memory_system.analyze_context_nvc(client_genai, MODEL_ID, history_text, lore, rules)
            
            system_evt = ""
            if nvc and nvc["SystemAction"] != "None":
                act = nvc["SystemAction"]
                if "MemoAction" in act:
                    parts = act.split('|')
                    m_type, m_content = parts[1].split(':')[1].strip().lower(), parts[2].split(':')[1].strip()
                    if m_type == "add": quest_manager.add_memo(channel_id, m_content)
                    elif m_type == "remove": quest_manager.archive_memo(channel_id, m_content)
                    system_evt = f"\n[System: Memo {m_type}d - {m_content}]"
                # Add other system actions here...

            full_prompt = f"{world_ctx}\n{obj_ctx}\n[Internal]: {nvc.get('Feeling')}\n{final_input}{system_evt}"
            session = persona.create_risu_style_session(client_genai, MODEL_ID, lore, rules)
            for h in domain.get('history', []):
                role = "user" if h['role'] == "User" else "model"
                session.history.append(types.Content(role=role, parts=[types.Part(text=h['content'])]))
            
            response = await persona.generate_response_with_retry(client_genai, session, full_prompt)
            if response:
                last_msg = await send_long_message(message.channel, response)
                if last_msg: await last_msg.add_reaction("✅")
                domain_manager.append_history(channel_id, "User", final_input)
                domain_manager.append_history(channel_id, "Char", response)

    except Exception as e:
        logging.error(f"Error: {e}")
        await message.channel.send(f"⚠️ 에러: {e}")

if __name__ == "__main__": client_discord.run(DISCORD_TOKEN)