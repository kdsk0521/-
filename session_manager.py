import discord
import asyncio
import os

class SessionManager:
    """
    TRPG 세션의 준비 및 시작 흐름을 관리합니다.
    """

    async def execute_reset(self, message, client, domain_manager, character_sheet):
        channel_id = str(message.channel.id)
        confirm_msg = await message.channel.send("🗑️ **데이터 초기화 확인:** 모든 정보가 삭제됩니다. 5초 내에 ⭕를 누르세요.")
        await confirm_msg.add_reaction("⭕")

        def check(reaction, user):
            return user == message.author and str(reaction.emoji) == "⭕" and reaction.message.id == confirm_msg.id

        try:
            await client.wait_for('reaction_add', timeout=5.0, check=check)
            domain_manager.reset_domain(channel_id)
            character_sheet.reset_npc_status(channel_id)
            try:
                await message.channel.purge(limit=100)
            except:
                pass
            await message.channel.send("✅ **초기화 완료.**")
        except asyncio.TimeoutError:
            await message.channel.send("❌ 취소되었습니다.")

    async def check_preparation(self, message, domain_manager):
        channel_id = str(message.channel.id)
        lore = domain_manager.get_lore(channel_id)
        rules = domain_manager.get_rules(channel_id)
        participants = domain_manager.get_active_participants_summary(channel_id)

        msg_log = "🔍 **세션 준비 점검...**\n"
        ready_flag = True

        if not lore:
            msg_log += "❌ **로어:** 비어있음\n"
            ready_flag = False
        else:
            msg_log += "✅ **로어:** 준비됨\n"

        if not rules:
            msg_log += "❌ **룰북:** 비어있음\n"
            ready_flag = False
        else:
            msg_log += "✅ **룰북:** 준비됨\n"

        if ready_flag:
            domain_manager.set_prepared(channel_id, True)
            msg_log += "\n✨ **활성화 완료:** `!가면` 후 `!시작` 하세요."
        else:
            domain_manager.set_prepared(channel_id, False)
            msg_log += "\n❗ **실패:** 설정 확인 후 다시 `!준비` 하세요."

        await message.channel.send(msg_log)

    async def start_session(self, message, client_genai, model_id, domain_manager):
        """
        [수정] 세션 시작 성공 여부를 반환하여 main.py에서 오프닝을 생성할 수 있게 합니다.
        """
        channel_id = str(message.channel.id)
        if not domain_manager.is_prepared(channel_id):
            await message.channel.send("❌ **시작 불가:** 먼저 `!준비`를 완료하세요.")
            return False

        domain_manager.toggle_session_lock(channel_id)
        await message.channel.send("🔒 **세션 잠금:** 게임이 시작되었습니다.\n📜 **오프닝 서사 생성 중...**")
        return True

# 싱글톤 인스턴스
manager = SessionManager()