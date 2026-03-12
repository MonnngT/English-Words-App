import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os
import base64
import json
import requests
import streamlit.components.v1 as components

# ================= 1. 页面与基础设置 =================
st.set_page_config(page_title="AI 听力单词本", page_icon="🎧", layout="wide")
st.title("🎧 单元听力单词本 (智能例句版)")

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

# ================= 3. 智能例句获取 =================
@st.cache_data(show_spinner=False)
def get_example_sentence(word):
    """通过免费的词典 API 自动抓取地道例句"""
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            for meaning in data[0].get('meanings', []):
                for defn in meaning.get('definitions', []):
                    if 'example' in defn:
                        # 清理可能存在的 html 标签
                        sentence = defn['example'].replace('<b>', '').replace('</b>', '')
                        # 确保以句号结尾，让语音语调自然
                        if not sentence.endswith(('.', '!', '?')):
                            sentence += '.'
                        return sentence
    except:
        pass
    return "" # 如果抓取失败或没找到例句，返回空

# ================= 4. 单元划分 =================
WORDS_PER_UNIT = 20
total_units = (total_words + WORDS_PER_UNIT - 1) // WORDS_PER_UNIT

unit_options = []
for i in range(total_units):
    start_idx = i * WORDS_PER_UNIT + 1
    end_idx = min((i + 1) * WORDS_PER_UNIT, total_words)
    unit_options.append(f"第 {i+1} 单元 ({start_idx}-{end_idx})")

# ================= 5. 侧边栏控制台 =================
with st.sidebar:
    st.header("⚙️ 学习控制台")
    
    selected_unit_str = st.selectbox("📚 选择单元：", unit_options)
    current_unit_idx = unit_options.index(selected_unit_str)
    
    st.markdown("---")
    st.subheader("👁️ 视觉显示设置")
    show_english = st.checkbox("显示英文 (English)", value=True)
    show_chinese = st.checkbox("显示中文 (释义)", value=True)
    show_sentence = st.checkbox("📝 列表中显示例句", value=True)
    
    is_shuffle = st.toggle("🔀 开启打乱顺序")
    if is_shuffle:
        if 'shuffle_seed' not in st.session_state:
            st.session_state.shuffle_seed = 42
        if st.button("🔄 换一种打乱方式"):
            st.session_state.shuffle_seed += 1
        
    st.markdown("---")
    st.subheader("🔊 听力发音设置")
    # 核心新功能：是否连为例句一起读
    read_sentence = st.checkbox("💬 朗读时包含例句", value=False, help="开启后，AI 读完单词会紧接着朗读一遍例句。")
    
    speed_option = st.radio("朗读语速：", ["正常语速", "放慢发音 (Slow)"])
    is_slow_mode = (speed_option == "放慢发音 (Slow)")
    pause_seconds = st.slider("单词/例句 结束后的停顿 (秒)：", min_value=1, max_value=30, value=15)

# ================= 6. 数据处理 =================
start_index = current_unit_idx * WORDS_PER_UNIT
end_index = min((current_unit_idx + 1) * WORDS_PER_UNIT, total_words)
df_unit = df_words.iloc[start_index:end_index].copy()

if is_shuffle:
    df_unit = df_unit.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)

audio_words = df_unit['English'].tolist()

# ================= 7. 终极智能前端播放器 =================
@st.cache_data(show_spinner=False)
def get_audio_b64_list(words_list, slow_mode, include_sentence):
    b64_list = []
    for word in words_list:
        text_to_read = word
        # 如果用户选择了朗读例句，并且该单词成功抓取到了例句
        if include_sentence:
            sentence = get_example_sentence(word)
            if sentence:
                text_to_read = f"{word}. {sentence}" # 拼在一起读
                
        tts = gTTS(text=text_to_read, lang='en', slow=slow_mode)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        b64 = base64.b64encode(fp.getvalue()).decode('utf-8')
        b64_list.append(b64)
    return b64_list

@st.cache_data(show_spinner=False)
def generate_single_audio(word, slow_mode, include_sentence):
    text_to_read = word
    if include_sentence:
        sentence = get_example_sentence(word)
        if sentence:
            text_to_read = f"{word}. {sentence}"
            
    tts = gTTS(text=text_to_read, lang='en', slow=slow_mode)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp.read()

st.markdown(f"### 当前：{selected_unit_str} {'(🔀 乱序模式)' if is_shuffle else ''}")
st.markdown("---")

with st.spinner("正在智能抓取地道例句并生成高音质音频，请稍等..."):
    b64_audios = get_audio_b64_list(audio_words, is_slow_mode, read_sentence)

# 内嵌定制的 HTML+JS 播放器
html_code = f"""
<div style="font-family: sans-serif; padding: 15px; background-color: #f0f2f6; border-radius: 10px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
    <button id="playBtn" style="background-color: #ff4b4b; color: white; border: none; padding: 12px 24px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; transition: 0.3s;">
        🔊 开始连续播放本页内容 (间隔 {pause_seconds} 秒)
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

components.html(html_code, height=160)
single_audio_player = st.empty()
st.markdown("---")

# ================= 8. 列表渲染 (UI 展示) =================
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
    
    # 动态抓取当前单词的例句
    word_sentence = get_example_sentence(row['English']) if show_sentence else ""
    
    with col_btn:
        # 单点发音时，同样受“是否朗读例句”控制
        if st.button("🔊", key=f"btn_play_{current_unit_idx}_{idx}", help=f"朗读 {row['English']}"):
            single_bytes = generate_single_audio(row['English'], is_slow_mode, read_sentence)
            single_audio_player.audio(single_bytes, format='audio/mp3', autoplay=True)
            
    with col_en:
        if show_english:
            st.markdown(f"**{row['English']}**")
            # 如果抓到了例句且用户允许显示，则以灰色小字附在单词下方
            if show_sentence and word_sentence:
                st.caption(f"📝 *{word_sentence}*")
            
    with col_zh:
        if show_chinese:
            st.markdown(f"{row['Chinese']}")
            
    st.divider()

st.caption("💡 提示：所有例句均通过网络实时免费获取。如果部分单词没有显示例句，说明在线词典中暂无该词的简易例句。")
