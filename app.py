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
    
    pause_seconds = st.slider("调节单词间停顿 (秒)：", min_value=1, max_value=30, value=2)

# ================= 5. 数据处理 =================
start_index = current_unit_idx * WORDS_PER_UNIT
end_index = min((current_unit_idx + 1) * WORDS_PER_UNIT, total_words)
df_unit = df_words.iloc[start_index:end_index].copy()

if is_shuffle:
    df_unit = df_unit.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)

# ================= 6. 核心：一次性生成所有音频 =================
@st.cache_data(show_spinner=False)
def get_all_audios(words_list, slow_mode):
    b64_list = []
    for word in words_list:
        tts = gTTS(text=word, lang='en', slow=slow_mode)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        audio_data = fp.getvalue()
        b64_list.append(base64.b64encode(audio_data).decode('utf-8'))
    return b64_list

st.markdown(f"### 当前：{selected_unit_str} {'(🔀 乱序模式)' if is_shuffle else ''}")
st.markdown("---")

audio_words = df_unit['English'].tolist()

with st.spinner("正在加载智能音频组件..."):
    b64_audios = get_all_audios(audio_words, is_slow_mode)

# ================= 7. 顶部连播控制台 (隐藏式的独立播放器) =================
html_code = f"""
<div style="font-family: sans-serif; padding: 15px; background-color: #f0f2f6; border-radius: 10px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
    
    <div style="display: flex; gap: 10px; width: 100%;">
        <button id="playBtn" style="flex: 1; background-color: #ff4b4b; color: white; border: none; padding: 12px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.3s; -webkit-tap-highlight-color: transparent;">
            🔊 开始连读磨耳朵 (精确停顿 {pause_seconds} 秒)
        </button>
        <button id="pauseBtn" style="flex: 1; display: none; background-color: #ffc107; color: #333; border: none; padding: 12px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.3s; -webkit-tap-highlight-color: transparent;">
            ⏸️ 暂停播放
        </button>
        <button id="resetBtn" style="flex: 1; display: none; background-color: #666; color: white; border: none; padding: 12px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.3s; -webkit-tap-highlight-color: transparent;">
            🔄 从头重播
        </button>
    </div>

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
    let isGap = false; 
    let timer = null;
    
    const player = document.getElementById('audioPlayer');
    const playBtn = document.getElementById('playBtn');
    const pauseBtn = document.getElementById('pauseBtn');
    const resetBtn = document.getElementById('resetBtn');
    const status = document.getElementById('status');
    
    function resetAll() {{
        isPlaying = false;
        isGap = false;
        currentIndex = 0;
        clearTimeout(timer);
        player.pause();
        player.src = "";
        
        playBtn.innerText = "🔊 开始连读磨耳朵 (精确停顿 {pause_seconds} 秒)";
        playBtn.style.display = "block";
        pauseBtn.style.display = "none";
        resetBtn.style.display = "none";
        
        status.innerText = "等待播放...";
        status.style.color = "#31333F";
    }}

    playBtn.onclick = () => {{
        isPlaying = true;
        playBtn.style.display = "none";
        pauseBtn.style.display = "block";
        resetBtn.style.display = "block";
        
        if (currentIndex >= words.length) {{
            currentIndex = 0;
        }}
        
        if (isGap) {{
            isGap = false;
            playNext();
        }} else if (player.src && player.currentTime > 0 && !player.ended) {{
            status.innerText = "🔊 正在朗读: " + words[currentIndex];
            status.style.color = "#ff4b4b";
            player.play();
        }} else {{
            playNext();
        }}
    }};
    
    pauseBtn.onclick = () => {{
        isPlaying = false;
        playBtn.innerText = "▶️ 继续播放";
        playBtn.style.display = "block";
        pauseBtn.style.display = "none";
        
        player.pause();
        clearTimeout(timer);
        
        status.innerText = "⏸️ 已暂停: " + (currentIndex < words.length ? words[currentIndex] : "");
        status.style.color = "#888";
    }};
    
    resetBtn.onclick = resetAll;
    
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
                    isGap = true;
                    status.innerText = "⏳ 思考中 (" + {pause_seconds} + "秒)...";
                    status.style.color = "#0083B8";
                    timer = setTimeout(() => {{
                        isGap = false;
                        playNext();
                    }}, pauseTime);
                }} else {{
                    resetAll();
                    status.innerText = "🎉 本组播放完毕！";
                    status.style.color = "#28a745";
                }}
            }};
        }}
    }}
</script>
"""

components.html(html_code, height=160)
st.markdown("---")

# ================= 8. 列表渲染 (防崩溃移动端专属排版) =================
# 核心修复：逐行渲染！避免生成超大文本导致报错

for loop_idx, (idx, row) in enumerate(df_unit.iterrows()):
    en_word = str(row['English']).replace('<', '&lt;').replace('>', '&gt;')
    zh_word = str(row['Chinese']).replace('<', '&lt;').replace('>', '&gt;')
    
    # 将原本挤在一行的英文和中文，变成精美的“上下排列”
    en_text = f"<div style='font-size: 18px; font-weight: bold; color: #2C3E50;'>{en_word}</div>" if show_english else "<div style='color:#ccc;'>[英文已遮挡]</div>"
    zh_text = f"<div style='font-size: 14px; color: #7F8C8D; margin-top: 4px;'>{zh_word}</div>" if show_chinese else "<div style='color:#ccc; margin-top: 4px;'>[中文已遮挡]</div>"
    
    # 召唤不受任何手机浏览器阻碍的原生音频控件
    audio_tag = f"<audio controls src='data:audio/mp3;base64,{b64_audios[loop_idx]}' style='width: 140px; height: 35px; outline: none;'></audio>"
    
    # “左侧单词释义，右侧播放器” 的完美二维排版
    row_html = f"""
    <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #EAECEE; padding: 12px 0;">
        <div style="flex: 1; min-width: 0; padding-right: 15px; word-wrap: break-word;">
            {en_text}
            {zh_text}
        </div>
        <div style="flex: 0 0 140px; text-align: right;">
            {audio_tag}
        </div>
    </div>
    """
    
    # 一行一行地安全输出，永不崩溃
    st.markdown(row_html, unsafe_allow_html=True)

st.caption("📱 移动端防崩溃护眼版：左右双结构排版，完美适配各类手机屏幕，顺畅发音！")
