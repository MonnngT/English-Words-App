import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os
import base64
import json
import streamlit.components.v1 as components

# ================= 1. 页面与基础设置 =================
st.set_page_config(page_title="AI 听力单词本", page_icon="🎧", layout="centered")
st.title("🎧 单元听力单词本")

# ================= 2. 加载数据 =================
@st.cache_data
def load_data():
    file_name = "words.csv" if os.path.exists("words.csv") else "word.csv"
    try:
        return pd.read_csv(file_name, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(file_name, encoding="gbk")

try:
    df_words = load_data()
    total_words = len(df_words)
except FileNotFoundError:
    st.error("找不到单词本文件！请确保仓库里有 words.csv。")
    st.stop()

# ================= 3. 单元划分 =================
WORDS_PER_UNIT = 20
total_units = (total_words + WORDS_PER_UNIT - 1) // WORDS_PER_UNIT

unit_options = []
for i in range(total_units):
    start_idx = i * WORDS_PER_UNIT + 1
    end_idx = min((i + 1) * WORDS_PER_UNIT, total_words)
    unit_options.append(f"第 {i+1} 单元 ({start_idx}-{end_idx})")

# ================= 4. 侧边栏控制台 =================
with st.sidebar:
    st.header("⚙️ 学习控制台")
    
    selected_unit_str = st.selectbox("📚 选择单元：", unit_options)
    current_unit_idx = unit_options.index(selected_unit_str)
    
    st.markdown("---")
    st.subheader("👁️ 显隐与乱序")
    show_english = st.checkbox("显示英文 (English)", value=True)
    show_chinese = st.checkbox("显示中文 (释义)", value=True)
    
    is_shuffle = st.toggle("🔀 开启打乱顺序")
    if is_shuffle:
        if 'shuffle_seed' not in st.session_state:
            st.session_state.shuffle_seed = 42
        if st.button("🔄 换一种打乱方式"):
            st.session_state.shuffle_seed += 1

    if not show_english and not show_chinese:
        st.warning("请至少选择显示一种语言哦！")
        
    st.markdown("---")
    st.subheader("🔊 语音设置")
    speed_option = st.radio("选择单个词的朗读语速：", ["正常语速", "放慢发音 (Slow)"])
    is_slow_mode = (speed_option == "放慢发音 (Slow)")
    
    pause_seconds = st.slider("调节单词间停顿 (秒)：", min_value=1, max_value=30, value=15)

# ================= 5. 数据处理 =================
start_index = current_unit_idx * WORDS_PER_UNIT
end_index = min((current_unit_idx + 1) * WORDS_PER_UNIT, total_words)
df_unit = df_words.iloc[start_index:end_index].copy()

if is_shuffle:
    df_unit = df_unit.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)

# ================= 6. 终极智能前端播放器 =================
@st.cache_data(show_spinner=False)
def get_audio_b64_list(words_list, slow_mode):
    """将单词转化为 Base64 音频流发给网页前端"""
    b64_list = []
    for word in words_list:
        tts = gTTS(text=word, lang='en', slow=slow_mode)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        b64 = base64.b64encode(fp.getvalue()).decode('utf-8')
        b64_list.append(b64)
    return b64_list

@st.cache_data(show_spinner=False)
def generate_single_audio(word, slow_mode):
    tts = gTTS(text=word, lang='en', slow=slow_mode)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp.read()

st.markdown(f"### 当前：{selected_unit_str} {'(🔀 乱序模式)' if is_shuffle else ''}")
st.markdown("---")

audio_words = df_unit['English'].tolist()

with st.spinner("正在加载智能播放器..."):
    b64_audios = get_audio_b64_list(audio_words, is_slow_mode)

# 内嵌定制的 HTML+JS 播放器
html_code = f"""
<div style="font-family: sans-serif; padding: 15px; background-color: #f0f2f6; border-radius: 10px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
    <button id="playBtn" style="background-color: #ff4b4b; color: white; border: none; padding: 12px 24px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; transition: 0.3s;">
        🔊 开始播放本组英文 (精确停顿 {pause_seconds} 秒)
    </button>
    <button id="stopBtn" style="background-color: #666; color: white; border: none; padding: 8px 16px; font-size: 14px; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 10px; display: none;">
        ⏹ 停止播放
    </button>
    <div id="status" style="margin-top: 15px; font-size: 16px; color: #31333F; font-weight: bold;">
        等待播放...
    </div>
    <audio id="audioPlayer"></audio>
</div>

<script>
    const words = {json.dumps(audio_words)};
    const audios = {json.dumps(b64_audios)};
    const pauseTime = {pause_seconds} * 1000;
    
    let currentIndex = 0;
    let isPlaying = false;
    let timer = null;
    
    const player = document.getElementById('audioPlayer');
    const playBtn = document.getElementById('playBtn');
    const stopBtn = document.getElementById('stopBtn');
    const status = document.getElementById('status');
    
    function resetPlayer() {{
        isPlaying = false;
        currentIndex = 0;
        clearTimeout(timer);
        player.pause();
        playBtn.style.display = "block";
        stopBtn.style.display = "none";
        status.innerText = "播放已停止";
        status.style.color = "#31333F";
    }}

    playBtn.onclick = () => {{
        isPlaying = true;
        currentIndex = 0;
        playBtn.style.display = "none";
        stopBtn.style.display = "block";
        playNext();
    }};
    
    stopBtn.onclick = resetPlayer;
    
    function playNext() {{
        if (!isPlaying) return;
        
        if (currentIndex < words.length) {{
            status.innerText = "🔊 正在朗读: " + words[currentIndex];
            status.style.color = "#ff4b4b";
            player.src = "data:audio/mp3;base64," + audios[currentIndex];
            player.play();
            
            player.onended = () => {{
                if (!isPlaying) return;
                currentIndex++;
                if (currentIndex < words.length) {{
                    status.innerText = "⏳ 思考中 (" + {pause_seconds} + "秒)...";
                    status.style.color = "#0083B8";
                    timer = setTimeout(playNext, pauseTime);
                }} else {{
                    resetPlayer();
                    status.innerText = "🎉 本组播放完毕！";
                    status.style.color = "#28a745";
                }}
            }};
        }}
    }}
</script>
"""

# 将播放器嵌入页面
components.html(html_code, height=160)

single_audio_player = st.empty()
st.markdown("---")

# ================= 7. 列表渲染 (UI 展示) =================
col_btn, col_en, col_zh = st.columns([1, 4, 4])
with col_btn:
    st.markdown("**发音**")
with col_en:
    st.markdown("**英文单词**" if show_english else "")
with col_zh:
    st.markdown("**中文释义**" if show_chinese else "")

st.divider()

for idx, row in df_unit.iterrows():
    col_btn, col_en, col_zh = st.columns([1, 4, 4])
    
    with col_btn:
        if st.button("🔊", key=f"btn_play_{current_unit_idx}_{idx}", help=f"朗读 {row['English']}"):
            single_bytes = generate_single_audio(row['English'], is_slow_mode)
            single_audio_player.audio(single_bytes, format='audio/mp3', autoplay=True)
            
    with col_en:
        if show_english:
            st.markdown(f"**{row['English']}**")
            
    with col_zh:
        if show_chinese:
            st.markdown(f"{row['Chinese']}")
            
    st.divider()

st.caption("💡 提示：点击上方的红色大按钮开启连读，在下方列表中点击小喇叭可单独发音。")
