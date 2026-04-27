import os
import discord
import gspread
import json
import asyncio
from datetime import datetime
from flask import Flask
from threading import Thread
from discord.ext import commands, tasks
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

# --- Flaskサーバー（叩き起こし用） ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"
def run_web(): app.run(host='0.0.0.0', port=8080)

# --- 機能関数 ---
def update_work_time_by_name(name, value, is_subtract=False):
    cell = sheet.find(name)
    if not cell:
        if is_subtract: return None, None
        sheet.append_row([name, value, value])
        return value, value

    row = cell.row
    val_b = sheet.cell(row, 2).value
    val_c = sheet.cell(row, 3).value
    current_month = int(val_b) if val_b and val_b.isdigit() else 0
    current_total = int(val_c) if val_c and val_c.isdigit() else 0
    
    new_month = max(0, current_month - value) if is_subtract else current_month + value
    new_total = max(0, current_total - value) if is_subtract else current_total + value
        
    sheet.update_cell(row, 2, new_month)
    sheet.update_cell(row, 3, new_total)
    return new_month, new_total

# --- 自動リセットタスク ---
@tasks.loop(hours=24)
async def auto_reset():
    if datetime.now().day == 1:
        sheet.batch_clear(["B2:B10000"])

@bot.event
async def on_ready():
    auto_reset.start()
    print("Bot is ready.")

# --- コマンド ---

# 自分の追加
@bot.command()
async def work(ctx, minutes: int):
    month, total = update_work_time_by_name(ctx.author.display_name, minutes, is_subtract=False)
    await ctx.send(f"✅ {ctx.author.display_name} さん、{minutes}分追加しました（今月: {month}分 / 累計: {total}分）。")

# 自分の削除
@bot.command()
async def delete(ctx, minutes: int):
    month, total = update_work_time_by_name(ctx.author.display_name, minutes, is_subtract=True)
    await ctx.send(f"⚠️ {ctx.author.display_name} さんの記録から {minutes}分削除しました（今月: {month}分 / 累計: {total}分）。")

# 幹部用：他人に追加
@bot.command()
@commands.has_role(KANKU_ROLE_ID)
async def add(ctx, name: str, minutes: int):
    month, total = update_work_time_by_name(name, minutes, is_subtract=False)
    await ctx.send(f"👮 幹部権限: '{name}' さんに {minutes}分追加しました。")

# 幹部用：他人の削除
@bot.command()
@commands.has_role(KANKU_ROLE_ID)
async def sub(ctx, name: str, minutes: int):
    month, total = update_work_time_by_name(name, minutes, is_subtract=True)
    if month is not None:
        await ctx.send(f"⚠️ 幹部権限: '{name}' さんから {minutes}分削除しました。")
    else:
        await ctx.send(f"❌ '{name}' さんが見つかりません。")

# トータル確認
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
@commands.has_role(KANKU_ROLE_ID)
async def reset(ctx):
    sheet.batch_clear(["B2:B10000"])
    await ctx.send("🧹 幹部権限: 今月の勤務記録を全リセットしました。")

# --- 実行 ---
if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.run(os.environ["TOKEN"])
