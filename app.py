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

# ================= 6. 核心：一次性生成双格式音频 =================
# 一次性把音频生成好，供上方播放器和下方列表同时调用
@st.cache_data(show_spinner=False)
def get_all_audios(words_list, slow_mode):
    b64_list = []
    bytes_list = []
    for word in words_list:
        tts = gTTS(text=word, lang='en', slow=slow_mode)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        audio_data = fp.getvalue()
        
        bytes_list.append(audio_data)  # 供原生播放器使用
        b64_list.append(base64.b64encode(audio_data).decode('utf-8')) # 供网页 JS 使用
        
    return b64_list, bytes_list

st.markdown(f"### 当前：{selected_unit_str} {'(🔀 乱序模式)' if is_shuffle else ''}")
st.markdown("---")

audio_words = df_unit['English'].tolist()

with st.spinner("正在加载音频数据..."):
    b64_audios, bytes_audios = get_all_audios(audio_words, is_slow_mode)

# ================= 7. 顶部连播控制台 (依然保持前端智能连读) =================
html_code = f"""
<div style="font-family: sans-serif; padding: 15px; background-color: #f0f2f6; border-radius: 10px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
    
    <div style="display: flex; gap: 10px; width: 100%;">
        <button id="playBtn" style="flex: 1; background-color: #ff4b4b; color: white; border: none; padding: 12px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.3s; -webkit-tap-highlight-color: transparent;">
            🔊 开始播放本组英文 (精确停顿 {pause_seconds} 秒)
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
        
        playBtn.innerText = "🔊 开始播放本组英文 (精确停顿 {pause_seconds} 秒)";
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

# ================= 8. 列表渲染 (手机端无敌适配版) =================
# 调整列宽比例，给原生播放器留出更舒适的空间
col_en, col_zh, col_aud = st.columns([3, 3, 4])
with col_en:
    st.markdown("**英文单词**" if show_english else "")
with col_zh:
    st.markdown("**中文释义**" if show_chinese else "")
with col_aud:
    st.markdown("**单点发音**")

st.divider()

for loop_idx, (idx, row) in enumerate(df_unit.iterrows()):
    col_en, col_zh, col_aud = st.columns([3, 3, 4])
    
    with col_en:
        if show_english:
            # 加入 padding-top 完美对齐右侧播放器的高度
            st.markdown(f"<div style='padding-top: 15px; font-weight: bold; font-size: 16px;'>{row['English']}</div>", unsafe_allow_html=True)
            
    with col_zh:
        if show_chinese:
            st.markdown(f"<div style='padding-top: 15px;'>{row['Chinese']}</div>", unsafe_allow_html=True)
            
    with col_aud:
        # 终极方案：使用 Streamlit 官方原生播放控件 st.audio
        # 手机浏览器绝不会拦截系统原生的播放器控件！
        st.audio(bytes_audios[loop_idx], format='audio/mp3')
            
    st.divider()

st.caption("📱 移动端防吞音版：列表已全面换装手机系统级原生音频控件，点多少次响多少次，无视一切浏览器拦截限制！")
