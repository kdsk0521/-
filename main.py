import discord
import os
import asyncio
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 필수 모듈 임포트
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

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MODEL_ID = os.getenv('GEMINI_MODEL_VERSION', 'gemini-2.0-flash-exp')

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    print("Error: 토큰 정보를 .env 파일에서 확인하세요.")
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
    if len(text) <= 2000:
        last_msg = await channel.send(text)
    else:
        chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
        for chunk in chunks:
            last_msg = await channel.send(chunk)
    return last_msg

@client_discord.event
async def on_message(message):
    if message.author == client_discord.user or not message.content:
        return

    try:
        channel_id = str(message.channel.id)
        
        # 1. 봇 전원 관리
        if message.content.strip() == "!off":
            domain_manager.set_bot_disabled(channel_id, True)
            return await message.channel.send("🔇 **봇 비활성화.**")
        if message.content.strip() == "!on":
            domain_manager.set_bot_disabled(channel_id, False)
            return await message.channel.send("🔊 **봇 활성화.**")
        if domain_manager.is_bot_disabled(channel_id):
            return

        # 2. 입력 분석 (마크다운 무시 로직 포함)
        parsed = input_handler.parse_input(message.content)
        if not parsed:
            return

        # 3. 명령어 게이트키퍼
        cmd_name = parsed.get('command') if parsed['type'] == 'command' else None
        is_ready = domain_manager.is_prepared(channel_id)
        
        # 준비 전에도 허용되는 명령어 리스트
        allowed_pre_ready = ['ready', '준비', 'reset', '리셋', '초기화', 'lore', '로어', 'rule', '룰']
        
        if not is_ready:
            if parsed['type'] == 'command':
                if cmd_name not in allowed_pre_ready:
                    return await message.channel.send("⚠️ 세션이 준비되지 않았습니다. `!로어`와 `!룰` 설정 후 `!준비`를 입력하세요.")
            else:
                return # 준비 전 일반 채팅 무시

        system_trigger_msg = None # AI 응답을 강제 유도하기 위한 메시지

        # 4. 명령어 상세 처리
        if parsed['type'] == 'command':
            # 리셋/초기화
            if cmd_name in ['reset', '리셋', '초기화']:
                return await session_manager.manager.execute_reset(message, client_discord, domain_manager, character_sheet)
            
            # 준비
            elif cmd_name in ['ready', '준비']:
                return await session_manager.manager.check_preparation(message, domain_manager)
            
            # 시작
            elif cmd_name in ['start', '시작']:
                success = await session_manager.manager.start_session(message, client_genai, MODEL_ID, domain_manager)
                if success:
                    system_trigger_msg = "[System: Generate a visceral opening scene for the start of the adventure.]"
                else:
                    return
            
            # [신규] 잠금 해제 (중간 참가 허용)
            elif cmd_name in ['unlock', '잠금해제']:
                domain_manager.set_session_lock(channel_id, False)
                return await message.channel.send("🔓 **세션 잠금 해제:** 이제 새로운 플레이어가 `!가면`으로 참가할 수 있습니다.")

            # [신규] 중간 이탈
            elif cmd_name in ['leave', '이탈', '퇴장']:
                mask = domain_manager.leave_participant(channel_id, message.author.id)
                if mask:
                    return await message.channel.send(f"🚪 **[{mask}]** 캐릭터가 대열에서 이탈하여 휴식에 들어갑니다. (다시 채팅하면 복귀)")
                return await message.channel.send("⚠️ 등록된 캐릭터 정보가 없습니다.")

            # [신규] 건너뛰기/진행 (할 말 없을 때)
            elif cmd_name in ['next', '진행', '건너뛰기']:
                system_trigger_msg = "[System: The players are silent or waiting. Advance the narrative to the next meaningful moment or reaction from the world.]"

            # 가면/설명/정보 확인
            elif cmd_name in ['mask', '가면']:
                if not parsed['content']:
                    mask = domain_manager.get_user_mask(channel_id, message.author.id)
                    return await message.channel.send(f"🎭 **현재 가면:** {mask}")
                domain_manager.set_user_mask(channel_id, message.author.id, parsed['content'])
                return await message.channel.send(f"🎭 **가면 설정 완료:** {parsed['content']}")
            
            elif cmd_name in ['desc', '설명']:
                mask = domain_manager.get_user_mask(channel_id, message.author.id)
                if not parsed['content']:
                    desc = domain_manager.get_user_description(channel_id, message.author.id)
                    return await message.channel.send(f"📝 **[{mask}]의 설정:**\n{desc if desc else '내용 없음'}")
                domain_manager.set_user_description(channel_id, message.author.id, parsed['content'])
                return await message.channel.send(f"📝 **[{mask}]** 설명 업데이트됨.")
            
            elif cmd_name in ['info', '정보', '내정보']:
                mask = domain_manager.get_user_mask(channel_id, message.author.id)
                desc = domain_manager.get_user_description(channel_id, message.author.id)
                return await message.channel.send(f"👤 **캐릭터 프로필**\n- 이름: {mask}\n- 설정: {desc if desc else '내용 없음'}")

            # 로어/룰
            elif cmd_name in ['lore', '로어']:
                if not parsed['content']:
                    return await message.channel.send(f"📜 **현재 로어:**\n{domain_manager.get_lore(channel_id)}")
                domain_manager.append_lore(channel_id, parsed['content'])
                return await message.channel.send("📜 로어 업데이트 완료.")
            
            elif cmd_name in ['rule', '룰']:
                if not parsed['content']:
                    return await message.channel.send(f"📘 **현재 룰:**\n{domain_manager.get_rules(channel_id)}")
                domain_manager.append_rules(channel_id, parsed['content'])
                return await message.channel.send("📘 룰 업데이트 완료.")
            
            # 메모
            elif cmd_name in ['memo', '메모']:
                if not parsed['content']: return await message.channel.send(quest_manager.get_status_message(channel_id))
                if parsed['content'] == '기록': return await message.channel.send(quest_manager.get_archived_memos(channel_id))
                return await message.channel.send(quest_manager.add_memo(channel_id, parsed['content']))
            
            else:
                # 위 리스트에 없는 명령어는 무시
                if not system_trigger_msg:
                    return

        # 5. 주사위 처리
        if parsed['type'] == 'dice':
            return await message.channel.send(parsed['content'])

        # 6. 세션 잠금 체크 (RPG 진행 중인지 확인)
        domain = domain_manager.get_domain(channel_id)
        is_locked = domain['settings'].get('session_locked', False)
        
        # 잠기지 않았는데 일반 채팅이 들어오거나, 시스템 트리거가 없다면 무시
        if not is_locked and not system_trigger_msg:
            if parsed['type'] == 'chat':
                return

        # 7. AI 응답 생성
        async with message.channel.typing():
            # 참가자 정보 자동 업데이트 (활동 중인 유저로)
            domain_manager.update_participant(channel_id, message.author)
            
            lore, rules = domain_manager.get_lore(channel_id), domain_manager.get_rules(channel_id)
            world_ctx, obj_ctx = world_manager.get_world_context(channel_id), quest_manager.get_objective_context(channel_id)
            user_mask = domain_manager.get_user_mask(channel_id, message.author.id)
            
            # 최종 입력값 결정
            current_action = system_trigger_msg if system_trigger_msg else f"[{user_mask}]: {parsed['content']}"
            
            # NVC 분석 및 히스토리 구성
            history_list = domain.get('history', [])[-10:]
            history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history_list]) + f"\nUser: {current_action}"
            nvc = await memory_system.analyze_context_nvc(client_genai, MODEL_ID, history_text, lore, rules)
            
            # 최종 프롬프트 조립
            full_prompt = (
                f"### CURRENT CONTEXT\n{world_ctx}\n{obj_ctx}\n\n"
                f"### ACTION/INPUT\n{current_action}\n\n"
                f"### INSTRUCTION\nGM으로서 서사를 이어가세요. 한국어로 응답하십시오."
            )

            # 페르소나 세션 생성 및 히스토리 복원
            session = persona.create_risu_style_session(client_genai, MODEL_ID, lore, rules)
            for h in domain.get('history', []):
                role = "user" if h['role'] == "User" else "model"
                session.history.append(types.Content(role=role, parts=[types.Part(text=h['content'])]))
            
            # 응답 생성
            response = await persona.generate_response_with_retry(client_genai, session, full_prompt)
            if response:
                last_msg = await send_long_message(message.channel, response)
                if last_msg:
                    await last_msg.add_reaction("✅")
                # 역사 저장
                domain_manager.append_history(channel_id, "User", current_action)
                domain_manager.append_history(channel_id, "Char", response)

    except Exception as e:
        logging.error(f"Error in on_message: {e}")

if __name__ == "__main__":
    client_discord.run(DISCORD_TOKEN)