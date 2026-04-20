import os
import discord
import gspread
import json
from discord.ext import commands
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Google Sheetsの設定
creds_dict = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
client = gspread.authorize(creds)
# スプレッドシート名に注意
sheet = client.open("勤務記録シート").sheet1 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def work(ctx, arg: str):
    rows = sheet.get_all_values()
    
    # 1. !work <数字> (勤務時間記入)
    if arg.isdigit():
        minutes = int(arg)
        # 行形式: [ユーザーID, 名前, 分, 日付(YYYY-MM)]
        date_str = datetime.now().strftime("%Y-%m")
        sheet.append_row([str(ctx.author.id), ctx.author.display_name, minutes, date_str])
        await ctx.send(f"✅ {ctx.author.display_name} さん、{minutes}分を記録しました。")
    
    # 2. !work month (今月の合計)
    elif arg == "month":
        current_month = datetime.now().strftime("%Y-%m")
        total = sum(int(r[2]) for r in rows if r[0] == str(ctx.author.id) and r[3] == current_month)
        await ctx.send(f"📅 今月の勤務合計: {total}分")
        
    # 3. !work total (今までの全部)
    elif arg == "total":
        total = sum(int(r[2]) for r in rows if r[0] == str(ctx.author.id))
        await ctx.send(f"📊 今までの累計勤務時間: {total}分")
    
    else:
        await ctx.send("❌ 指定されたコマンドが正しくありません。`!work <分>`, `!work month`, `!work total` を使ってください。")

bot.run(os.environ["TOKEN"])
