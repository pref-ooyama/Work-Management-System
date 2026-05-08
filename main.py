import os
import discord
import gspread
import json
from datetime import datetime, timezone, timedelta
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. Flaskの設定 (Render/Replit等での24時間稼働用) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. Google Sheets / Discord Bot設定 ---
try:
    creds_dict = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    # スプレッドシート名が「勤務記録シート」であることを確認してください
    sheet = client.open("勤務記録シート").sheet1 
except Exception as e:
    print(f"初期設定エラー (スプレッドシート): {e}")

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# 幹部設定（役職IDまたは名前で判定）
KANKU_ROLE_ID = 1397055554144309358
KANKU_ROLE_NAME = "管理部【ADD】--Admin Department"

# 全部署リスト
DEPT_ROLES = {
    1469839939293286400: "刑事課", 1469839945010122772: "交通課",
    1482332775330611231: "地域指導係", 1469838348733517998: "地域課",
    1469839423054155900: "白崎署", 1469839437516111912: "山口署",
    1490599950919405609: "航空隊", 1396775870861148250: "機動隊",
    1489511872058101950: "警護課", 1396775600663822346: "特殊急襲部隊",
    1370812196954574888: "警備部", 1397855629611368499: "特殊事件捜査隊",
    1396776140542181416: "第二方面機動隊", 1369120275093782668: "第一方面機動隊",
    1369120045883457730: "捜査一課", 1369117562364891247: "刑事部",
    1369120554656993290: "交通鑑識課", 1369120943472902224: "交通機動隊",
    1369116976684994632: "交通部", 1369119769080365117: "空港警察",
    1369119537781407774: "鉄道警察", 1454725598055239945: "通信指令課",
    1393801666096005180: "遊撃特別警ら隊", 1369119275197006005: "自動車警ら隊",
    1369116816349200464: "地域部", 1469842787984736460: "教養課",
    1369123630788640849: "教務部", 1369118961521786880: "装備課",
    1369116490782998530: "警務部", 1470757182378082495: "広報課",
    1369118761352826890: "監察課", 1369118431240261674: "人事課",
    1369116075156832387: "管理部"
}

# --- 3. 共通ロジック関数 ---

def is_admin():
    async def predicate(ctx):
        has_id = any(role.id == KANKU_ROLE_ID for role in ctx.author.roles)
        has_name = any(role.name == KANKU_ROLE_NAME for role in ctx.author.roles)
        return has_id or has_name
    return commands.check(predicate)

def find_dept(input_text):
    """入力テキストから部署名を特定する"""
    candidates = [v for v in DEPT_ROLES.values() if input_text in v]
    if len(candidates) == 1:
        return candidates[0], None
    elif len(candidates) > 1:
        if input_text in candidates: return input_text, None
        return None, candidates
    return None, None

def update_work_time(name, value, dept=None, is_subtract=False):
    """スプレッドシートの時間を更新する核心部分"""
    data = sheet.get_all_values()
    target_row = None
    search_dept = dept if dept else ""

    # 重複を避け、名前と部署が一致する行を探す
    for i, row in enumerate(data):
        row_dept = row[4] if len(row) >= 5 else ""
        if len(row) >= 1 and row[0] == name and row_dept == search_dept:
            target_row = i + 1
            break

    if not target_row:
        if is_subtract: return None, None # 減算時は新規作成しない
        sheet.append_row([name, value, value, "", search_dept])
        return value, value

    # 既存データの更新
    try:
        val_b = int(sheet.cell(target_row, 2).value or 0)
        val_c = int(sheet.cell(target_row, 3).value or 0)
    except:
        val_b, val_c = 0, 0

    new_month = max(0, val_b - value) if is_subtract else val_b + value
    new_total = max(0, val_c - value) if is_subtract else val_c + value
    
    sheet.update_cell(target_row, 2, new_month)
    sheet.update_cell(target_row, 3, new_total)
    return new_month, new_total

# --- 4. ユーザーコマンド ---

