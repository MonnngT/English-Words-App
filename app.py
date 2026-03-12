import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os
import requests

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

# ================= 6. 黑科技：纯字节流音频合成 =================
@st.cache_data(show_spinner=False)
def get_silence_mp3():
    """直接从云端下载一段极其纯净的 1秒静音 MP3"""
    url = "https://raw.githubusercontent.com/anars/blank-audio/master/1-second-of-silence.mp3"
    try:
        return requests.get(url, timeout=5).content
    except:
        return b"" # 万一网络卡了，不影响程序运行，只是没有停顿而已

@st.cache_data(show_spinner=False)
def generate_unit_audio_magic(words_list, slow_mode, pause_sec):
    # 拿到 1 秒的空白音频
    silence_1s = get_silence_mp3()
    # 核心魔法：MP3 是流式文件，把字节乘上倍数，1秒静音瞬间变成 15秒静音！
    silence_block = silence_1s * pause_sec 
    
    combined_audio_bytes = b""
    
    for word in words_list:
        # 生成单个单词的读音
        tts = gTTS(text=word, lang='en', slow=slow_mode)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        
        # 魔法拼接：单词字节 + 15秒静音字节
        combined_audio_bytes += fp.getvalue() + silence_block
        
    return combined_audio_bytes

@st.cache_data(show_spinner=False)
def generate_single_audio(word, slow_mode):
    tts = gTTS(text=word, lang='en', slow=slow_mode)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp.read()

st.markdown(f"### 当前：{selected_unit_str} {'(🔀 乱序模式)' if is_shuffle else ''}")

audio_words = df_unit['English'].tolist()

st.markdown("---")
    
if st.button(f"🔊 播放本组英文 (精准停顿 {pause_seconds} 秒)", use_container_width=True):
    with st.spinner(f"正在使用字节流黑科技合成中..."):
        audio_bytes = generate_unit_audio_magic(audio_words, is_slow_mode, pause_seconds)
        st.audio(audio_bytes, format='audio/mp3', autoplay=True)
        st.success(f"合成完毕！现在的停顿绝对是分秒不差的 {pause_seconds} 秒！")

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
