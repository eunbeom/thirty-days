# -*- coding: utf-8 -*-
import os
from calendar import monthrange
from datetime import datetime

import redis as redis
import requests
from flask import Flask, request, json, render_template
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage, TextSendMessage, \
    BubbleContainer, BoxComponent, TextComponent, FillerComponent, ImageComponent, StickerMessage

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

r = redis.from_url(os.environ.get("REDIS_URL"), charset="utf-8", decode_responses=True)

saved_year, saved_month, saved_holiday = 0, 0, []


@app.route("/<gid>", methods=['GET', 'POST'])
def index(gid):
    keys = []
    now = datetime.now()

    if request.method == 'GET':
        month = f'{now.year}-{now.month:02d}'
    else:
        month = request.form['month']

    for key in r.scan_iter(f'{gid}:*:{month}'):
        uid = key.split(':')[1]
        keys.append(f'display_name:{uid}')
        keys.append(f'{gid}:{uid}:{month}')

    if len(keys) == 0:
        return render_template('empty.html', month=month)

    values = r.mget(keys)

    length = len(values[1])
    table = [[''] + [str(i + 1) for i in range(length)]]
    for i in range(0, len(values), 2):
        row = [values[i]] + [char if char == 'O' else '' for char in values[i + 1]]
        table.append(row)

    return render_template('index.html', table=table, label=list(range(1, length + 1)), month=month)


@app.route("/callback", methods=['POST'])
def callback():
    handler.handle(request.get_data(as_text=True), request.headers['X-Line-Signature'])
    return 'OK'


@handler.add(MessageEvent, message=StickerMessage)
def handle_sticker_message(event):
    print(f'package_id : {event.message.package_id}, sticker_id : {event.message.sticker_id}')
    if event.message.package_id == '1813268' and event.message.sticker_id == '25483443':
        group_id, profile = get_profile(event)
        check(event, group_id, profile, '#ffff00')


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    if event.message.text == '@bye':
        if event.source.type == 'group':
            line_bot_api.leave_group(group_id=event.source.group_id)
        elif event.source.type == 'room':
            line_bot_api.leave_room(room_id=event.source.room_id)
        return

    if not any(tag in event.message.text for tag in ['#인증', '#ㅇㅈ']):
        return

    group_id, profile = get_profile(event)

    if any(tag in event.message.text for tag in ['#인증내역', '#인증현황']):
        url = f'https://{request.host}/{group_id}'
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=url))
        return

    attend = False if '#인증취소' in event.message.text else True
    check(event, group_id, profile, attend)


def get_profile(event):
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
    return group_id, profile


def check(event, group_id, profile, attend, color=None):
    now = datetime.now()
    weekday, number_of_days = monthrange(now.year, now.month)

    key_name = f'display_name:{event.source.user_id}'
    key_days = f'{group_id}:{event.source.user_id}:{now.year}-{now.month:02d}'
    days = r.get(key_days) if r.exists(key_days) else 'X' * number_of_days
    mark = 'O' if attend else "X"
    days = f'{days[:now.day - 1]}{mark}{days[now.day:]}'
    message = f"{days.count('O')}회 달성!"

    r.mset({key_name: profile.display_name, key_days: days})

    line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=message, contents=draw(
        display_name=profile.display_name, message=message, days=days,
        weekday=weekday, holiday=get_holiday(now.year, now.month), color=color
    )))


def draw(display_name, message, days, weekday, holiday, color):
    cells = []
    for i in range((weekday + 1) % 7):
        cells.append(FillerComponent())
    for i in range(len(days)):
        if days[i] == 'O':
            cells.append(
                ImageComponent(url='https://raw.githubusercontent.com/eunbeom/thirty-days/master/static/check.png'))
        else:
            color = '#ff0000' if len(cells) % 7 == 0 or i + 1 in holiday else None
            cells.append(TextComponent(align='center', gravity='center', size='sm', color=color, text=str(i + 1)))
    for i in range(-len(cells) % 7):
        cells.append(FillerComponent())

    contents = [TextComponent(text=message, weight='bold'), TextComponent(text=display_name, size='sm')]
    for start in range(0, len(cells), 7):
        contents.append(BoxComponent(layout='horizontal', contents=cells[start:start + 7]))

    return BubbleContainer(direction='ltr', size='micro',
                           body=BoxComponent(layout='vertical', contents=contents, background_color=color))


def get_holiday(year, month):
    global saved_year, saved_month, saved_holiday
    if year == saved_year and month == saved_month:
        return saved_holiday

    url = 'http://openapi.kasi.re.kr/openapi/service/SpcdeInfoService/getRestDeInfo'
    try:
        res = requests.get(url, params={'_type': 'json', 'solYear': year, 'solMonth': f"{month:02d}"})
        items = json.loads(res.text)['response']['body']['items']
        if items == '':
            holiday = []
        elif type(items['item']) == dict:
            holiday = [items['item']['locdate'] % 100]
        else:
            holiday = []
            for item in items['item']:
                holiday.append(item['locdate'] % 100)
        saved_year, saved_month, saved_holiday = year, month, holiday
        return holiday
    except:
        return []


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.environ['PORT'])
