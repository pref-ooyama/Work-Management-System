import os
import discord
import gspread
import json
from discord.ext import commands
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheetsの設定
creds_dict = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("勤務記録シート").sheet1 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

KANKU_ROLE_ID = 1397055554144309358

def update_work_time_by_name(name, value, is_subtract=False):
    cell = sheet.find(name)
    
    # ユーザーが見つからない場合は「新規登録」
    if not cell:
        if is_subtract: return None, None # 削除コマンドで新規登録はさせない
        sheet.append_row([name, value, value])
        return value, value

    row = cell.row
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
    return new_month, new_total

# --- コマンド一覧 ---

@bot.command()
async def work(ctx, minutes: int):
    month, total = update_work_time_by_name(ctx.author.display_name, minutes, is_subtract=False)
    await ctx.send(f"✅ {ctx.author.display_name} さん、{minutes}分追加しました（累計: {total}分）。")

@bot.command()
@commands.has_role(KANKU_ROLE_ID)
async def add(ctx, name: str, minutes: int):
    month, total = update_work_time_by_name(name, minutes, is_subtract=False)
    await ctx.send(f"👮 幹部権限: '{name}' さんに {minutes}分追加しました。")

@bot.command()
@commands.has_role(KANKU_ROLE_ID)
async def sub(ctx, name: str, minutes: int):
    month, total = update_work_time_by_name(name, minutes, is_subtract=True)
    if month is not None:
        await ctx.send(f"⚠️ 幹部権限: '{name}' さんから {minutes}分削除しました。")
    else:
        await ctx.send(f"❌ '{name}' さんが見つかりません。")

@bot.command()
async def total(ctx, name: str = None):
    target_name = name if name else ctx.author.display_name
    cell = sheet.find(target_name)
    if cell:
        total_val = sheet.cell(cell.row, 3).value
        await ctx.send(f"📊 '{target_name}' さんの累計勤務時間は **{total_val}分** です！")
    else:
        await ctx.send(f"❌ '{target_name}' さんはまだ記録がありません。")

@bot.command()
@commands.has_role(KANKU_ROLE_ID)
async def reset(ctx):
    sheet.batch_clear(["B2:B10000"])
    await ctx.send("🧹 幹部権限: 今月の勤務記録を全リセットしました。")

bot.run(os.environ["TOKEN"])
