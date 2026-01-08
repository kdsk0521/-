"""
Lorekeeper TRPG Bot - Main Module
Version: 3.1 (Refactored)
"""

import discord
import os
import asyncio
import logging
import io
import re
from typing import Optional, Tuple, List
from dotenv import load_dotenv
from google import genai
from google.genai import types

# =========================================================
# 상수 정의
# =========================================================
MAX_DISCORD_MESSAGE_LENGTH = 2000
SUPPORTED_TEXT_EXTENSIONS = ['.txt', '.md', '.json', '.log', '.py', '.yaml', '.yml']
VERSION = "3.1"

# =========================================================
# 모듈 임포트
# =========================================================
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

# =========================================================
# 로깅 설정
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# =========================================================
# 환경 변수 로드
# =========================================================
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MODEL_ID = os.getenv('GEMINI_MODEL_VERSION', 'gemini-3-flash-preview')  # Gemini 3 Flash 사용

# =========================================================
# API 클라이언트 초기화
# =========================================================
if not GEMINI_API_KEY:
    logging.warning("GEMINI_API_KEY가 설정되지 않았습니다!")

client_genai = None
try:
    if GEMINI_API_KEY:
        client_genai = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    logging.error(f"Gemini 클라이언트 초기화 실패: {e}")

# =========================================================
# Discord 클라이언트 초기화
# =========================================================
intents = discord.Intents.default()
intents.message_content = True
client_discord = discord.Client(intents=intents)


# =========================================================
# 유틸리티 함수
# =========================================================
async def send_long_message(channel, text: str) -> None:
    """2000자가 넘는 메시지를 나누어 전송하는 함수"""
    if not text:
        return
    
    if len(text) <= MAX_DISCORD_MESSAGE_LENGTH:
        await channel.send(text)
        return
    
    # 메시지 분할 전송
    for i in range(0, len(text), MAX_DISCORD_MESSAGE_LENGTH):
        chunk = text[i:i + MAX_DISCORD_MESSAGE_LENGTH]
        await channel.send(chunk)


async def read_attachment_text(attachment) -> Tuple[Optional[str], Optional[str]]:
    """
    첨부파일에서 텍스트를 읽어옵니다.
    
    Returns:
        Tuple[Optional[str], Optional[str]]: (텍스트 내용, 에러 메시지)
    """
    filename_lower = attachment.filename.lower()
    
    # 지원되는 확장자인지 확인
    if not any(filename_lower.endswith(ext) for ext in SUPPORTED_TEXT_EXTENSIONS):
        return None, f"⚠️ **지원하지 않는 파일입니다.**\n지원 확장자: {', '.join(SUPPORTED_TEXT_EXTENSIONS)}"
    
    try:
        data = await attachment.read()
        text = data.decode('utf-8')
        return text, None
    except UnicodeDecodeError:
        return None, f"⚠️ 파일 `{attachment.filename}` 읽기 실패: UTF-8 인코딩이 아닙니다."
    except Exception as e:
        return None, f"⚠️ 파일 `{attachment.filename}` 읽기 실패: {e}"


async def safe_delete_message(message) -> None:
    """메시지를 안전하게 삭제합니다."""
    try:
        await message.delete()
    except discord.NotFound:
        pass
    except discord.Forbidden:
        logging.warning("메시지 삭제 권한이 없습니다.")
    except Exception as e:
        logging.warning(f"메시지 삭제 실패: {e}")