@bot.command()
async def help(ctx):
    help_msg = """
📜 **勤務管理Bot コマンド一覧**

**【一般コマンド】**
`!work [分]` : 部署指定なしで時間を記録
`!dwork [部署名] [分]` : 部署を指定して時間を記録
`!total [名前]` : 指定した人（省略時は自分）の全記録を表示

**【ランキング】**
`!mranking` : 今月の個人ランキング（TOP10）
`!ranking` : 累計の個人ランキング（TOP10）
`!granking` : 部署ごとの合計時間ランキング
`!dranking [部署名]` : 特定の部署内のランキング

**【幹部専用】**
`!add [名前] [分]` : 指定した人の個人記録に加算
`!sub [名前] [分]` : 指定した人の個人記録から減算
`!dadd [名前] [部署名] [分]` : 指定した人の部署記録に加算
`!dsub [名前] [部署名] [分]` : 指定した人の部署記録から減算
`!reset` : 【注意】今月の月間記録を全リセット
    """
    await ctx.send(help_msg)

@bot.command()
async def work(ctx, minutes: int):
    m, t = update_work_time(ctx.author.display_name, minutes)
    await ctx.send(f"✅ {ctx.author.display_name}さん、未指定で {minutes}分記録しました。\n（今月合計: {m}分 / 累計: {t}分）")

@bot.command()
async def dwork(ctx, dept_input: str, minutes: int):
    dept_name, _ = find_dept(dept_input)
    if not dept_name:
        return await ctx.send(f"❌ 部署名 '{dept_input}' が見つかりません。正確に入力してください。")
    m, t = update_work_time(ctx.author.display_name, minutes, dept=dept_name)
    await ctx.send(f"✅ {ctx.author.display_name}さん、[{dept_name}] に {minutes}分記録しました。\n（今月合計: {m}分 / 累計: {t}分）")

@bot.command()
async def total(ctx, name: str = None):
    target = name if name else ctx.author.display_name
    try:
        data = sheet.get_all_values()
        # ターゲットに一致するすべての行を取得
        user_rows = [row for row in data if len(row) >= 1 and row[0] == target]
        
        if not user_rows:
            return await ctx.send(f"❌ {target} さんの記録は見つかりませんでした。")

        msg = f"📊 **{target} さんの勤務記録**\n"
        seen_depts = set()
        for r in user_rows:
            d_label = r[4] if len(r) >= 5 and r[4] else "個人・未指定"
            if d_label in seen_depts: continue # 重複表示防止
            seen_depts.add(d_label)
            
            m_val = r[1] if len(r) > 1 else "0"
            t_val = r[2] if len(r) > 2 else "0"
            msg += f"・{d_label}: 今月 {m_val}分 / 累計 {t_val}分\n"
        
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"❌ エラーが発生しました: {e}")

# --- 5. ランキングコマンド ---

@bot.command()
async def mranking(ctx):
    data = sheet.get_all_values()[1:] # ヘッダー除外
    stats = {}
    for r in data:
        stats[r[0]] = stats.get(r[0], 0) + int(r[1] or 0)
    sorted_s = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:10]
    msg = "🏆 **今月の個人総合ランキング (TOP10)**\n"
    for i, (name, val) in enumerate(sorted_s): msg += f"{i+1}位: {name} ({val}分)\n"
    await ctx.send(msg)

@bot.command()
async def granking(ctx):
    data = sheet.get_all_values()[1:]
    depts = {}
    for r in data:
        d = r[4] if len(r) >= 5 and r[4] else "未指定"
        depts[d] = depts.get(d, 0) + int(r[1] or 0)
    sorted_d = sorted(depts.items(), key=lambda x: x[1], reverse=True)
    msg = "🏆 **部署別合計時間ランキング**\n"
    for i, (name, val) in enumerate(sorted_d): msg += f"{i+1}位: {name} ({val}分)\n"
    await ctx.send(msg)

# --- 6. 幹部専用コマンド ---

@bot.command()
@is_admin()
async def add(ctx, name: str, minutes: int):
    update_work_time(name, minutes)
    await ctx.send(f"👮 {name}さんの個人記録に {minutes}分加算しました。")

@bot.command()
@is_admin()
async def dadd(ctx, name: str, dept_input: str, minutes: int):
    dept_name, _ = find_dept(dept_input)
    if dept_name:
        update_work_time(name, minutes, dept=dept_name)
        await ctx.send(f"👮 {name}さんの[{dept_name}]に {minutes}分加算しました。")

@bot.command()
@is_admin()
async def reset(ctx):
    # 月間記録（2列目）をすべて0にする
    data = sheet.get_all_values()
    for i in range(2, len(data) + 1):
        sheet.update_cell(i, 2, 0)
    await ctx.send("🚨 全員の月間勤務記録をリセットしました。")

# --- 7. 起動 ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.run(os.environ["TOKEN"])
