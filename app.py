import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os
import base64
import json
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components

# ================= 1. 页面配置与数据库连接 =================
st.set_page_config(page_title="AI 听力单词本-持久化版", page_icon="🎧", layout="centered")

# 连接到 Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_history = conn.read(ttl=0) 
except Exception as e:
    st.error("云端数据库连接尚未生效，请检查 Secrets。目前使用临时数据。")
    df_history = pd.DataFrame(columns=['English', 'Chinese'])

# ================= 2. 加载本地单词表 =================
@st.cache_data
def load_data():
    file_name = "words.csv" if os.path.exists("words.csv") else "word.csv"
    try:
        return pd.read_csv(file_name, encoding="utf-8-sig")
    except:
        return pd.read_csv(file_name, encoding="gbk")

try:
    df_source = load_data()
    total_words = len(df_source)
except:
    st.error("找不到单词本文件！请确保仓库里有 words.csv。")
    st.stop()

# 👇这里就是上一次被我误删的核心代码，现在补回来了！👇
WORDS_PER_UNIT = 20
total_units = (total_words + WORDS_PER_UNIT - 1) // WORDS_PER_UNIT
unit_options = [f"第 {i+1} 单元 ({i*WORDS_PER_UNIT + 1}-{min((i+1)*WORDS_PER_UNIT, total_words)})" for i in range(total_units)]

# ================= 3. 核心功能：渲染模块 =================
@st.cache_data(show_spinner=False)
def get_audio_b64(word, slow_mode):
    tts = gTTS(text=word, lang='en', slow=slow_mode)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    return base64.b64encode(fp.getvalue()).decode('utf-8')

def render_list(df_to_show, pause_sec, is_slow, show_en, show_zh):
    if df_to_show.empty:
        st.info("库里还没有单词。")
        return
    
    audio_words = df_to_show['English'].tolist()
    with st.spinner("正在加载音频..."):
        b64_audios = [get_audio_b64(w, is_slow) for w in audio_words]

    html_code = f"""
    <div style="font-family: sans-serif; padding: 15px; background-color: #f0f2f6; border-radius: 10px; text-align: center;">
        <button id="pBtn" style="width:100%; background:#ff4b4b; color:white; border:none; padding:12px; border-radius:6px; cursor:pointer; font-weight:bold;">
            🔊 开始连续播放 (停顿 {pause_sec}s)
        </button>
        <div id="st" style="margin-top:10px; font-weight:bold; color:#31333F;">准备就绪</div>
        <audio id="player"></audio>
    </div>
    <script>
        const ws = {json.dumps(audio_words)}; const as = {json.dumps(b64_audios)};
        let cur = 0; let playing = false; const p = document.getElementById('player');
        const b = document.getElementById('pBtn'); const s = document.getElementById('st');

        b.onclick = () => {{
            if(playing) {{ playing=false; b.innerText="▶️ 继续播放"; s.innerText="已暂停"; p.pause(); }}
            else {{ playing=true; b.innerText="⏸️ 暂停"; play(); }}
        }};

        function play() {{
            if(!playing || cur >= ws.length) return;
            s.innerText = "正在读: " + ws[cur];
            p.src = "data:audio/mp3;base64," + as[cur]; p.play();
            p.onended = () => {{
                cur++;
                if(cur < ws.length) {{
                    s.innerText = "思考中({pause_sec}s)...";
                    setTimeout(play, {pause_sec} * 1000);
                }} else {{ s.innerText="🎉 播放完毕"; playing=false; b.innerText="🔊 重新开始"; cur=0; }}
            }};
        }}
    </script>
    """
    components.html(html_code, height=130)

    for i, row in df_to_show.iterrows():
        en_word = str(row['English']).replace('<', '&lt;').replace('>', '&gt;')
        zh_word = str(row['Chinese']).replace('<', '&lt;').replace('>', '&gt;')
        en = f"<b>{en_word}</b>" if show_en else "<span style='color:#ccc;'>***</span>"
        zh = zh_word if show_zh else "<span style='color:#ccc;'>***</span>"
        tag = f"<audio controls src='data:audio/mp3;base64,{b64_audios[audio_words.index(row['English'])]}' style='width:140px;height:35px;'></audio>"
        st.markdown(f'<div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #eee;padding:10px 0;"><div style="flex:1;">{en}<br>{zh}</div><div style="flex:0 0 140px;">{tag}</div></div>', unsafe_allow_html=True)

# ================= 4. 侧边栏与页面逻辑 =================
with st.sidebar:
    mode = st.radio("模式：", ["📖 单元学习", "📚 历史复习库(永久保存)"])
    st.divider()
    show_en = st.checkbox("显示英文", value=True)
    show_zh = st.checkbox("显示中文", value=True)
    is_shuffle = st.toggle("乱序模式")
    pause_sec = st.slider("停顿时间", 1, 30, 2)
    is_slow = st.radio("语速", ["正常", "放慢"]) == "放慢"

if mode == "📖 单元学习":
    st.title("📖 单元学习")
    unit = st.selectbox("选择单元", unit_options)
    idx = unit_options.index(unit)
    df_unit = df_source.iloc[idx*WORDS_PER_UNIT : (idx+1)*WORDS_PER_UNIT].copy()

    if st.button("⭐ 永久存入云端复习库", type="primary", use_container_width=True):
        if 'English' not in df_history.columns:
            df_history = pd.DataFrame(columns=['English', 'Chinese'])
        updated_df = pd.concat([df_history, df_unit]).drop_duplicates(subset=['English'])
        conn.update(data=updated_df)
        st.success("已成功存入云端表格！永不丢失。")
        st.rerun()

    if is_shuffle: df_unit = df_unit.sample(frac=1).reset_index(drop=True)
    render_list(df_unit, pause_sec, is_slow, show_en, show_zh)

else:
    st.title("📚 历史复习库")
    st.caption(f"当前云端库中共存储了 {len(df_history)} 个单词")
    
    if st.button("🗑️ 彻底清空云端数据"):
        empty_df = pd.DataFrame(columns=['English', 'Chinese'])
        conn.update(data=empty_df)
        st.rerun()

    df_rev = df_history.copy()
    if is_shuffle and not df_rev.empty: df_rev = df_rev.sample(frac=1).reset_index(drop=True)
    render_list(df_rev, pause_sec, is_slow, show_en, show_zh)
