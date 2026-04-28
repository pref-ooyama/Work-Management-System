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

KANKU_ROLE_ID = 1397055554144309358

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
    val_b = int(sheet.cell(row, 2).value or 0)
    val_c = int(sheet.cell(row, 3).value or 0)
    
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
    # 毎月1日にB列（今月分）をクリア（C列の累計は保持）
    if now.day == 1:
        cell_list = sheet.range(f"B2:B{sheet.row_count}")
        for cell in cell_list:
            cell.value = ''
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
        m = sheet.cell(cell.row, 2).value
        t = sheet.cell(cell.row, 3).value
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
        if len(row) >= 3 and row[2].isdigit():
            ranking_data.append({"name": row[0], "total": int(row[2])})
    
    sorted_ranking = sorted(ranking_data, key=lambda x: x["total"], reverse=True)
    msg = "📊 **勤務時間ランキング（累計）**\n"
    for i, item in enumerate(sorted_ranking[:10]):
        msg += f"{i+1}位: {item['name']} - **{item['total']}分**\n"
    await ctx.send(msg)

# --- 幹部用 ---
@bot.command()
@commands.has_role(KANKU_ROLE_ID)
async def add(ctx, name: str, minutes: int):
    update_work_time_by_name(name, minutes, is_subtract=False)
    await ctx.send(f"👮 幹部権限: '{name}' さんに {minutes}分追加しました。")

@bot.command()
@commands.has_role(KANKU_ROLE_ID)
async def sub(ctx, name: str, minutes: int):
    month, _ = update_work_time_by_name(name, minutes, is_subtract=True)
    if month is not None:
        await ctx.send(f"⚠️ 幹部権限: '{name}' さんから {minutes}分削除しました。")
    else:
        await ctx.send(f"❌ '{name}' さんが見つかりません。")

@bot.command()
@commands.has_role(KANKU_ROLE_ID)
async def reset(ctx):
    # 今月分(B列)のみクリアし、累計(C列)は維持
    cell_list = sheet.range(f"B2:B{sheet.row_count}")
    for cell in cell_list:
        cell.value = ''
    sheet.update_cells(cell_list)
    await ctx.send("🧹 幹部権限: 今月の勤務記録を全リセットしました。")

@bot.event
async def on_ready():
    auto_reset_task.start()
    print(f"{bot.user} が起動しました。")

# --- 実行 ---
if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.run(os.environ["TOKEN"])
