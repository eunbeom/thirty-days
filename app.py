# -*- coding: utf-8 -*-
import os
from calendar import monthrange
from datetime import datetime

import redis as redis
import requests
from flask import Flask, request, json
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage, \
    BubbleContainer, BoxComponent, TextComponent, FillerComponent, ImageComponent

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
        profile = line_bot_api.get_group_member_profile(event.source.group_id, event.source.user_id)
    elif event.source.type == 'room':
        group_id = event.source.room_id
        profile = line_bot_api.get_room_member_profile(event.source.room_id, event.source.user_id)
    elif event.source.type == 'user':
        group_id = event.source.user_id
        profile = line_bot_api.get_profile(event.source.user_id)
    else:
        return

    now = datetime.now()
    weekday, number_of_days = monthrange(now.year, now.month)

    key_name = f'{group_id}:{event.source.user_id}:{profile.display_name}'
    key_days = f'{group_id}:{event.source.user_id}:{now.year}-{now.month}'
    days = r.get(key_days) if r.exists(key_days) else 'X' * number_of_days
    days = f'{days[:now.day - 1]}O{days[now.day:]}'
    message = f"{days.count('O')}회 달성!"

    r.mset({key_name: profile.display_name, key_days: days})

    line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=message, contents=draw(
        display_name=profile.display_name, message=message, days=days,
        weekday=weekday, holiday=get_holiday(now.year, now.month)
    )))


def draw(display_name, message, days, weekday, holiday):
    cells = []
    for i in range((weekday + 1) % 7):
        cells.append(FillerComponent())
    for i in range(days):
        if days[i] == 'O':
            cells.append(
                ImageComponent(url='https://raw.githubusercontent.com/eunbeom/thirty-days/master/static/check.png'))
        else:
            day = str(i + 1)
            color = '#ff0000' if len(cells) % 7 == 0 or day in holiday else None
            cells.append(TextComponent(align='center', gravity='center', size='sm', color=color, text=day))
    for i in range((7 - len(cells) % 7) % 7):
        cells.append(FillerComponent())

    contents = [TextComponent(text=message, weight='bold'), TextComponent(text=display_name, size='sm')]
    for start in range(0, len(cells), 7):
        contents.append(BoxComponent(layout='horizontal', contents=cells[start:start + 7]))

    return BubbleContainer(direction='ltr', size='micro', body=BoxComponent(layout='vertical', contents=contents))


def get_holiday(year, month):
    url = 'http://openapi.kasi.re.kr/openapi/service/SpcdeInfoService/getHoliDeInfo'
    try:
        text = requests.get(url, params={'_type': 'json', 'solYear': year, 'solMonth': f"{month:02d}"}).text
        items = json.loads(text)['response']['body']['items']
        if items == '':
            return []
        elif type(items['item']) == dict:
            return [items['item']['locdate'] % 100]
        else:
            holiday = list()
            for item in items['item']:
                holiday.append(item['locdate'] % 100)
            return holiday
    except:
        return []


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.environ['PORT'])
