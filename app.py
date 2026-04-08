import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os
import base64
import json
import wave 
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components

# ================= 1. 初始化 =================
st.set_page_config(page_title="终极后台背单词", page_icon="🎧", layout="centered")

if 'shuffle_seed' not in st.session_state:
    st.session_state.shuffle_seed = 42

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_history = conn.read(ttl=0).dropna(subset=['English'])
    df_history['English'] = df_history['English'].astype(str).str.strip()
    df_history = df_history[df_history['English'] != '']
except:
    df_history = pd.DataFrame(columns=['English', 'Chinese', 'Unit_Name'])

# ================= 2. 数据加载 =================
@st.cache_data
def load_local():
    for f in ["words.csv", "word.csv"]:
        if os.path.exists(f):
            try: return pd.read_csv(f, encoding="utf-8-sig")
            except: return pd.read_csv(f, encoding="gbk")
    return pd.DataFrame()

df_source = load_local()
WORDS_PER_UNIT = 20
unit_options = [f"第 {i+1} 单元" for i in range((len(df_source)+19)//20)]

# ================= 3. 音频生成 =================
@st.cache_data(show_spinner=False)
def get_audio_b64(word, slow):
    tts = gTTS(text=str(word), lang='en', slow=slow)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    return base64.b64encode(fp.getvalue()).decode('utf-8')

@st.cache_data(show_spinner=False)
def generate_silence(sec):
    fp = io.BytesIO()
    with wave.open(fp, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b'\x00' * int(44100 * sec * 2))
    return "data:audio/wav;base64," + base64.b64encode(fp.getvalue()).decode('utf-8')

def render_list(df_to_show, pause_sec, is_slow, show_en, show_zh):
    audio_words = df_to_show['English'].astype(str).tolist()
    b64_audios = [get_audio_b64(w, is_slow) for w in audio_words]
    silence_uri = generate_silence(pause_sec)

    # 【终极 JS 逻辑】：增加 WakeLock 防止系统进入深度睡眠
    html_code = f"""
    <div style="padding:15px; background:#f0f2f6; border-radius:12px; text-align:center;">
        <button id="pBtn" style="width:100%; background:#ff4b4b; color:white; border:none; padding:15px; border-radius:8px; font-weight:bold; font-size:18px;">
            🔊 启动“不死鸟”后台播放
        </button>
        <div id="st" style="margin-top:10px; font-weight:bold;">准备就绪</div>
        <audio id="player" style="display:none;"></audio>
    </div>

    <script>
        const ws = {json.dumps(audio_words)};
        const as = {json.dumps(b64_audios)};
        const silence = "{silence_uri}";
        let cur = 0, playing = false, isGap = false, wakeLock = null;
        const p = document.getElementById('player'), b = document.getElementById('pBtn'), s = document.getElementById('st');

        // 请求屏幕常亮，防止系统杀掉后台
        async function requestWakeLock() {{
            try {{ if('wakeLock' in navigator) wakeLock = await navigator.wakeLock.request('screen'); }} catch(e) {{}}
        }}

        function syncMedia() {{
            if ('mediaSession' in navigator) {{
                navigator.mediaSession.metadata = new MediaMetadata({{
                    title: '背单词中 - ' + (ws[cur] || '结束'),
                    artist: '点击播放可强行续播',
                    artwork: [{{ src: 'https://cdn-icons-png.flaticon.com/512/3039/3039403.png', sizes: '512x512' }}]
                }});
            }}
        }}

        async function play() {{
            try {{ await p.play(); playing = true; b.innerText = "⏸️ 暂停"; requestWakeLock(); }} 
            catch(e) {{ s.innerText = "⚠️ 焦点被抢，请点按钮或通知栏恢复"; }}
        }}

        // 核心：每 1 秒心跳监测，一旦发现声音断了且不是手动暂停，立刻重连
        setInterval(() => {{
            if (playing && p.paused && !isGap) play();
        }}, 1000);

        b.onclick = () => {{
            if(playing) {{ playing=false; p.pause(); b.innerText="▶️ 继续"; }}
            else {{ playing=true; if(p.src) play(); else playNext(); }}
        }};

        function playNext() {{
            if(!playing) return;
            syncMedia();
            if(isGap) {{
                s.innerText = "⏳ 停顿中..."; p.src = silence; p.play();
                p.onended = () => {{ if(playing) {{ isGap = false; playNext(); }} }};
            }} else {{
                if(cur < ws.length) {{
                    s.innerText = "🔊 正在读: " + ws[cur];
                    p.src = "data:audio/mp3;base64," + as[cur]; p.play();
                    p.onended = () => {{ cur++; if(cur < ws.length) {{ isGap = true; playNext(); }} else {{ playing=false; cur=0; s.innerText="🎉 完！"; }} }};
                }}
            }}
        }}

        if ('mediaSession' in navigator) {{
            navigator.mediaSession.setActionHandler('play', play);
            navigator.mediaSession.setActionHandler('pause', () => {{ playing=false; p.pause(); }});
        }}
    </script>
    """
    components.html(html_code, height=160)

    for i, row in df_to_show.iterrows():
        en = f"<b>{row['English']}</b>" if show_en else "***"
        zh = row['Chinese'] if show_zh else "***"
        tag = f"<audio controls src='data:audio/mp3;base64,{b64_audios[audio_words.index(str(row['English']))]}' style='width:145px;height:35px;'></audio>"
        st.markdown(f'<div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #eee;padding:12px 0;"><div>{en}<br><small>{zh}</small></div>{tag}</div>', unsafe_allow_html=True)

# ================= 4. UI 逻辑 =================
with st.sidebar:
    nav = st.radio("导航", ["学习", "复习库"])
    show_en = st.checkbox("显英文", True); show_zh = st.checkbox("显中文", True)
    is_shuffle = st.toggle("乱序")
    if is_shuffle and st.button("🔄 换序"): st.session_state.shuffle_seed += 1
    pause = st.slider("停顿", 1, 15, 2)
    slow = st.checkbox("慢速")

if nav == "学习":
    st.title("📖 学习")
    u = st.selectbox("选择单元", unit_options)
    idx = unit_options.index(u)
    df = df_source.iloc[idx*20:(idx+1)*20].copy()
    if st.button("⭐ 存入云端"):
        new = pd.concat([df_history, df]).drop_duplicates('English')
        conn.update(data=new); st.success("已存"); st.rerun()
    if is_shuffle: df = df.sample(frac=1, random_state=st.session_state.shuffle_seed)
    render_list(df, pause, slow, show_en, show_zh)
else:
    st.title("📚 复习库")
    st.write(f"共 {len(df_history)} 词")
    if st.button("🗑️ 清空"): conn.update(data=pd.DataFrame(columns=['English','Chinese','Unit_Name'])); st.rerun()
    df = df_history.copy()
    if is_shuffle: df = df.sample(frac=1, random_state=st.session_state.shuffle_seed)
    render_list(df, pause, slow, show_en, show_zh)
