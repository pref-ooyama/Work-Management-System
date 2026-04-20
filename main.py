import os
import discord
import gspread
import json
from discord.ext import commands

# Google Sheetsの設定
creds_dict = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
client = gspread.authorize(creds)
sheet = client.open("勤務記録シート").sheet1 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ユーザーを探して値を加算・減算するヘルパー関数
def update_work_time(user_id, value, is_subtract=False):
    user_id = str(user_id)
    cell = sheet.find(user_id)
    if not cell:
        return False # ユーザーが見つからない

    row = cell.row
    # 現在の値を取得（空なら0）
    current_month = int(sheet.cell(row, 2).value or 0)
    current_total = int(sheet.cell(row, 3).value or 0)
    
    if is_subtract:
        new_month = max(0, current_month - value)
        new_total = max(0, current_total - value)
    else:
        new_month = current_month + value
        new_total = current_total + value
        
    sheet.update_cell(row, 2, new_month)
    sheet.update_cell(row, 3, new_total)
    return True

@bot.command()
async def work(ctx, arg: str):
    if arg.isdigit():
        if update_work_time(ctx.author.id, int(arg), is_subtract=False):
            await ctx.send(f"✅ {ctx.author.display_name} さん、{arg}分追加しました。")
        else:
            await ctx.send("❌ ユーザーがリストに登録されていません。")

@bot.command()
async def delete(ctx, arg: str):
    if arg.isdigit():
        if update_work_time(ctx.author.id, int(arg), is_subtract=True):
            await ctx.send(f"⚠️ {ctx.author.display_name} さん、{arg}分を記録から削除しました。")
        else:
            await ctx.send("❌ ユーザーがリストに登録されていません。")

@bot.command()
async def reset(ctx):
    # B列（今月分）だけをクリア（2行目〜10000行目）
    sheet.batch_clear(["B2:B10000"])
    await ctx.send("🧹 今月の勤務記録（B列）をリセットしました！")

bot.run(os.environ["TOKEN"])
