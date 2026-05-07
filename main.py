import os
import discord
import gspread
import json
from datetime import datetime, timezone, timedelta
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
creds_dict = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("勤務記録シート").sheet1 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 幹部設定
KANKU_ROLE_ID = 1397055554144309358
KANKU_ROLE_NAME = "管理部【ADD】--Admin Department"

# 部署リスト
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

# --- Flask ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 共通関数 ---
def is_admin():
    async def predicate(ctx):
        has_id = any(role.id == KANKU_ROLE_ID for role in ctx.author.roles)
        has_name = any(role.name == KANKU_ROLE_NAME for role in ctx.author.roles)
        return has_id or has_name
    return commands.check(predicate)

def find_dept(input_text):
    candidates = [v for v in DEPT_ROLES.values() if input_text in v]
    if len(candidates) == 1: return candidates[0], None
    elif len(candidates) > 1:
        if input_text in candidates: return input_text, None
        return None, candidates
    return None, None

def update_work_time(name, value, dept=None, is_subtract=False):
    data = sheet.get_all_values()
    target_row = None
    for i, row in enumerate(data):
        if dept:
            if len(row) >= 5 and row[0] == name and row[4] == dept:
                target_row = i + 1
                break
        else:
            if len(row) >= 1 and row[0] == name:
                d_val = row[4] if len(row) >= 5 else ""
                if not d_val:
                    target_row = i + 1
                    break

    if not target_row:
        if is_subtract: return None, None
        sheet.append_row([name, value, value, "", dept if dept else ""])
        return value, value

    val_b_raw = sheet.cell(target_row, 2).value
    val_c_raw = sheet.cell(target_row, 3).value
    def to_int(v):
        try: return int(v) if v else 0
        except: return 0
    val_b, val_c = to_int(val_b_raw), to_int(val_c_raw)
    
    new_month = max(0, val_b - value) if is_subtract else val_b + value
    new_total = max(0, val_c - value) if is_subtract else val_c + value
    
    sheet.update_cell(target_row, 2, new_month)
    sheet.update_cell(target_row, 3, new_total)
    return new_month, new_total

# --- 自動リセット ---
@tasks.loop(hours=24)
async def auto_reset_task():
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)
    if now.day == 1:
        cell_list = sheet.range(f"B2:B{sheet.row_count}")
        for cell in cell_list: cell.value = 0
        sheet.update_cells(cell_list)

# --- コマンド ---

# 部署別入力
@bot.command()
async def dwork(ctx, dept_input: str, minutes: int):
    dept_name, candidates = find_dept(dept_input)
    if candidates: return await ctx.send(f"⚠️ 候補複数: `{', '.join(candidates)}`")
    if not dept_name: return await ctx.send(f"❌ 部署名 '{dept_input}' 不明")
    month, total = update_work_time(ctx.author.display_name, minutes, dept=dept_name)
    await ctx.send(f"✅ {ctx.author.display_name}さん [{dept_name}]\n{minutes}分追加（今月: {month} / 累計: {total}）")

# 個人入力（従来）
@bot.command()
async def work(ctx, minutes: int):
    month, total = update_work_time(ctx.author.display_name, minutes)
    await ctx.send(f"✅ {ctx.author.display_name}さん、{minutes}分追加（今月: {month} / 累計: {total}）。")

@bot.command()
async def delete(ctx, minutes: int):
    month, total = update_work_time(ctx.author.display_name, minutes, is_subtract=True)
    await ctx.send(f"⚠️ {ctx.author.display_name}さんの記録から{minutes}分削除。")

# 表示系
@bot.command()
async def total(ctx, name: str = None):
    target = name if name else ctx.author.display_name
    data = sheet.get_all_values()
    records = [row for row in data if len(row) >= 1 and row[0] == target]
    if not records: return await ctx.send(f"❌ '{target}' さんの記録なし。")
    msg = f"📊 **{target} さんの記録**\n"
    for r in records:
        d_name = r[4] if len(r) >= 5 and r[4] else "個人・未指定"
        msg += f"・{d_name}: 今月 {r[1]}分 / 累計 {r[2]}分\n"
    await ctx.send(msg)

@bot.command()
async def ranking(ctx):
    """個人累計TOP10"""
    data = sheet.get_all_values()
    if len(data) <= 1: return await ctx.send("❌ 記録なし。")
    r_list = [{"label": f"{r[0]}({r[4]})" if len(r)>=5 and r[4] else r[0], "val": int(r[2])} for r in data[1:] if len(r)>=3 and str(r[2]).isdigit()]
    sorted_r = sorted(r_list, key=lambda x: x["val"], reverse=True)
    msg = "📊 **累計個人ランキング (TOP 10)**\n"
    for i, item in enumerate(sorted_r[:10]): msg += f"{i+1}位: {item['label']} - {item['val']}分\n"
    await ctx.send(msg)