# =========================================================
# 명령어 핸들러
# =========================================================
async def handle_cheat_command(message, channel_id: str, args: List[str], client_genai, MODEL_ID: str) -> Optional[str]:
    """
    치트/GM 명령어를 처리합니다.
    AI 분석 도구 및 게임 마스터 기능을 통합합니다.
    
    Args:
        message: Discord 메시지 객체
        channel_id: 채널 ID
        args: 명령어 인자 리스트
        client_genai: Gemini API 클라이언트
        MODEL_ID: 모델 ID
    
    Returns:
        응답 메시지 또는 None
    """
    if not args or args[0] == '':
        return (
            "🛠️ **치트/GM 명령어:**\n"
            "━━━━━━━━━━━━━━━\n"
            "**데이터 조작:**\n"
            "`!치트 xp [숫자]` - 경험치 부여\n"
            "`!치트 퀘스트 [추가/완료] [내용]`\n"
            "`!치트 메모 [추가/삭제] [내용]`\n"
            "`!치트 npc [이름] [설명]` - NPC 추가\n"
            "`!치트 버프 [이름]` / `!치트 디버프 [이름]`\n"
            "`!치트 둠 [+/-숫자]` - 위기 수치 조절\n\n"
            "**AI 분석:**\n"
            "`!치트 분석 [질문]` - OOC 브레인스토밍\n"
            "`!치트 일관성` - 서사 일관성 검사\n"
            "`!치트 세계` - 세계관 규칙 추출"
        )
    
    category = args[0].lower()
    
    # === 경험치 치트 ===
    if category in ['xp', '경험치']:
        if len(args) < 2:
            return "❌ 사용법: `!치트 xp [숫자]`"
        
        try:
            amount = int(args[1])
        except ValueError:
            return "❌ 경험치는 숫자로 입력해주세요."
        
        uid = str(message.author.id)
        p_data = domain_manager.get_participant_data(channel_id, uid)
        
        if not p_data:
            return "❌ 캐릭터가 없습니다. `!가면`으로 먼저 등록하세요."
        
        growth_system = domain_manager.get_growth_system(channel_id)
        new_data, msg, _ = simulation_manager.gain_experience(p_data, amount, growth_system)
        domain_manager.save_participant_data(channel_id, uid, new_data)
        return f"🛠️ **[GM]** {msg}"
    
    # === 퀘스트 치트 ===
    elif category in ['quest', '퀘스트']:
        if len(args) < 2:
            return "❌ 사용법: `!치트 퀘스트 [추가/완료] [내용]`"
        
        action = args[1]
        content = " ".join(args[2:]) if len(args) > 2 else ""
        
        if action in ['추가', 'add', '+']:
            if not content:
                return "❌ 퀘스트 내용을 입력하세요."
            result = quest_manager.add_quest(channel_id, content)
            return f"🛠️ {result}"
        elif action in ['완료', 'complete', 'done']:
            if not content:
                return "❌ 완료할 퀘스트 키워드를 입력하세요."
            result = quest_manager.complete_quest(channel_id, content)
            return f"🛠️ {result}"
        else:
            return "❌ `추가` 또는 `완료`만 가능합니다."
    
    # === 메모 치트 ===
    elif category in ['memo', '메모']:
        if len(args) < 2:
            return "❌ 사용법: `!치트 메모 [추가/삭제] [내용]`"
        
        action = args[1]
        content = " ".join(args[2:]) if len(args) > 2 else ""
        
        if action in ['추가', 'add', '+']:
            if not content:
                return "❌ 메모 내용을 입력하세요."
            result = quest_manager.add_memo(channel_id, content)
            return f"🛠️ {result}"
        elif action in ['삭제', 'remove', 'delete', '-']:
            if not content:
                return "❌ 삭제할 메모 키워드를 입력하세요."
            result = quest_manager.remove_memo(channel_id, content)
            return f"🛠️ {result}"
        else:
            return "❌ `추가` 또는 `삭제`만 가능합니다."
    
    # === NPC 치트 ===
    elif category == 'npc':
        if len(args) < 2:
            return "❌ 사용법: `!치트 npc [이름] [설명]`"
        
        npc_name = args[1]
        npc_desc = " ".join(args[2:]) if len(args) > 2 else "GM이 추가한 NPC"
        
        character_sheet.npc_memory.add_npc(channel_id, npc_name, npc_desc)
        return f"🛠️ **NPC 추가:** {npc_name} - {npc_desc}"
    
    # === 버프/디버프 치트 ===
    elif category in ['버프', 'buff']:
        if len(args) < 2:
            buffs = [name for name, data in simulation_manager.STATUS_EFFECTS.items() 
                     if data.get("type") == "buff"]
            return f"🛠️ **사용 가능한 버프:**\n{', '.join(buffs)}\n\n사용법: `!치트 버프 [이름]` 또는 `!치트 버프 제거 [이름]`"
        
        action = args[1]
        uid = str(message.author.id)
        p_data = domain_manager.get_participant_data(channel_id, uid)
        
        if not p_data:
            return "❌ 캐릭터가 없습니다."
        
        # 제거 명령
        if action in ['제거', 'remove', '-']:
            if len(args) < 3:
                return "❌ 제거할 버프 이름을 입력하세요."
            effect_name = args[2]
            p_data, msg = simulation_manager.update_status_effect(p_data, "remove", effect_name)
        else:
            effect_name = action
            p_data, msg = simulation_manager.update_status_effect(p_data, "add", effect_name)
        
        domain_manager.save_participant_data(channel_id, uid, p_data)
        return f"🛠️ {msg}"
    
    elif category in ['디버프', 'debuff']:
        if len(args) < 2:
            debuffs = [name for name, data in simulation_manager.STATUS_EFFECTS.items() 
                       if data.get("type") != "buff"]
            return f"🛠️ **사용 가능한 디버프:**\n{', '.join(debuffs[:20])}...\n\n사용법: `!치트 디버프 [이름]` 또는 `!치트 디버프 제거 [이름]`"
        
        action = args[1]
        uid = str(message.author.id)
        p_data = domain_manager.get_participant_data(channel_id, uid)
        
        if not p_data:
            return "❌ 캐릭터가 없습니다."
        
        # 제거 명령
        if action in ['제거', 'remove', '-']:
            if len(args) < 3:
                return "❌ 제거할 디버프 이름을 입력하세요."
            effect_name = args[2]
            p_data, msg = simulation_manager.update_status_effect(p_data, "remove", effect_name)
        else:
            effect_name = action
            p_data, msg = simulation_manager.update_status_effect(p_data, "add", effect_name)
        
        domain_manager.save_participant_data(channel_id, uid, p_data)
        return f"🛠️ {msg}"
    
    # === Doom 치트 ===
    elif category in ['doom', '둠', '위기']:
        if len(args) < 2:
            status = world_manager.get_doom_status(channel_id)
            return f"📊 **위기 수치:** {status['value']}% ({status['description']})"
        
        try:
            amount = int(args[1])
            result = world_manager.change_doom(channel_id, amount)
            return f"🛠️ {result}"
        except ValueError:
            return "❌ 숫자를 입력하세요. 예: `!치트 둠 +10`"
    
    # === AI 분석: OOC 브레인스토밍 ===
    elif category in ['분석', 'analyze', 'ooc']:
        question = " ".join(args[1:]) if len(args) > 1 else ""
        if not question:
            return "❌ 사용법: `!치트 분석 [질문]`\n예: `!치트 분석 이 NPC의 진짜 목적은?`"
        
        if not client_genai:
            return "⚠️ AI가 연결되지 않았습니다."
        
        # 로딩 메시지는 None 반환 후 별도 처리 필요
        return f"__ANALYZE__{question}"
    
    # === AI 분석: 일관성 검사 ===
    elif category in ['일관성', 'consistency']:
        if not client_genai:
            return "⚠️ AI가 연결되지 않았습니다."
        return "__CONSISTENCY__"
    
    # === AI 분석: 세계 규칙 ===
    elif category in ['세계', 'world', 'worldrules']:
        if not client_genai:
            return "⚠️ AI가 연결되지 않았습니다."
        return "__WORLDRULES__"
    
    return "⚠️ 알 수 없는 치트 명령입니다. `!치트`로 목록을 확인하세요."


