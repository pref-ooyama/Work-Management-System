import os
import discord
import gspread
import json
from discord.ext import commands
from oauth2client.service_account import ServiceAccountCredentials # ここを確実にインポート

# Google Sheetsの設定
# 環境変数からJSONを読み込む
creds_dict = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# クレデンシャルの作成
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("勤務記録シート").sheet1 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ユーザーの勤務時間を更新する関数
def update_work_time(user_id, value, is_subtract=False):
    user_id = str(user_id)
    try:
        cell = sheet.find(user_id)
    except:
        return False
    
    if not cell:
        return False

    row = cell.row
    # 現在のB列(今月)とC列(累計)の値を取得
    val_b = sheet.cell(row, 2).value
    val_c = sheet.cell(row, 3).value
    current_month = int(val_b) if val_b and val_b.isdigit() else 0
    current_total = int(val_c) if val_c and val_c.isdigit() else 0
    
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
            await ctx.send("❌ ユーザーがリストに登録されていません。A列にDiscord IDを入力してください。")

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
    await ctx.send("🧹 今月の勤務記録（B列）をリセットしました！累計（C列）はそのままです。")

bot.run(os.environ["TOKEN"])
