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


@app.route('/')
def index():
    now = datetime.now()
    month = f'{now.year}-{now.month:02d}'

    keys = list()
    for key in r.scan_iter(match=f'*:{month}', count=100):
        keys.append(key)

    values = r.mget(keys)

    count = dict()
    for i in range(len(keys)):
        key = keys[i]
        group_id = key.split(':', 1)[0]

        attend = 1 if values[i][now.day - 1] == 'O' else 0

        if group_id in count:
            count[group_id][0] += attend
            count[group_id][1] += 1
        else:
            count[group_id] = [attend, 1]

    res = ''
    for group_id in count:
        if group_id[0] != 'C':
            group_name = group_id
        else:
            group_name = r.get(f'group_name:{group_id}')
            if group_name is None:
                summary = line_bot_api.get_group_summary(group_id)
                group_name = summary.group_name
                r.set(f'group_name:{group_id}', group_name)

        res += f'<a href="{group_id}">{group_name}</a> : {count[group_id][0] / count[group_id][1]:.0%}<br>'
    return res


@app.route("/<gid>", methods=['GET', 'POST'])
def attendance(gid):
    keys = []
    now = datetime.now()

    if request.method == 'GET':
        month = f'{now.year}-{now.month:02d}'
    else:
        month = request.form['month']

    for key in r.scan_iter(match=f'{gid}:*:{month}', count=100):
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

    return render_template('table.html', table=table, label=list(range(1, length + 1)), month=month)


@app.route("/callback", methods=['POST'])
def callback():
    handler.handle(request.get_data(as_text=True), request.headers['X-Line-Signature'])
    return 'OK'


@handler.add(MessageEvent, message=StickerMessage)
def handle_sticker_message(event):
    print(event)

    if event.message.package_id == '13503068':
        group_id, profile = get_profile(event)
        if event.message.sticker_id == '356169382' or event.message.sticker_id == '356169383':
            check(event, group_id, profile, True)
        elif event.message.sticker_id == '356169384':
            check(event, group_id, profile, False)
        elif event.message.sticker_id == '356169385':
            url = f'https://{request.host}/{group_id}'
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=url))
        elif event.message.sticker_id == '356169386':
            check(event, group_id, profile, True, '#000000', '#ffffff')
        elif event.message.sticker_id == '356169387':
            check(event, group_id, profile, True, '#87ceeb', '#ffffff')
        elif event.message.sticker_id == '356169388':
            check(event, group_id, profile, True, '#fbccd1', '#ffffff')
        elif event.message.sticker_id == '356169389':
            check(event, group_id, profile, True, '#00C300', '#ffffff')
        else:
            return


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    print(f'{event.message.text} {event}')

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


def check(event, group_id, profile, attend, bg_color=None, font_color=None):
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
        weekday=weekday, holiday=get_holiday(now.year, now.month), bg_color=bg_color, font_color=font_color
    )))


def draw(display_name, message, days, weekday, holiday, bg_color, font_color):
    cells = []
    for i in range((weekday + 1) % 7):
        cells.append(FillerComponent())
    for i in range(len(days)):
        if days[i] == 'O':
            cells.append(
                ImageComponent(url='https://raw.githubusercontent.com/eunbeom/thirty-days/master/static/check.png'))
        else:
            color = '#ff0000' if len(cells) % 7 == 0 or i + 1 in holiday else font_color
            cells.append(TextComponent(align='center', gravity='center', size='sm', color=color, text=str(i + 1)))
    for i in range(-len(cells) % 7):
        cells.append(FillerComponent())

    contents = [TextComponent(text=message, weight='bold', color=font_color),
                TextComponent(text=display_name, size='sm', color=font_color)]
    for start in range(0, len(cells), 7):
        contents.append(BoxComponent(layout='horizontal', contents=cells[start:start + 7]))

    return BubbleContainer(direction='ltr', size='micro',
                           body=BoxComponent(layout='vertical', contents=contents, background_color=bg_color))


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
