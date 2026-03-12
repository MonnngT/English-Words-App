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

# ================= 3. 单元划分逻辑 =================
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
    
    selected_unit_str = st.selectbox("📚 选择要学习的单元：", unit_options)
    current_unit_idx = unit_options.index(selected_unit_str)
    
    st.markdown("---")
    st.subheader("👁️ 显示与排序")
    show_english = st.checkbox("显示英文 (English)", value=True)
    show_chinese = st.checkbox("显示中文 (释义)", value=True)
    
    # 新增：打乱顺序开关
    is_shuffle = st.toggle("🔀 开启打乱顺序")
    if is_shuffle:
        if 'shuffle_seed' not in st.session_state:
            st.session_state.shuffle_seed = 42
        # 提供一个按钮，如果觉得这遍乱序背熟了，可以换一种乱序方式
        if st.button("🔄 换一种打乱方式"):
            st.session_state.shuffle_seed += 1

    if not show_english and not show_chinese:
        st.warning("请至少选择显示一种语言哦！")

# ================= 5. 提取并处理当前单元的数据 =================
start_index = current_unit_idx * WORDS_PER_UNIT
end_index = min((current_unit_idx + 1) * WORDS_PER_UNIT, total_words)
# 复制一份当前单元的数据，避免修改原始数据
df_unit = df_words.iloc[start_index:end_index].copy()

# 如果开启了乱序，对当前这 20 个单词进行重新洗牌
if is_shuffle:
    df_unit = df_unit.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)

# ================= 6. 一键连读音频生成 (纯英文优化版) =================
@st.cache_data(show_spinner=False)
def generate_unit_audio(text_to_read):
    # 固定使用英文引擎，去掉了中文切换
    tts = gTTS(text=text_to_read, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp.read()

st.markdown(f"### 当前：{selected_unit_str} {'(🔀 乱序模式)' if is_shuffle else ''}")

# 优化发音逻辑：只提取英文，并且用逗号分隔，让它读起来节奏更轻快连贯
audio_text = ", ".join(df_unit['English'].tolist())

st.markdown("---")
    
if st.button("🔊 播放英文音频 (连续朗读)"):
    with st.spinner("正在光速合成音频，马上就好..."):
        audio_bytes = generate_unit_audio(audio_text)
        st.audio(audio_bytes, format='audio/mp3', autoplay=True)
        st.success("合成完毕！音频生成后不消耗流量，可以直接后台挂机听啦。")

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

st.caption("💡 提示：请在左侧边栏切换上下单元")
