from flask import Flask, request, send_file, make_response
from playwright.sync_api import sync_playwright
import io
import os
import requests
import random

# Redis 라이브러리 로드
try:
    import redis
    redis_available = True
except ImportError:
    redis_available = False

app = Flask(__name__)

# --- Redis 연결 ---
r = None
if redis_available:
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            r = redis.from_url(redis_url)
            r.ping()
            print("Successfully connected to Redis.")
        except redis.exceptions.ConnectionError as e:
            r = None
            print(f"Could not connect to Redis: {e}")
    else: # 로컬 테스트용
        try:
            r = redis.Redis(host='localhost', port=6379, db=0)
            r.ping()
            print("Successfully connected to local Redis.")
        except redis.exceptions.ConnectionError as e:
            r = None
            print(f"Could not connect to local Redis: {e}")

# --- 공통 설정: 이미지 URL ---
IMAGE_BASE_URL = 'https://pub-46e5ec14460c439081d4bed697e21c3a.r2.dev/'

# --- HTML 템플릿 생성 함수 ---
def create_stream_html_template(title, image_url, all_chats):
    
    # 방송 화면 이미지 HTML 생성 (단일 이미지)
    image_html = f'<img src="{image_url}" alt="stream content">' if image_url else ""

    # 채팅 메시지 HTML 생성
    chats_html = ""
    for chat in all_chats:
        if chat.get('type') == 'text':
            chats_html += f"""
            <div class="chat-message">
                <span class="chat-username">{chat['user']}:</span>
                <span class="chat-text">{chat['text']}</span>
            </div>
            """
        elif chat.get('type') == 'emote':
            chats_html += f"""
            <div class="chat-message">
                <span class="chat-username">{chat['user']}:</span>
                <img src="{chat['emote_url']}" class="chat-emote">
            </div>
            """

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>Streaming Screen</title>
        <link rel="stylesheet" type="text/css" href="https://hangeul.pstatic.net/hangeul_static/css/lineseed.css">
        <style>
            :root {{ --bg-color: #18181b; --surface-color: #2a2a2e; --border-color: #444449; --primary-text-color: #efeff1; --secondary-text-color: #a0a0ab; --accent-color-light: #a970ff; }}
            body {{ background-color: var(--bg-color); display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: "LINESeed", sans-serif; color: var(--primary-text-color); }}
            .browser-window {{ width: 1024px; aspect-ratio: 4 / 3; background-color: var(--surface-color); border-radius: 8px; box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7); display: flex; flex-direction: column; overflow: hidden; }}
            .browser-header {{ background-color: #3c3c42; padding: 8px 15px; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }}
            .address-bar {{ background-color: var(--bg-color); border-radius: 6px; padding: 5px 10px; width: 100%; color: var(--secondary-text-color); font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
            .stream-layout {{ display: flex; flex-grow: 1; min-height: 0; }}
            .video-player {{ flex-grow: 1; background-color: #000; display: flex; justify-content: center; align-items: center; }}
            .video-player img {{ width: 100%; height: 100%; object-fit: cover; }}
            .stream-info {{ padding: 20px; background-color: #1f1f23; border-top: 1px solid var(--border-color); flex-shrink: 0; }}
            .stream-title {{ font-size: 22px; font-weight: 700; margin: 0 0 10px 0; }}
            .streamer-info {{ display: flex; align-items: center; gap: 12px; }}
            .streamer-pic {{ width: 40px; height: 40px; border-radius: 50%; }}
            .streamer-name {{ font-size: 16px; font-weight: 600; }}
            .chat-window {{ width: 320px; background-color: #1f1f23; display: flex; flex-direction: column; flex-shrink: 0; border-left: 1px solid var(--border-color); }}
            .chat-header {{ padding: 15px; font-weight: 600; border-bottom: 1px solid var(--border-color); text-align: center; flex-shrink: 0; }}
            .chat-messages {{ flex-grow: 1; padding: 15px; overflow-y: auto; }}
            .chat-message {{ margin-bottom: 15px; line-height: 1.5; word-wrap: break-word; }}
            .chat-username {{ font-weight: 700; color: var(--accent-color-light); }}
            .chat-emote {{ height: 28px; vertical-align: middle; margin-left: 5px; }}
        </style>
    </head>
    <body>
        <div class="browser-window">
            <header class="browser-header"><div class="address-bar">https://rplay.live/yahwa</div></header>
            <main class="stream-layout">
                <div class="video-player">{image_html}</div>
                <div class="chat-window">
                    <div class="chat-header">채팅</div>
                    <div class="chat-messages">{chats_html}</div>
                </div>
            </main>
            <footer class="stream-info">
                <h1 class="stream-title">{title}</h1>
                <div class="streamer-info">
                    <img src="https://placehold.co/40x40/efeff1/18181b?text=Y" alt="스트리머 프로필" class="streamer-pic">
                    <span class="streamer-name">야화</span>
                </div>
            </footer>
        </div>
    </body>
    </html>
    """

@app.route('/make_stream')
def make_stream():
    try:
        # 1. 단일 이미지 파라미터 'i' 파싱
        image_name = request.args.get('i')
        image_url = f"{IMAGE_BASE_URL}{image_name}.png" if image_name else ""

        # 2. 방송 제목 파라미터 't' 파싱
        title = request.args.get('t') or '야화님 방송 중!'

        # 3. 전달받은 채팅 파라미터 파싱 (4개로 변경)
        user_chats = []
        for i in range(1, 5):
            user = request.args.get(f'c{i}u')
            text = request.args.get(f'c{i}t')
            if user and text:
                user_chats.append({'user': user, 'text': text, 'type': 'text'})
        
        # 4. 랜덤 이모티콘 채팅 생성 (유지)
        random_chats = []
        random_usernames = [
            "매일밤세우는기둥", "헐떡이는숨구멍", "야화전용방망이", "축축한손바닥", "가버렷홍콩열차",
            "사정없이쏜다", "뜨거워진아랫도리", "너의그곳을탐하리", "깊은곳까지느껴져", "흔들어줘요야화님",
            "쾌락의절정", "육체파리스너", "정복하고싶은입술", "땀으로샤워중", "질척이는밤",
            "맛보고싶어", "밤새도록격렬하게", "애타는혀놀림", "중심을잡아줘", "너의굴에들어가고싶어",
            "길들여줘요주인님", "야화의개", "복종하는노예1호", "오늘밤은내가주인", "당신의펫",
            "목줄채워줘", "은밀한계약관계", "명령을기다립니다", "지배당하고싶어", "너는내소유물",
            "저를벌해주세요", "주인님의장난감", "밤의지배자", "발밑에꿇겠습니다", "당신만의암캐",
            "금단의주종관계", "나를조련해봐", "비밀의정원사", "꺾고싶은꽃", "야화의가축",
            "팬티내리고시청중", "니목소리가내최음제", "돈으로살수있다면", "육성으로터져버렷", "모니터에박을기세",
            "지금만나러갑니다", "이성을잃은정자", "욕정이가득한밤", "제발한번만", "정액도둑",
            "더럽혀줘", "엄마미안해", "통장비번알려줄게", "오늘은너로정했다", "내안에가득채워",
            "싸고싶다", "이미한발뺐음", "머릿속은온통섹스", "오디오만듣고상상중", "휴지끈길이세계챔피언"
        ]
        for _ in range(random.randint(5, 12)):
            user = random.choice(random_usernames)
            emote_num = random.randint(1, 12)
            emote_url = f"{IMAGE_BASE_URL}YA{emote_num}.png"
            random_chats.append({'user': user, 'emote_url': emote_url, 'type': 'emote'})

        # 5. 두 채팅 목록을 합치고 순서 섞기
        all_chats = user_chats + random_chats
        random.shuffle(all_chats)
        
        # 6. HTML 생성 및 Playwright 렌더링
        html_content = create_stream_html_template(title, image_url, all_chats)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_viewport_size({"width": 1024, "height": 768}) # 4:3 비율
            page.set_content(html_content, wait_until="networkidle")
            screenshot_bytes = page.screenshot(type='png')
            browser.close()

        response = make_response(send_file(io.BytesIO(screenshot_bytes), mimetype='image/png'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    except Exception as e:
        return f"Error in /make_stream: {e}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