async def handle_lore_command(message, channel_id: str, arg: str) -> None:
    """로어 명령어를 처리합니다."""
    file_text = ""
    is_file_processed = False
    
    # 첨부파일 처리
    if message.attachments:
        for att in message.attachments:
            text, error = await read_attachment_text(att)
            if error:
                await message.channel.send(error)
                return
            if text:
                file_text = text
                is_file_processed = True
                break
        
        # 첨부파일이 있지만 처리되지 않았고, 텍스트 인자도 없는 경우
        if not is_file_processed and not arg:
            await message.channel.send(
                f"⚠️ **지원하지 않는 파일입니다.**\n"
                f"지원 확장자: {', '.join(SUPPORTED_TEXT_EXTENSIONS)}"
            )
            return
    
    full = (arg + "\n" + file_text).strip()
    
    # 로어 조회
    if not full:
        summary = domain_manager.get_lore_summary(channel_id)
        display_text = summary if summary else domain_manager.get_lore(channel_id)
        title = "[핵심 요약본]" if summary else "[원본 로어]"
        
        if display_text == domain_manager.DEFAULT_LORE:
            await message.channel.send(
                "📜 저장된 로어가 없습니다. `!로어 [내용]` 또는 텍스트 파일을 업로드하세요."
            )
            return
        
        await send_long_message(message.channel, f"📜 **{title}**\n{display_text}")
        return
    
    # 로어 초기화
    if full == "초기화":
        domain_manager.reset_lore(channel_id)
        domain_manager.set_active_genres(channel_id, ["noir"])
        domain_manager.set_custom_tone(channel_id, None)
        await message.channel.send("📜 초기화됨")
        return
    
    # 로어 저장
    current_lore = domain_manager.get_lore(channel_id)
    
    # 파일 업로드 시 또는 기존 로어가 기본값이면 리셋
    if file_text or current_lore == domain_manager.DEFAULT_LORE:
        domain_manager.reset_lore(channel_id)
    
    domain_manager.append_lore(channel_id, full)
    
    # 로어 크기 확인
    raw_lore = domain_manager.get_lore(channel_id)
    lore_length = len(raw_lore)
    
    # 대용량 로어 여부 판단 (15000자 이상)
    is_massive = lore_length > 15000
    
    if is_massive:
        estimated_chunks = (lore_length // 15000) + 1
        status_msg = await message.channel.send(
            f"📜 **로어 저장됨** ({lore_length:,}자 감지)\n"
            f"📚 대용량 로어 처리 모드 활성화 (약 {estimated_chunks}개 청크)\n"
            f"⏳ 처리 시간: 약 {estimated_chunks * 10}~{estimated_chunks * 20}초 예상..."
        )
    else:
        status_msg = await message.channel.send("📜 **로어 저장됨.** (AI 분석 준비 중...)")
    
    # AI 분석
    if client_genai:
        try:
            # 대용량 로어 처리
            if is_massive:
                async def progress_callback(stage, current, total):
                    stage_names = {
                        "splitting": "📂 청크 분할",
                        "compressing": "🗜️ 청크 압축",
                        "merging": "🔗 중간 병합",
                        "finalizing": "✨ 최종 통합"
                    }
                    stage_name = stage_names.get(stage, stage)
                    await status_msg.edit(
                        content=f"📚 **[대용량 로어 처리 중]**\n"
                                f"{stage_name}: {current}/{total}"
                    )
                
                summary, metadata = await memory_system.process_massive_lore(
                    client_genai, MODEL_ID, raw_lore, progress_callback
                )
                
                domain_manager.save_lore_summary(channel_id, summary)
                
                await status_msg.edit(
                    content=f"📚 **[대용량 처리 완료]**\n"
                            f"• 원본: {metadata['original_length']:,}자\n"
                            f"• 압축: {metadata['final_length']:,}자\n"
                            f"• 압축률: {metadata['compression_ratio']}:1\n"
                            f"• 처리 시간: {metadata['processing_time']}초\n"
                            f"• 방식: {metadata['method']}\n\n"
                            f"⏳ 장르/NPC 분석 중..."
                )
            else:
                await status_msg.edit(content="⏳ **[AI]** 세계관 압축 중...")
                summary = await memory_system.compress_lore_core(client_genai, MODEL_ID, raw_lore)
                domain_manager.save_lore_summary(channel_id, summary)
            
            # 장르 분석 (요약본 기반으로 수행 - 토큰 절약)
            await status_msg.edit(content="⏳ **[AI]** 장르 및 NPC 데이터 추출 중...")
            
            # 대용량일 경우 요약본으로 분석, 아니면 원본으로
            analysis_text = summary if is_massive else raw_lore
            
            res = await memory_system.analyze_genre_from_lore(client_genai, MODEL_ID, analysis_text)
            domain_manager.set_active_genres(channel_id, res.get("genres", ["noir"]))
            domain_manager.set_custom_tone(channel_id, res.get("custom_tone"))
            
            npcs = await memory_system.analyze_npcs_from_lore(client_genai, MODEL_ID, analysis_text)
            for n in npcs:
                character_sheet.npc_memory.add_npc(channel_id, n.get("name"), n.get("description"))
            
            rules = await memory_system.analyze_location_rules_from_lore(client_genai, MODEL_ID, analysis_text)
            if rules:
                domain_manager.set_location_rules(channel_id, rules)
            
            # 최종 메시지
            final_msg = f"✅ **[분석 완료]**\n**장르:** {res.get('genres')}"
            if is_massive:
                final_msg += f"\n**압축률:** {metadata['compression_ratio']}:1 ({metadata['original_length']:,}자 → {metadata['final_length']:,}자)"
            
            await status_msg.edit(content=final_msg)
            
        except Exception as e:
            logging.error(f"Lore Analysis Error: {e}")
            await status_msg.edit(content=f"⚠️ **분석 중 오류 발생:** {e}")
    else:
        await status_msg.edit(content="📜 저장 완료 (⚠️ API 키 없음: AI 분석 건너뜀)")


async def handle_rule_command(message, channel_id: str, arg: str) -> None:
    """룰 명령어를 처리합니다."""
    file_text = ""
    
    # 첨부파일 처리
    if message.attachments:
        for att in message.attachments:
            if att.filename.lower().endswith('.txt'):
                try:
                    data = await att.read()
                    file_text = data.decode('utf-8')
                    break
                except Exception as e:
                    await message.channel.send(f"⚠️ 파일 읽기 실패: {e}")
                    return
    
    # 룰 저장 또는 초기화
    if file_text or arg:
        if arg == "초기화":
            domain_manager.reset_rules(channel_id)
            await message.channel.send("📘 초기화됨")
            return
        
        content = file_text if file_text else arg
        domain_manager.append_rules(channel_id, content)
        await message.channel.send("📘 룰 업데이트")
        return
    
    # 룰 조회
    await send_long_message(
        message.channel,
        f"📘 **현재 룰:**\n{domain_manager.get_rules(channel_id)}"
    )


async def handle_chronicle_command(message, channel_id: str, arg: str) -> None:
    """연대기 명령어를 처리합니다."""
    # 연대기 생성 (AI 요약)
    if arg == "생성":
        msg = await message.channel.send("⏳ **[AI]** 현재까지의 이야기를 연대기로 요약 중입니다...")
        
        if not client_genai:
            await msg.edit(content="⚠️ AI 미연동 상태입니다.")
            return
        
        result_text = await quest_manager.generate_chronicle_from_history(client_genai, MODEL_ID, channel_id)
        await safe_delete_message(msg)
        await send_long_message(message.channel, result_text)
        return
    
    # 연대기 추출 (파일 다운로드)
    elif arg == "추출":
        txt_data, msg = quest_manager.export_lore_book_file(channel_id)
        
        if not txt_data:
            await message.channel.send(msg)
            return
        
        with io.BytesIO(txt_data.encode('utf-8')) as f:
            await message.channel.send(msg, file=discord.File(f, filename="chronicles.txt"))
        return
    
    # 연대기 목록 조회 (기본)
    await send_long_message(message.channel, quest_manager.get_lore_book(channel_id))


async def handle_npc_info_command(message, channel_id: str, npc_name: str) -> None:
    """NPC 정보 조회 명령어를 처리합니다."""
    if not npc_name:
        # 전체 NPC 목록
        summary = character_sheet.get_npc_summary(channel_id)
        if not summary:
            await message.channel.send("⚠️ 등록된 NPC가 없습니다.")
            return
        await send_long_message(message.channel, f"👥 **NPC 목록**\n{summary}")
        return
    
    # 특정 NPC 조회
    npcs = domain_manager.get_npcs(channel_id)
    npc_data = npcs.get(npc_name)
    
    if npc_data:
        status = npc_data.get('status', 'Active')
        desc = npc_data.get('desc', '설명 없음')
        await message.channel.send(f"👤 **{npc_name}** ({status})\n{desc}")
    else:
        await message.channel.send(f"⚠️ '{npc_name}'라는 NPC를 찾을 수 없습니다.")


async def handle_info_command(message, channel_id: str) -> None:
    """
    통합 캐릭터 정보 명령어를 처리합니다.
    이름, 설명, 상태이상, 패시브, 적응도, 인벤토리, NPC 관계 상위 3~4개를 표시합니다.
    """
    uid = str(message.author.id)
    p = domain_manager.get_participant_data(channel_id, uid)
    
    if not p:
        await message.channel.send("❌ 정보 없음. `!가면`으로 먼저 등록하세요.")
        return
    
    mask = p.get('mask', 'Unknown')
    desc = p.get('description', '')
    ai_mem = p.get('ai_memory', {})
    
    # === 기본 정보 ===
    header = f"👤 **[{mask}]**"
    if desc:
        header += f"\n_{desc}_"
    
    # AI가 업데이트한 외모/성격 정보
    appearance = ai_mem.get('appearance', '')
    personality = ai_mem.get('personality', '')
    if appearance or personality:
        header += "\n"
        if appearance:
            header += f"\n👁️ {appearance}"
        if personality:
            header += f"\n💭 {personality}"
    
    # === 상태이상 (버프/디버프 통합) ===
    status_effects = p.get('status_effects', [])
    status_section = ""
    if status_effects:
        buffs = []
        debuffs = []
        for effect_name in status_effects:
            effect_info = simulation_manager.STATUS_EFFECTS.get(effect_name, {"type": "unknown"})
            if effect_info.get("type") == "buff":
                buffs.append(effect_name)
            else:
                debuffs.append(effect_name)
        
        if buffs:
            status_section += f"✨ 버프: {', '.join(buffs)}\n"
        if debuffs:
            status_section += f"💀 디버프: {', '.join(debuffs)}\n"
    else:
        status_section = "✅ 상태: 정상\n"
    
    # === 패시브 (간략 표시) ===
    passives = p.get('passives', [])
    passive_section = ""
    if passives:
        passive_names = [ps.get('name', '???') for ps in passives[:4]]
        passive_section = f"🏆 패시브: {', '.join(passive_names)}"
        if len(passives) > 4:
            passive_section += f" 외 {len(passives) - 4}개"
        passive_section += "\n"
    
    # === 비일상 적응도 (간략 표시) ===
    exposure = p.get('abnormal_exposure', {})
    adapt_section = ""
    if exposure:
        adapt_items = []
        for ab_type, data in sorted(exposure.items(), key=lambda x: x[1].get('normality', 0), reverse=True)[:3]:
            normality = data.get('normality', 0)
            stage = simulation_manager.get_normality_stage(normality)
            adapt_items.append(f"{ab_type}({stage['name']})")
        adapt_section = f"🌓 적응: {', '.join(adapt_items)}\n"
    
    # === 인벤토리 ===
    inventory = p.get('inventory', {})
    inv_section = ""
    if inventory:
        inv_items = [f"{k} x{v}" for k, v in list(inventory.items())[:5]]
        inv_section = f"🎒 소지품: {', '.join(inv_items)}"
        if len(inventory) > 5:
            inv_section += f" 외 {len(inventory) - 5}개"
        inv_section += "\n"
    
    # === NPC 관계 상위 3~4개 ===
    relations = p.get('relations', {})
    ai_relationships = ai_mem.get('relationships', {})
    
    # 코드 관계 + AI 관계 병합 (AI 관계 우선)
    merged_relations = {}
    for npc, val in relations.items():
        merged_relations[npc] = {"score": val, "desc": ""}
    for npc, desc in ai_relationships.items():
        if npc in merged_relations:
            merged_relations[npc]["desc"] = desc
        else:
            merged_relations[npc] = {"score": 0, "desc": desc}
    
    rel_section = ""
    if merged_relations:
        # 점수 기준 정렬, 상위 4개
        sorted_rels = sorted(merged_relations.items(), key=lambda x: abs(x[1].get("score", 0)), reverse=True)[:4]
        rel_items = []
        for npc, data in sorted_rels:
            score = data.get("score", 0)
            desc = data.get("desc", "")
            if score != 0:
                emoji = "💖" if score > 0 else "💔"
                rel_items.append(f"{npc} {emoji}{score:+}")
            elif desc:
                rel_items.append(f"{npc}: {desc[:15]}...")
            else:
                rel_items.append(npc)
        rel_section = f"🤝 관계: {' | '.join(rel_items)}\n"
    
    # === 최종 조합 ===
    final_msg = f"{header}\n\n"
    final_msg += f"**━━━ 상태 ━━━**\n"
    final_msg += status_section
    
    if passive_section:
        final_msg += passive_section
    if adapt_section:
        final_msg += adapt_section
    if inv_section:
        final_msg += inv_section
    if rel_section:
        final_msg += rel_section
    
    final_msg += f"\n💡 _수정: `(OOC: 요청 내용)` 입력_"
    
    await send_long_message(message.channel, final_msg)


async def process_ai_system_action(message, channel_id: str, sys_action: dict) -> Optional[str]:
    """AI가 제안한 시스템 액션을 처리합니다."""
    if not sys_action or not isinstance(sys_action, dict):
        return None
    
    tool = sys_action.get("tool")
    atype = sys_action.get("type")
    content = sys_action.get("content")
    
    if not all([tool, atype, content]):
        return None
    
    auto_msg = None
    
    if tool == "Memo":
        if atype == "Add":
            auto_msg = quest_manager.add_memo(channel_id, content)
        elif atype == "Remove":
            auto_msg = quest_manager.remove_memo(channel_id, content)
        elif atype == "Archive":
            auto_msg = quest_manager.resolve_memo_auto(channel_id, content)
    
    elif tool == "Quest":
        if atype == "Add":
            auto_msg = quest_manager.add_quest(channel_id, content)
        elif atype == "Complete":
            auto_msg = quest_manager.complete_quest(channel_id, content)
    
    elif tool == "NPC" and atype == "Add":
        if ":" in content:
            name, desc = content.split(":", 1)
            character_sheet.npc_memory.add_npc(channel_id, name.strip(), desc.strip())
            auto_msg = f"👥 NPC: {name.strip()}"
        else:
            character_sheet.npc_memory.add_npc(channel_id, content, "Auto")
            auto_msg = f"👥 NPC: {content}"
    
    elif tool == "XP" and atype == "Award":
        try:
            match = re.match(r"(\d+)\s*(?:\((.*)\))?", str(content))
            if match:
                xp_amount = int(match.group(1))
                reason = match.group(2) or "Activity"
                uid = str(message.author.id)
                p_data = domain_manager.get_participant_data(channel_id, uid)
                
                if p_data:
                    growth_system = domain_manager.get_growth_system(channel_id)
                    new_data, xp_msg, _ = simulation_manager.gain_experience(
                        p_data, xp_amount, growth_system
                    )
                    domain_manager.save_participant_data(channel_id, uid, new_data)
                    auto_msg = f"⚔️ **성과 확인:** {reason}\n{xp_msg}"
        except Exception as e:
            logging.error(f"Auto XP Error: {e}")
    
    return auto_msg


# =========================================================
# Discord 이벤트 핸들러
# =========================================================
@client_discord.event
async def on_ready():
    """봇 준비 완료 시 실행"""
    domain_manager.initialize_folders()
    print(f"--- Lorekeeper V{VERSION} Online ({client_discord.user}) ---")
    print(f"Model: {MODEL_ID}")


@client_discord.event
async def on_message(message):
    """메시지 수신 시 실행"""
    # 봇 자신의 메시지 또는 빈 메시지 무시
    if message.author == client_discord.user or not message.content:
        return
    
    try:
        channel_id = str(message.channel.id)
        
        # 봇 On/Off 명령어
        if message.content == "!off":
            domain_manager.set_bot_disabled(channel_id, True)
            await message.channel.send("🔇 Off")
            return
        
        if message.content == "!on":
            domain_manager.set_bot_disabled(channel_id, False)
            await message.channel.send("🔊 On")
            return
        
        # 봇이 비활성화된 경우 무시
        if domain_manager.is_bot_disabled(channel_id):
            return
        
        # 입력 파싱
        parsed = input_handler.parse_input(message.content)
        if not parsed:
            return
        
        cmd = parsed.get('command')
        
        # =========================================================
        # 보안: 참가자 및 잠금 확인
        # =========================================================
        is_participant = domain_manager.get_participant_data(
            channel_id, str(message.author.id)
        ) is not None
        domain_data = domain_manager.get_domain(channel_id)
        is_locked = domain_data['settings'].get('session_locked', False)
        
        # 비참가자가 사용 가능한 명령어
        entry_commands = [
            'ready', 'reset', 'start', 'mask', 'lore', 'rule', 'system'
        ]
        
        if not is_participant:
            if is_locked:
                return  # 잠긴 세션에서 비참가자 무시
            if parsed['type'] == 'command':
                if cmd not in entry_commands:
                    return
            else:
                return
        
        # 준비되지 않은 세션에서 허용되는 명령어
        if not domain_manager.is_prepared(channel_id):
            allowed_before_ready = ['ready', 'lore', 'rule', 'reset', 'system']
            if parsed['type'] != 'command' or cmd not in allowed_before_ready:
                await message.channel.send("⚠️ `!준비`를 먼저 해주세요.")
                return
        
        system_trigger = None
        
        # =========================================================
        # 명령어 처리
        # =========================================================
        if parsed['type'] == 'command':
            
            # --- 세션 관리 ---
            if cmd == 'reset':
                await session_manager.manager.execute_reset(
                    message, client_discord, domain_manager, character_sheet
                )
                return
            
            if cmd == 'ready':
                await session_manager.manager.check_preparation(message, domain_manager)
                return
            
            if cmd == 'start':
                domain_manager.update_participant(channel_id, message.author)
                if await session_manager.manager.start_session(
                    message, client_genai, MODEL_ID, domain_manager
                ):
                    system_trigger = "[System: Generate a visceral opening scene for the campaign.]"
                else:
                    return
            
            if cmd == 'unlock':
                domain_manager.set_session_lock(channel_id, False)
                await message.channel.send("🔓 **잠금 해제**")
                return
            
            if cmd == 'lock':
                domain_manager.set_session_lock(channel_id, True)
                await message.channel.send("🔒 **세션 잠금**")
                return
            
            # --- 시스템 설정 ---
            if cmd == 'system':
                args = parsed['content'].strip().split()
                if not args:
                    await message.channel.send("⚙️ 사용법: `!시스템 성장 [기본/커스텀]`\n• 기본: 패시브/칭호 기반 (숫자 없음)\n• 커스텀: !룰에 정의한 규칙 사용")
                    return
                
                if args[0] in ['성장', 'growth']:
                    if len(args) < 2:
                        current = domain_manager.get_growth_system(channel_id)
                        await message.channel.send(f"📊 **현재 성장:** `{current}`")
                        return
                    
                    growth_type = args[1].lower()
                    if growth_type in ['기본', 'standard', '표준']:
                        growth_type = 'standard'
                    elif growth_type in ['커스텀', 'custom', '사용자']:
                        growth_type = 'custom'
                    else:
                        await message.channel.send("⚠️ `기본` 또는 `커스텀`만 가능합니다.")
                        return
                    
                    domain_manager.set_growth_system(channel_id, growth_type)
                    await message.channel.send(f"✅ 성장 시스템: `{growth_type}`")
                return
            
            # --- 치트/GM 모드 ---
            if cmd == 'cheat':
                args = parsed['content'].strip().split()
                result = await handle_cheat_command(message, channel_id, args, client_genai, MODEL_ID)
                
                if result:
                    # AI 분석 특수 처리 (비동기 작업 필요)
                    if result.startswith("__ANALYZE__"):
                        question = result[11:]
                        loading = await message.channel.send("🔍 **[OOC 분석 중...]**")
                        
                        domain = domain_manager.get_domain(channel_id)
                        lore = domain_manager.get_lore(channel_id)
                        history = domain.get('history', [])[-20:]
                        hist_text = "\n".join([f"{h['role']}: {h['content']}" for h in history])
                        
                        analysis = await memory_system.analyze_brainstorming(
                            client_genai, MODEL_ID, hist_text, lore, question
                        )
                        await safe_delete_message(loading)
                        
                        if analysis.get("analysis_type") == "error":
                            await message.channel.send(f"⚠️ 분석 실패: {analysis.get('recommendation')}")
                        else:
                            response_text = f"🔍 **[OOC 분석]**\n\n**상황:** {analysis.get('current_state_summary', 'N/A')}\n"
                            if analysis.get('potential_paths'):
                                response_text += "\n**가능한 경로:**\n"
                                for i, path in enumerate(analysis.get('potential_paths', [])[:3], 1):
                                    response_text += f"{i}. {path.get('path', 'N/A')}\n"
                            if analysis.get('recommendation'):
                                response_text += f"\n**추천:** {analysis.get('recommendation')}"
                            await send_long_message(message.channel, response_text)
                    
                    elif result == "__CONSISTENCY__":
                        loading = await message.channel.send("🔍 **[일관성 검사 중...]**")
                        
                        domain = domain_manager.get_domain(channel_id)
                        lore = domain_manager.get_lore(channel_id)
                        history = domain.get('history', [])[-30:]
                        hist_text = "\n".join([f"{h['role']}: {h['content']}" for h in history])
                        
                        analysis = await memory_system.check_narrative_consistency(
                            client_genai, MODEL_ID, hist_text, lore
                        )
                        await safe_delete_message(loading)
                        
                        response_text = f"📋 **[일관성 검사]**\n\n**전체:** {analysis.get('overall_consistency', 'Unknown')}\n"
                        issues = analysis.get('issues', [])
                        if issues:
                            response_text += "\n**문제점:**\n"
                            for issue in issues[:5]:
                                severity = "🔴" if issue.get('severity') == 'critical' else "🟡"
                                response_text += f"{severity} {issue.get('description')}\n"
                        else:
                            response_text += "✅ 문제 없음\n"
                        await send_long_message(message.channel, response_text)
                    
                    elif result == "__WORLDRULES__":
                        loading = await message.channel.send("🌍 **[세계 규칙 추출 중...]**")
                        
                        lore = domain_manager.get_lore(channel_id)
                        analysis = await memory_system.extract_world_constraints(
                            client_genai, MODEL_ID, lore
                        )
                        await safe_delete_message(loading)
                        
                        if analysis:
                            response_text = "🌍 **[세계 규칙]**\n\n"
                            if analysis.get('setting'):
                                s = analysis['setting']
                                response_text += f"**배경:** {s.get('era', 'N/A')} / {s.get('location', 'N/A')}\n"
                            if analysis.get('theme'):
                                t = analysis['theme']
                                response_text += f"**장르:** {', '.join(t.get('genres', []))}\n"
                            await send_long_message(message.channel, response_text)
                        else:
                            await message.channel.send("⚠️ 세계 규칙 추출 실패")
                    
                    else:
                        await message.channel.send(result)
                return
            
            # --- 경험치 확인 ---
            # --- 경험치 (치트로 통합) ---
            # --- 로어 명령어 ---
            if cmd == 'lore':
                await handle_lore_command(message, channel_id, parsed['content'].strip())
                return
            
            # --- 모드 전환 ---
            if cmd == 'mode':
                arg = parsed['content'].strip()
                if '수동' in arg:
                    domain_manager.set_response_mode(channel_id, 'manual')
                    await message.channel.send("🛑 수동 모드")
                elif '자동' in arg:
                    domain_manager.set_response_mode(channel_id, 'auto')
                    await message.channel.send("⏩ 자동 모드")
                else:
                    current = domain_manager.get_response_mode(channel_id)
                    await message.channel.send(f"⚙️ 현재: {current}")
                return
            
            # --- 진행 ---
            if cmd == 'next':
                system_trigger = "[System: Resolve pending actions and advance the scene.]"
                await message.add_reaction("🎬")
            
            # --- 캐릭터 관리 ---
            if cmd == 'mask':
                target = parsed['content']
                status = domain_manager.get_participant_status(channel_id, message.author.id)
                
                if status == "left":
                    domain_manager.update_participant(channel_id, message.author, True)
                    await message.channel.send("🆕 환생 완료")
                
                domain_manager.update_participant(channel_id, message.author)
                domain_manager.set_user_mask(channel_id, message.author.id, target)
                await message.channel.send(f"🎭 가면: {target}")
                return
            
            if cmd == 'desc':
                domain_manager.update_participant(channel_id, message.author)
                domain_manager.set_user_description(
                    channel_id, message.author.id, parsed['content']
                )
                await message.channel.send("📝 저장됨")
                return
            
            if cmd == 'info':
                await handle_info_command(message, channel_id)
                return
            
            if cmd == 'status':
                await send_long_message(
                    message.channel,
                    quest_manager.get_status_message(channel_id)
                )
                return
            
            # --- 참가자 상태 ---
            if cmd == 'afk':
                domain_manager.set_participant_status(channel_id, message.author.id, "afk")
                await message.channel.send("💤")
                return
            
            if cmd == 'leave':
                domain_manager.set_participant_status(
                    channel_id, message.author.id, "left", "이탈"
                )
                await message.channel.send("🚪")
                return
            
            if cmd == 'back':
                domain_manager.update_participant(channel_id, message.author)
                await message.channel.send("✨")
                return
            
            # --- 룰 명령어 ---
            if cmd == 'rule':
                await handle_rule_command(message, channel_id, parsed['content'].strip())
                return
            
            # --- 연대기 ---
            if cmd == 'lores':
                await handle_chronicle_command(message, channel_id, parsed['content'].strip())
                return
            
            # --- 내보내기 ---
            if cmd == 'export':
                mode = parsed.get('content', '').strip()
                lore = domain_manager.get_lore(channel_id)
                ch, msg = quest_manager.export_chronicles_incremental(channel_id, mode)
                
                if not ch:
                    await message.channel.send(msg)
                    return
                
                content = f"=== LORE ===\n{lore}\n\n{ch}"
                with io.BytesIO(content.encode('utf-8')) as f:
                    await message.channel.send(msg, file=discord.File(f, filename="export.txt"))
                return
            
            # --- NPC 정보 ---
            if cmd == 'npc':
                await handle_npc_info_command(
                    message, channel_id, parsed.get('content', '').strip()
                )
                return
            
            # --- Thinking Level 설정 ---
            if cmd == 'thinking':
                arg = parsed.get('content', '').strip().lower()
                
                valid_modes = ['auto', 'minimal', 'low', 'medium', 'high']
                
                if not arg:
                    # 현재 상태 표시
                    current_mode = domain_manager.get_thinking_mode(channel_id)
                    mode_desc = {
                        'auto': '🤖 자동 (상황에 따라 조절)',
                        'minimal': '⚡ 최소 (빠름, 저비용)',
                        'low': '💭 낮음 (일반 대화)',
                        'medium': '🧠 보통 (전투, NPC 대화)',
                        'high': '🎓 높음 (추리, 복잡한 상황)'
                    }
                    
                    # 길이 정보 표시
                    length_info = ""
                    for level in ['minimal', 'low', 'medium', 'high']:
                        lengths = persona.get_length_requirements(level)
                        length_info += f"• `{level}`: {lengths['min']}~{lengths['max']}자\n"
                    
                    await message.channel.send(
                        f"🧠 **Thinking Level 설정**\n\n"
                        f"현재: **{mode_desc.get(current_mode, current_mode)}**\n\n"
                        f"**레벨별 응답 길이:**\n{length_info}\n"
                        f"사용법: `!사고 [auto/minimal/low/medium/high]`\n"
                        f"• `auto`: 상황 복잡도에 따라 자동 조절 (권장)\n"
                        f"• `minimal`: 단순 행동에 적합, 비용 최소\n"
                        f"• `low`: 일반 대화에 적합\n"
                        f"• `medium`: 전투, NPC 상호작용\n"
                        f"• `high`: 추리, 협상, 중요 결정"
                    )
                    return
                
                if arg in valid_modes:
                    domain_manager.set_thinking_mode(channel_id, arg)
                    mode_emoji = {'auto': '🤖', 'minimal': '⚡', 'low': '💭', 'medium': '🧠', 'high': '🎓'}
                    
                    # 변경된 모드의 길이 정보 표시
                    if arg != 'auto':
                        lengths = persona.get_length_requirements(arg)
                        length_msg = f" (응답 길이: {lengths['min']}~{lengths['max']}자)"
                    else:
                        length_msg = " (상황에 따라 300~1200자)"
                    
                    await message.channel.send(
                        f"{mode_emoji.get(arg, '🧠')} **Thinking Level 변경:** `{arg}`{length_msg}"
                    )
                else:
                    await message.channel.send(
                        f"⚠️ 올바른 모드를 입력하세요: {', '.join(valid_modes)}"
                    )
                return
            
        # =========================================================
        # 주사위 처리
        # =========================================================
        if parsed['type'] == 'dice':
            await message.channel.send(parsed['content'])
            domain_manager.append_history(channel_id, "System", f"Dice: {parsed['content']}")
            return
        
        # =========================================================
        # OOC (자연어 메모리 수정) 처리
        # =========================================================
        if parsed['type'] == 'ooc':
            ooc_content = parsed['content']
            uid = str(message.author.id)
            
            # 현재 AI 메모리 가져오기
            ai_mem = domain_manager.get_ai_memory(channel_id, uid)
            if not ai_mem:
                await message.channel.send("❌ 먼저 `!가면`으로 캐릭터를 등록하세요.")
                return
            
            if not client_genai:
                await message.channel.send("⚠️ AI가 비활성화되어 OOC 수정이 불가능합니다.")
                return
            
            wait_msg = await message.channel.send("⏳ **[OOC]** 요청 처리 중...")
            
            # AI에게 수정 요청 파싱
            edit_result = await memory_system.process_ooc_memory_edit(
                client_genai, MODEL_ID, ooc_content, ai_mem
            )
            
            if edit_result and edit_result.get("edits"):
                # 수정 적용
                updated_mem = memory_system.apply_memory_edits(ai_mem, edit_result["edits"])
                domain_manager.update_ai_memory(channel_id, uid, updated_mem)
                
                confirm_msg = edit_result.get("confirmation_message", "수정 완료!")
                interpretation = edit_result.get("interpretation", "")
                
                await safe_delete_message(wait_msg)
                await message.channel.send(
                    f"✅ **[OOC 수정 완료]**\n"
                    f"_{interpretation}_\n\n"
                    f"{confirm_msg}"
                )
            else:
                await safe_delete_message(wait_msg)
                await message.channel.send(
                    "❌ **[OOC]** 요청을 이해하지 못했습니다.\n"
                    "예시: `(OOC: 리엘이랑 친해진 걸로 해줘)`, `((마법 적응됐어))`"
                )
            return
        
        # =========================================================
        # AI 응답 생성
        # =========================================================
        if parsed['type'] == 'command' and not system_trigger:
            return
        
        domain = domain_manager.get_domain(channel_id)
        if not domain['settings'].get('session_locked', False) and not system_trigger:
            return
        
        async with message.channel.typing():
            if not domain_manager.update_participant(channel_id, message.author):
                return
            
            user_mask = domain_manager.get_user_mask(channel_id, message.author.id)
            action_text = system_trigger if system_trigger else f"[{user_mask}]: {parsed['content']}"
            
            # 수동 모드에서는 기록만 하고 AI 응답 생성 안 함
            response_mode = domain_manager.get_response_mode(channel_id)
            if response_mode == 'manual' and not system_trigger:
                domain_manager.append_history(channel_id, "User", action_text)
                await message.add_reaction("✏️")
                return
            
            # 컨텍스트 수집
            summary = domain_manager.get_lore_summary(channel_id)
            lore_txt = summary if summary else domain_manager.get_lore(channel_id)
            rule_txt = domain_manager.get_rules(channel_id)
            world_ctx = world_manager.get_world_context(channel_id)
            obj_ctx = quest_manager.get_objective_context(channel_id)
            active_genres = domain_manager.get_active_genres(channel_id)
            custom_tone = domain_manager.get_custom_tone(channel_id)
            
            history = domain.get('history', [])[-10:]
            hist_text = "\n".join([f"{h['role']}: {h['content']}" for h in history])
            hist_text += f"\nUser: {action_text}"
            
            active_quests = domain_manager.get_quest_board(channel_id).get("active", [])
            quest_txt = " | ".join(active_quests) if active_quests else "None"
            
            # 플레이어 컨텍스트 수집 (패시브 중복 방지용)
            uid = str(message.author.id)
            p_data = domain_manager.get_participant_data(channel_id, uid)
            player_context = ""
            if p_data:
                player_context = simulation_manager.get_passives_for_context(p_data)
            
            # AI 분석 (좌뇌)
            nvc_res = {}
            if client_genai:
                nvc_res = await memory_system.analyze_context_nvc(
                    client_genai, MODEL_ID, hist_text, lore_txt, rule_txt, quest_txt,
                    player_context=player_context
                )
                
                if nvc_res.get("CurrentLocation"):
                    domain_manager.set_current_location(channel_id, nvc_res["CurrentLocation"])
                if nvc_res.get("LocationRisk"):
                    domain_manager.set_current_risk(channel_id, nvc_res["LocationRisk"])
            
            # 시스템 액션 처리
            sys_action = nvc_res.get("SystemAction", {})
            auto_msg = await process_ai_system_action(message, channel_id, sys_action)
            
            # === 비일상 적응 시스템 처리 ===
            # uid와 p_data는 이미 위에서 가져옴
            abnormal_msgs = []
            abnormal_ctx = ""
            passive_ctx = ""
            
            if p_data:
                current_day = domain_manager.get_world_state(channel_id).get("day", 1)
                
                # 비일상 요소 노출 처리
                abnormal_elements = nvc_res.get("AbnormalElements", [])
                for ab_element in abnormal_elements:
                    p_data, stage_msg, stage_info = simulation_manager.expose_to_abnormal(
                        p_data, ab_element, current_day
                    )
                    if stage_msg:
                        abnormal_msgs.append(stage_msg)
                
                # 경험 카운터 처리 (AI가 패시브 제안)
                exp_counters = nvc_res.get("ExperienceCounters", {})
                for counter_name, count in exp_counters.items():
                    p_data, _ = simulation_manager.increment_experience_counter(
                        p_data, counter_name, count, current_day
                    )
                
                # === AI 자율 패시브 제안 처리 ===
                passive_suggestion = nvc_res.get("PassiveSuggestion")
                if passive_suggestion and isinstance(passive_suggestion, dict):
                    p_data, ai_passive_msg = simulation_manager.grant_ai_passive(
                        p_data, passive_suggestion, current_day
                    )
                    if ai_passive_msg:
                        abnormal_msgs.append(ai_passive_msg)
                
                # 업데이트된 데이터 저장
                domain_manager.save_participant_data(channel_id, uid, p_data)
                
                # 비일상 적응도 컨텍스트 생성 (AI에게 전달)
                if abnormal_elements:
                    abnormal_ctx = simulation_manager.get_abnormal_context(p_data, abnormal_elements)
                
                # 패시브 컨텍스트 생성 (AI에게 전달)
                passive_ctx = simulation_manager.get_passive_context(p_data)
            
            # Temporal Orientation 추출
            temporal = nvc_res.get("TemporalOrientation", {})
            temporal_ctx = ""
            if temporal:
                temporal_ctx = (
                    f"### [TEMPORAL ORIENTATION]\n"
                    f"Continuity: {temporal.get('continuity_from_previous', 'N/A')}\n"
                    f"Active Threads: {', '.join(temporal.get('active_threads', []))}\n"
                    f"Off-screen NPCs: {', '.join(temporal.get('offscreen_npcs', []))}\n"
                    f"Focus: {temporal.get('suggested_focus', 'N/A')}\n\n"
                )
            
            # NPC 태도 컨텍스트 생성
            npc_attitudes = nvc_res.get("NPCAttitudes", {})
            npc_attitude_ctx = ""
            if npc_attitudes:
                npc_attitude_ctx = "### [NPC ATTITUDES]\n"
                for npc_name, attitude_data in npc_attitudes.items():
                    if isinstance(attitude_data, dict):
                        att = attitude_data.get("attitude", "neutral")
                        reason = attitude_data.get("reason", "")
                        # 태도별 말투 힌트 추가
                        speech_hints = {
                            "hostile": "위협적, 조롱, 정보 숨김",
                            "unfriendly": "퉁명스럽고 짧음, 비협조",
                            "neutral": "정중하고 사무적",
                            "friendly": "따뜻하고 친근, 정보 제공",
                            "devoted": "존경/애정, 비밀 공유 가능"
                        }
                        hint = speech_hints.get(att, "")
                        npc_attitude_ctx += f"- **{npc_name}**: {att} ({reason}) → 말투: {hint}\n"
                npc_attitude_ctx += "\n"
            
            # NPC간 대화 컨텍스트 생성
            npc_interaction = nvc_res.get("NPCInteraction")
            npc_interaction_ctx = ""
            if npc_interaction and isinstance(npc_interaction, dict):
                participants = npc_interaction.get("participants", [])
                interaction_type = npc_interaction.get("type", "")
                topic = npc_interaction.get("topic", "")
                mood = npc_interaction.get("mood", "")
                if participants and len(participants) >= 2:
                    npc_interaction_ctx = (
                        f"### [NPC INTERACTION OPPORTUNITY]\n"
                        f"NPCs present: {', '.join(participants)}\n"
                        f"Type: {interaction_type} | Mood: {mood}\n"
                        f"Suggested topic: {topic}\n"
                        f"**Instruction:** Include ambient dialogue between these NPCs "
                        f"that players can overhear. This adds atmosphere and may reveal information.\n\n"
                    )
            
            # AI 응답 생성 (우뇌) - 강화된 프롬프트
            full_prompt = (
                f"### [WORLD STATE]\n{world_ctx}\n{obj_ctx}\n\n"
                f"{temporal_ctx}"
                f"{abnormal_ctx}"
                f"{passive_ctx}"
                f"{npc_attitude_ctx}"
                f"{npc_interaction_ctx}"
                f"### [LEFT HEMISPHERE ANALYSIS]\n"
                f"Location: {nvc_res.get('CurrentLocation', 'Unknown')} "
                f"(Risk: {nvc_res.get('LocationRisk', 'Low')})\n"
                f"Physical State: {nvc_res.get('PhysicalState', 'N/A')}\n"
                f"Observation: {nvc_res.get('Observation', 'N/A')}\n"
                f"Need: {nvc_res.get('Need', 'N/A')}\n\n"
                f"### [MATERIAL]\n"
                f"<material>\n{action_text}\n</material>\n\n"
                f"### [DIRECTIVE]\n"
                f"Process <material> as the player's attempt. "
                f"Players are identified by [Name]: prefix (e.g., [잭]:, [리사]:). "
                f"Generate NPC reactions and world response ONLY. "
                f"**Apply NPC attitudes to their speech and behavior.** "
                f"**If NPC Interaction is suggested, include their ambient dialogue.** "
                f"Do NOT generate ANY player's dialogue, thoughts, or decisions. "
                f"Track each player separately. 3rd person narration. Korean output."
            )
            
            response = "⚠️ AI Error"
            if client_genai:
                # Thinking Mode 확인 (auto 또는 수동 고정)
                thinking_mode = domain_manager.get_thinking_mode(channel_id)
                
                if thinking_mode == "auto":
                    # 자동: 상황에 따라 Thinking Level 결정
                    thinking_context = {
                        "risk_level": nvc_res.get("LocationRisk", "Low"),
                        "doom": domain_manager.get_world_state(channel_id).get("doom", 0)
                    }
                    thinking_level, thinking_reason = persona.analyze_input_complexity(
                        action_text, thinking_context
                    )
                else:
                    # 수동: 고정된 Thinking Level 사용
                    thinking_level = thinking_mode
                    thinking_reason = "수동 설정"
                
                loading = await message.channel.send(
                    f"⏳ **[Lorekeeper]** 집필 중... (🧠 {thinking_level})"
                )
                
                # Thinking Level을 적용하여 세션 생성
                session = persona.create_risu_style_session(
                    client_genai, MODEL_ID, lore_txt, rule_txt, 
                    active_genres, custom_tone,
                    thinking_level=thinking_level  # 동적 Thinking Level
                )
                
                # 히스토리 추가
                for h in domain.get('history', []):
                    role = "user" if h['role'] == "User" else "model"
                    session.history.append(
                        types.Content(role=role, parts=[types.Part(text=h['content'])])
                    )
                
                # 응답 생성 (동적 길이 적용)
                response = await persona.generate_response_with_retry(
                    client_genai, session, full_prompt,
                    thinking_level=thinking_level  # 길이 요구사항 전달
                )
                
                await safe_delete_message(loading)
                
                # 디버그: Thinking Level 및 응답 길이 로깅
                if response:
                    logging.info(
                        f"[Thinking] Level: {thinking_level}, "
                        f"Reason: {thinking_reason}, "
                        f"Length: {len(response)}자"
                    )
            
            # 결과 전송
            if auto_msg:
                await message.channel.send(f"🤖 {auto_msg}")
            
            # 비일상 적응/패시브 메시지 출력
            if abnormal_msgs:
                for ab_msg in abnormal_msgs:
                    await message.channel.send(ab_msg)
            
            if response:
                await send_long_message(message.channel, response)
                domain_manager.append_history(channel_id, "User", action_text)
                domain_manager.append_history(channel_id, "Char", response)
    
    except Exception as e:
        logging.error(f"Main Error: {e}", exc_info=True)
        await message.channel.send(f"⚠️ **시스템 오류 발생:** {e}")


# =========================================================
# 메인 실행
# =========================================================
if __name__ == "__main__":
    if DISCORD_TOKEN:
        client_discord.run(DISCORD_TOKEN)
    else:
        print("ERROR: DISCORD_TOKEN이 설정되지 않았습니다.")