@bot.command()
async def mranking(ctx):
    """個人今月全員分"""
    data = sheet.get_all_values()
    if len(data) <= 1: return await ctx.send("❌ 記録なし。")
    r_list = [{"label": f"{r[0]}({r[4]})" if len(r)>=5 and r[4] else r[0], "val": int(r[1])} for r in data[1:] if len(r)>=2 and str(r[1]).isdigit()]
    sorted_r = sorted(r_list, key=lambda x: x["val"], reverse=True)
    msg = "📅 **今月個人ランキング (全員)**\n"
    for i, item in enumerate(sorted_r): msg += f"{i+1}位: {item['label']} - {item['val']}分\n"
    if len(msg) > 2000:
        for chunk in [msg[i:i+1900] for i in range(0, len(msg), 1900)]: await ctx.send(chunk)
    else: await ctx.send(msg)

@bot.command()
async def granking(ctx):
    """部署対抗ランキング（今月の合計時間）"""
    data = sheet.get_all_values()
    if len(data) <= 1: return await ctx.send("❌ 記録なし。")
    dept_totals = {}
    for r in data[1:]:
        if len(r) >= 5 and r[4]:
            dept = r[4]
            minutes = int(r[1]) if str(r[1]).isdigit() else 0
            dept_totals[dept] = dept_totals.get(dept, 0) + minutes
    if not dept_totals: return await ctx.send("❌ 部署ごとの記録なし。")
    sorted_dept = sorted(dept_totals.items(), key=lambda x: x[1], reverse=True)
    msg = "🏆 **部署対抗ランキング (今月の合計)**\n"
    for i, (dept, total_min) in enumerate(sorted_dept):
        msg += f"{i+1}位: {dept} - **{total_min}分**\n"
    if len(msg) > 2000:
        for chunk in [msg[i:i+1900] for i in range(0, len(msg), 1900)]: await ctx.send(chunk)
    else: await ctx.send(msg)

@bot.command()
async def dranking(ctx, dept_input: str):
    """指定部署内のランキング"""
    dept_name, candidates = find_dept(dept_input)
    if candidates: return await ctx.send(f"⚠️ 候補複数: `{', '.join(candidates)}`")
    if not dept_name: return await ctx.send("❌ 部署名不明。")
    data = sheet.get_all_values()
    r_list = [{"name": r[0], "val": int(r[1])} for r in data[1:] if len(r)>=5 and r[4] == dept_name and str(r[1]).isdigit()]
    if not r_list: return await ctx.send(f"❌ '{dept_name}' の記録なし。")
    sorted_r = sorted(r_list, key=lambda x: x["val"], reverse=True)
    msg = f"🏢 **{dept_name} 内ランキング**\n"
    for i, item in enumerate(sorted_r): msg += f"{i+1}位: {item['name']} - {item['val']}分\n"
    await ctx.send(msg)

# 幹部用
@bot.command()
@is_admin()
async def add(ctx, name: str, minutes: int):
    update_work_time(name, minutes)
    await ctx.send(f"👮 幹部: '{name}' に {minutes}分追加。")

@bot.command()
@is_admin()
async def sub(ctx, name: str, minutes: int):
    update_work_time(name, minutes, is_subtract=True)
    await ctx.send(f"⚠️ 幹部: '{name}' から {minutes}分削除。")

@bot.command()
@is_admin()
async def dadd(ctx, name: str, dept_input: str, minutes: int):
    dept_name, _ = find_dept(dept_input)
    if not dept_name: return await ctx.send("❌ 部署名不明。")
    update_work_time(name, minutes, dept=dept_name)
    await ctx.send(f"👮 幹部: '{name}' の '{dept_name}' に {minutes}分追加。")

@bot.command()
@is_admin()
async def dsub(ctx, name: str, dept_input: str, minutes: int):
    dept_name, _ = find_dept(dept_input)
    if not dept_name: return await ctx.send("❌ 部署名不明。")
    update_work_time(name, minutes, dept=dept_name, is_subtract=True)
    await ctx.send(f"⚠️ 幹部: '{name}' の '{dept_name}' から削除。")

@bot.command()
@is_admin()
async def reset(ctx):
    cell_list = sheet.range(f"B2:B{sheet.row_count}")
    for cell in cell_list: cell.value = 0
    sheet.update_cells(cell_list)
    await ctx.send("🧹 今月の記録を全リセットしました。")

@bot.event
async def on_ready():
    if not auto_reset_task.is_running(): auto_reset_task.start()
    print(f"{bot.user} 起動")

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.run(os.environ["TOKEN"])
