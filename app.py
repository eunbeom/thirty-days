# -*- coding: utf-8 -*-
import os
from calendar import monthrange
from datetime import datetime

import redis as redis
from flask import Flask, request, json, render_template
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

r = redis.from_url(os.environ.get("REDIS_URL"), charset="utf-8", decode_responses=True)


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

    if event.source.type == 'group':
        group_id = event.source.group_id
        profile = line_bot_api.get_group_member_profile(event.source.user_id)
    elif event.source.type == 'room':
        group_id = event.source.room_id
        profile = line_bot_api.get_room_member_profile(event.source.user_id)
    elif event.source.type == 'user':
        group_id = event.source.user_id
        profile = line_bot_api.get_profile(event.source.user_id)
    else:
        return

    now = datetime.now()
    weekday, number_of_days = monthrange(now.year, now.month)

    key = f'{group_id}:{event.source.user_id}:{now.year}-{now.month}'
    days = r.get(key) if r.exists(key) else 'X' * number_of_days
    days = f'{days[:now.day - 1]}O{days[now.day:]}'
    count = days.count('O')

    r.set(key, days)

    contents = json.loads(render_template('flex.json', display_name=profile.display_name, count=count, days=days))
    line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=f"{count}회 달성!", contents=contents))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.environ['PORT'])
