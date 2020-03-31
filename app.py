# -*- coding: utf-8 -*-
import os
from datetime import datetime

import gspread
from flask import Flask, request, json, render_template
from gspread import WorksheetNotFound
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

scopes = 'https://www.googleapis.com/auth/spreadsheets'
credentials = json.loads(os.environ['CREDENTIALS'])
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scopes)


@app.route("/callback", methods=['POST'])
def callback():
    handler.handle(request.get_data(as_text=True), request.headers['X-Line-Signature'])
    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    if event.message.text == '@bye':
        if event.source.type == 'group':
            line_bot_api.leave_group(group_id=event.source.group_id)
        elif event.source.type == 'room':
            line_bot_api.leave_room(room_id=event.source.room_id)
        return

    if '#인증' not in event.message.text:
        return

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_url(os.environ['SPREADSHEETS_URL'])

    if event.source.type == 'group':
        group_id = event.source.group_id
    elif event.source.type == 'room':
        group_id = event.source.room_id
    else:
        return

    try:
        sheet = spreadsheet.worksheet(group_id)
    except WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(group_id, 1000, 33)
        cells = sheet.range(1, 1, 1, 33)
        cells[0].value = 'user_id'
        cells[1].value = '이름'
        for i in range(31):
            cells[2 + i].value = '{0}일'.format(i + 1)
        sheet.update_cells(cells)

    users = sheet.col_values(1)
    now = datetime.now()
    col = now.day + 2
    time_text = '{0:02d}:{1:02d}'.format(now.hour, now.minute)

    if event.source.type == 'group':
        profile = line_bot_api.get_group_member_profile(group_id, event.source.user_id)
    else:
        profile = line_bot_api.get_room_member_profile(group_id, event.source.user_id)

    if event.source.user_id in users:
        sheet.update_cell(users.index(event.source.user_id) + 1, col, time_text)
    else:
        sheet.update_cell(len(users) + 1, 1, event.source.user_id)
        sheet.update_cell(len(users) + 1, 2, profile.display_name)
        sheet.update_cell(len(users) + 1, col, time_text)
        users.append(event.source.user_id)

    row = users.index(event.source.user_id) + 1
    cells = sheet.range(row, 3, row, 33)
    count = sum(1 for cell in cells if cell.value)

    if '#테스트' in event.message.text:
        contents = render_template('flex.json', display_name=profile.display_name, count=count, cells=cells)
        print(contents)
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=f'{count}회 달성!', contents=contents))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(f'{count}회 달성!'))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.environ['PORT'])
