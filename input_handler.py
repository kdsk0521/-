import re
import random

def strip_discord_markdown(text):
    """디스코드 마크다운 제거"""
    if not text: return ""
    patterns = [r'\*\*\*', r'\*\*', r'___', r'__', r'~~', r'\|\|', r'`']
    clean_text = text
    for p in patterns:
        clean_text = re.sub(p, '', clean_text)
    return clean_text.strip()

def analyze_style(text, clean_text):
    """대화/행동 스타일 분석"""
    if clean_text.startswith('"') or clean_text.startswith('“') or clean_text.startswith("'"):
        return "Dialogue"
    if text.strip().startswith('*') and text.strip().endswith('*'):
        return "Action"
    return "Description"

def roll_dice(dice_str):
    """주사위 계산기"""
    match = re.match(r"(\d+)d(\d+)([+-]\d+)?", dice_str.lower().replace(" ", ""))
    if not match: return None
    count, sides = int(match.group(1)), int(match.group(2))
    mod = int(match.group(3)) if match.group(3) else 0
    if count > 100: return None
    rolls = [random.randint(1, sides) for _ in range(count)]
    return sum(rolls) + mod, rolls, mod

def parse_input(content):
    """명령어 및 텍스트 파싱"""
    raw_content = content.strip()
    clean_content = strip_discord_markdown(raw_content)
    if not clean_content: return None

    # 1. 명령어 인식
    if clean_content.startswith('!'):
        parts = clean_content[1:].split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # 명령어 한글 별칭 매핑 (일관된 처리를 위해 영어로 통일)
        if command in ['리셋', '초기화']: command = 'reset'
        if command in ['준비']: command = 'ready'
        if command in ['시작']: command = 'start'
        if command in ['가면']: command = 'mask'
        if command in ['설명']: command = 'desc'
        if command in ['로어']: command = 'lore'
        if command in ['룰']: command = 'rule'
        if command in ['진행']: command = 'next'
        
        # !roll 처리
        if command in ['roll', '굴림', 'r']:
            result = roll_dice(args)
            if result:
                total, rolls, mod = result
                mod_text = f"{mod:+}" if mod != 0 else ""
                res_msg = f"🎲 **Roll**: `{args}`\nResult: {total} (Dice: {rolls} {mod_text})"
                return {'type': 'dice', 'content': res_msg}
            return {'type': 'dice', 'content': "❌ 형식 오류 (예: !r 2d6)"}
        
        return {'type': 'command', 'command': command, 'content': args}

    # 2. 일반 채팅
    style = analyze_style(raw_content, clean_content)
    return {'type': 'chat', 'style': style, 'content': clean_content}