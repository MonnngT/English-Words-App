import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os

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
    st.error("找不到单词本文件！请确保你的 GitHub 仓库里有 words.csv 或 word.csv 文件。")
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
    st.subheader("🔊 语速设置")
    speed_option = st.radio("选择单个词的朗读语速：", ["正常语速", "放慢发音 (Slow)"])
    is_slow_mode = (speed_option == "放慢发音 (Slow)")

# ================= 5. 数据处理 =================
start_index = current_unit_idx * WORDS_PER_UNIT
end_index = min((current_unit_idx + 1) * WORDS_PER_UNIT, total_words)
df_unit = df_words.iloc[start_index:end_index].copy()

if is_shuffle:
    df_unit = df_unit.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)

# ================= 6. 音频生成 =================
@st.cache_data(show_spinner=False)
def generate_unit_audio(text_to_read, slow_mode):
    tts = gTTS(text=text_to_read, lang='en', slow=slow_mode)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp.read()

st.markdown(f"### 当前：{selected_unit_str} {'(🔀 乱序模式)' if is_shuffle else ''}")

# 核心修改点：叠加 3 个 " . \n"！
# 这样能成功欺骗 gTTS 引擎，强行把单词之间的停顿拉长到 2~3 秒钟
separator = " . \n . \n . \n"
audio_text = separator.join(df_unit['English'].tolist()) + separator

st.markdown("---")
    
if st.button("🔊 播放本组英文 (超长停顿 2~3 秒)"):
    with st.spinner("正在生成音频..."):
        audio_bytes = generate_unit_audio(audio_text, is_slow_mode)
        st.audio(audio_bytes, format='audio/mp3', autoplay=True)
        st.success("合成完毕！现在每个单词之间有非常充足的思考时间。")

st.markdown("---")

# ================= 7. 列表渲染 (UI 展示) =================
col1, col2 = st.columns(2)
with col1:
    st.markdown("**英文单词**" if show_english else "")
with col2:
    st.markdown("**中文释义**" if show_chinese else "")

st.divider()

for idx, row in df_unit.iterrows():
    col1, col2 = st.columns(2)
    with col1:
        if show_english:
            st.markdown(f"**{row['English']}**")
    with col2:
        if show_chinese:
            st.markdown(f"{row['Chinese']}")
    st.divider()

st.caption("💡 提示：遇到长难词时，记得在左侧边栏开启“放慢发音 (Slow)”。")
