import os
import discord
import gspread
import json
from datetime import datetime, timezone, timedelta
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. Flaskの設定 (保持用) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. 設定と認証 ---
try:
    creds_dict = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("勤務記録シート").sheet1 
except Exception as e:
    print(f"初期設定エラー: {e}")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# 幹部設定
KANKU_ROLE_ID = 1397055554144309358
KANKU_ROLE_NAME = "管理部【ADD】--Admin Department"

# 部署リスト（全リスト統合）
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

# --- 3. 共通関数 ---
def is_admin():
    async def predicate(ctx):
        return any(role.id == KANKU_ROLE_ID or role.name == KANKU_ROLE_NAME for role in ctx.author.roles)
    return commands.check(predicate)

def find_dept(input_text):
    candidates = [v for v in DEPT_ROLES.values() if input_text in v]
    if len(candidates) == 1: return candidates[0], None
    return (candidates[0], None) if input_text in candidates else (None, candidates)

def update_work_time(name, value, dept=None, is_subtract=False):
    data = sheet.get_all_values()
    target_row = None
    search_dept = dept if dept else ""
    for i, row in enumerate(data):
        d_val = row[4] if len(row) >= 5 else ""
        if row[0] == name and d_val == search_dept:
            target_row = i + 1
            break

    if not target_row:
        if is_subtract: return None, None
        sheet.append_row([name, value, value, "", search_dept])
        return value, value

    val_b = int(sheet.cell(target_row, 2).value or 0)
    val_c = int(sheet.cell(target_row, 3).value or 0)
    new_m = max(0, val_b - value) if is_subtract else val_b + value
    new_t = max(0, val_c - value) if is_subtract else val_c + value
    sheet.update_cell(target_row, 2, new_m)
    sheet.update_cell(target_row, 3, new_t)
    return new_m, new_t

# --- 4. コマンド ---

@bot.command()
async def help(ctx):
    msg = """**📜 勤務管理コマンド一覧**
`!work [分]` : 個人記録に追加
`!dwork [部署名] [分]` : 部署記録に追加
`!total [名前]` : 自分の（または誰かの）全記録を表示
`!mranking` : 今月の個人ランキング
`!ranking` : 累計ランキング
`!granking` : 部署別ランキング
`!add [名] [分]` : 【幹部】個人記録に追加
`!dadd [名] [部署] [分]` : 【幹部】部署記録に追加"""
    await ctx.send(msg)

@bot.command()
async def total(ctx, name: str = None):
    target = name if name else ctx.author.display_name
    try:
        data = sheet.get_all_values()
        records = [row for row in data if len(row) >= 1 and row[0] == target]
        if not records: return await ctx.send(f"❌ {target} さんの記録なし")
        
        msg = f"📊 **{target} さんの記録**\n"
        seen_depts = set()
        for r in records:
            d_name = r[4] if len(r) >= 5 and r[4] else "個人・未指定"
            if d_name in seen_depts: continue
            seen_depts.add(d_name)
            msg += f"・{d_name}: 今月 {r[1]}分 / 累計 {r[2]}分\n"
        await ctx.send(msg)
    except Exception as e: await ctx.send(f"❌ エラー: {e}")

@bot.command()
async def work(ctx, minutes: int):
    m, t = update_work_time(ctx.author.display_name, minutes)
    await ctx.send(f"✅ {ctx.author.display_name}さん、{minutes}分追加（今月: {m} / 累計: {t}）")

@bot.command()
async def dwork(ctx, dept_in: str, minutes: int):
    d_name, _ = find_dept(dept_in)
    if not d_name: return await ctx.send(f"❌ 部署 '{dept_in}' 不明")
    m, t = update_work_time(ctx.author.display_name, minutes, dept=d_name)
    await ctx.send(f"✅ [{d_name}] {minutes}分追加（今月: {m} / 累計: {t}）")

@bot.command()
async def mranking(ctx):
    data = sheet.get_all_values()
    if len(data) <= 1: return await ctx.send("❌ データなし")
    r_list = [{"n": r[0], "v": int(r[1] or 0)} for r in data[1:]]
    sorted_r = sorted(r_list, key=lambda x: x["v"], reverse=True)
    msg = "🏆 **今月個人ランキング**\n"
    for i, item in enumerate(sorted_r[:10]): msg += f"{i+1}位: {item['n']} - {item['v']}分\n"
    await ctx.send(msg)

@bot.command()
async def granking(ctx):
    data = sheet.get_all_values()
    if len(data) <= 1: return await ctx.send("❌ データなし")
    depts = {}
    for r in data[1:]:
        d = r[4] if len(r) >= 5 and r[4] else "未指定"
        depts[d] = depts.get(d, 0) + int(r[1] or 0)
    sorted_d = sorted(depts.items(), key=lambda x: x[1], reverse=True)
    msg = "🏆 **部署別ランキング**\n"
    for i, (name, val) in enumerate(sorted_d): msg += f"{i+1}位: {name} - {val}分\n"
    await ctx.send(msg)

@bot.command()
@is_admin()
async def add(ctx, name: str, minutes: int):
    update_work_time(name, minutes)
    await ctx.send(f"👮 {name}さんの個人記録に {minutes}分追加")

@bot.command()
@is_admin()
async def dadd(ctx, name: str, dept_in: str, minutes: int):
    d_name, _ = find_dept(dept_in)
    if d_name:
        update_work_time(name, minutes, dept=d_name)
        await ctx.send(f"👮 {name}さんの[{d_name}]に {minutes}分追加")

@bot.event
async def on_ready(): print(f"Logged in: {bot.user}")

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.run(os.environ["TOKEN"])
