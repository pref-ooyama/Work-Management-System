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

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def work(ctx, arg: str):
    # 今月の年月を取得 (例: "2026-04")
    current_month = datetime.now().strftime("%Y-%m")
    
    # シートを取得（なければ作成）
    try:
        sheet = client.open("勤務記録シート").worksheet(current_month)
    except:
        # シートがない場合は新規作成し、ヘッダーも作成
        sheet = client.open("勤務記録シート").add_worksheet(title=current_month, rows="10000", cols="5")
        sheet.append_row(["ID", "名前", "分", "記録日時"])

    rows = sheet.get_all_values()
    
    # 1. !work <数字> (勤務時間記入)
    if arg.isdigit():
        minutes = int(arg)
        # 記録行: [ユーザーID, 名前, 分, 日付]
        sheet.append_row([str(ctx.author.id), ctx.author.display_name, minutes, str(datetime.now())])
        await ctx.send(f"✅ {ctx.author.display_name} さん、{minutes}分を記録しました。")
    
    # 2. !work month (今月の合計)
    elif arg == "month":
        total = sum(int(r[2]) for r in rows[1:] if r[0] == str(ctx.author.id))
        await ctx.send(f"📅 {current_month}月の勤務合計: {total}分")
        
    # 3. !work total (今までの累計：全シートを合算するのは大変なので、今月のシートの合計を表示)
    elif arg == "total":
        total = sum(int(r[2]) for r in rows[1:] if r[0] == str(ctx.author.id))
        await ctx.send(f"📊 今月の累計勤務時間: {total}分")
    
    else:
        await ctx.send("❌ コマンドが正しくありません。`!work <分>`, `!work month`, `!work total` を使ってください。")

bot.run(os.environ["TOKEN"])
