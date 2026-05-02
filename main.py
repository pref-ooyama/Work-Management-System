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

# 権限チェック用の関数
def is_admin():
    async def predicate(ctx):
        # ロールID または ロール名 でチェック
        has_id = any(role.id == KANKU_ROLE_ID for role in ctx.author.roles)
        has_name = any(role.name == KANKU_ROLE_NAME for role in ctx.author.roles)
        return has_id or has_name
    return commands.check(predicate)

# --- Flaskサーバー（Render維持用） ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 共通関数 ---
def update_work_time_by_name(name, value, is_subtract=False):
    cell = sheet.find(name)
    if not cell:
        if is_subtract: return None, None
        sheet.append_row([name, value, value])
        return value, value

    row = cell.row
    # シートから値を取得（空文字の場合は0にする）
    val_b_raw = sheet.cell(row, 2).value
    val_c_raw = sheet.cell(row, 3).value
    val_b = int(val_b_raw) if val_b_raw and str(val_b_raw).isdigit() else 0
    val_c = int(val_c_raw) if val_c_raw and str(val_c_raw).isdigit() else 0
    
    new_month = max(0, val_b - value) if is_subtract else val_b + value
    new_total = max(0, val_c - value) if is_subtract else val_c + value
        
    sheet.update_cell(row, 2, new_month)
    sheet.update_cell(row, 3, new_total)
    return new_month, new_total

# --- 自動リセットタスク ---
@tasks.loop(hours=24)
async def auto_reset_task():
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)
    if now.day == 1:
        cell_list = sheet.range(f"B2:B{sheet.row_count}")
        for cell in cell_list:
            cell.value = 0
        sheet.update_cells(cell_list)
        print("Monthly reset completed.")

# --- コマンド ---

@bot.command()
async def work(ctx, minutes: int):
    month, total = update_work_time_by_name(ctx.author.display_name, minutes, is_subtract=False)
    await ctx.send(f"✅ {ctx.author.display_name} さん、{minutes}分追加しました（今月: {month}分 / 累計: {total}分）。")

@bot.command()
async def delete(ctx, minutes: int):
    month, total = update_work_time_by_name(ctx.author.display_name, minutes, is_subtract=True)
    await ctx.send(f"⚠️ {ctx.author.display_name} さんの記録から {minutes}分削除しました（今月: {month}分 / 累計: {total}分）。")

@bot.command()
async def total(ctx, name: str = None):
    target = name if name else ctx.author.display_name
    cell = sheet.find(target)
    if cell:
        m = sheet.cell(cell.row, 2).value or 0
        t = sheet.cell(cell.row, 3).value or 0
        await ctx.send(f"📊 '{target}' さんの勤務時間\n今月: **{m}分** / 累計: **{t}分** です！")
    else:
        await ctx.send(f"❌ '{target}' さんはまだ記録がありません。")

@bot.command()
async def ranking(ctx):
    data = sheet.get_all_values()
    if len(data) <= 1:
        return await ctx.send("❌ まだ記録がありません。")
    
    rows = data[1:] 
    ranking_data = []
    for row in rows:
        if len(row) >= 3 and str(row[2]).isdigit():
            ranking_data.append({"name": row[0], "total": int(row[2])})
    
    sorted_ranking = sorted(ranking_data, key=lambda x: x["total"], reverse=True)
    msg = "📊 **勤務時間ランキング（累計）**\n"
    for i, item in enumerate(sorted_ranking[:10]):
        msg += f"{i+1}位: {item['name']} - **{item['total']}分**\n"
    await ctx.send(msg)

@bot.command()
async def mranking(ctx):
    """月間ランキングを表示"""
    data = sheet.get_all_values()
    if len(data) <= 1:
        return await ctx.send("❌ まだ記録がありません。")
    
    rows = data[1:]
    ranking_data = []
    for row in rows:
        # B列（Index 1）が今月分
        if len(row) >= 2 and str(row[1]).isdigit():
            ranking_data.append({"name": row[0], "month": int(row[1])})
    
    sorted_ranking = sorted(ranking_data, key=lambda x: x["month"], reverse=True)
    msg = "📅 **勤務時間ランキング（今月分）**\n"
    for i, item in enumerate(sorted_ranking[:10]):
        msg += f"{i+1}位: {item['name']} - **{item['month']}分**\n"
    await ctx.send(msg)

# --- 幹部用 ---
@bot.command()
@is_admin()
async def add(ctx, name: str, minutes: int):
    update_work_time_by_name(name, minutes, is_subtract=False)
    await ctx.send(f"👮 幹部権限: '{name}' さんに {minutes}分追加しました。")

@bot.command()
@is_admin()
async def sub(ctx, name: str, minutes: int):
    month, _ = update_work_time_by_name(name, minutes, is_subtract=True)
    if month is not None:
        await ctx.send(f"⚠️ 幹部権限: '{name}' さんから {minutes}分削除しました。")
    else:
        await ctx.send(f"❌ '{name}' さんが見つかりません。")

@bot.command()
@is_admin()
async def reset(ctx):
    cell_list = sheet.range(f"B2:B{sheet.row_count}")
    for cell in cell_list:
        cell.value = 0
    sheet.update_cells(cell_list)
    await ctx.send("🧹 幹部権限: 今月の勤務記録を全リセットしました。")

@bot.event
async def on_ready():
    if not auto_reset_task.is_running():
        auto_reset_task.start()
    print(f"{bot.user} が起動しました。")

# --- 実行 ---
if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.run(os.environ["TOKEN"])
