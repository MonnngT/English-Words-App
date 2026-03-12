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

# 生成单元列表 (例如: "第 1 单元 (1-20)", "第 2 单元 (21-40)")
unit_options = []
for i in range(total_units):
    start_idx = i * WORDS_PER_UNIT + 1
    end_idx = min((i + 1) * WORDS_PER_UNIT, total_words)
    unit_options.append(f"第 {i+1} 单元 ({start_idx}-{end_idx})")

# ================= 4. 侧边栏控制台 =================
with st.sidebar:
    st.header("⚙️ 学习控制台")
    
    # 选择单元
    selected_unit_str = st.selectbox("📚 选择要学习的单元：", unit_options)
    # 提取当前选择的单元索引 (0-based)
    current_unit_idx = unit_options.index(selected_unit_str)
    
    st.markdown("---")
    st.subheader("👁️ 显示设置")
    show_english = st.checkbox("显示英文 (English)", value=True)
    show_chinese = st.checkbox("显示中文 (释义)", value=True)
    
    if not show_english and not show_chinese:
        st.warning("请至少选择显示一种语言哦！")

# ================= 5. 提取当前单元的单词 =================
start_index = current_unit_idx * WORDS_PER_UNIT
end_index = min((current_unit_idx + 1) * WORDS_PER_UNIT, total_words)
df_unit = df_words.iloc[start_index:end_index]

# ================= 6. 一键连读音频生成 =================
@st.cache_data(show_spinner=False)
def generate_unit_audio(text_to_read, lang):
    """缓存生成的音频，避免重复点击时重复生成"""
    tts = gTTS(text=text_to_read, lang=lang)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp.read()

st.markdown(f"### 当前：{selected_unit_str}")

# 生成供朗读的文本
if show_english or show_chinese:
    audio_text = ""
    for _, row in df_unit.iterrows():
        if show_english:
            audio_text += f"{row['English']}. "
        if show_chinese:
            # 加上逗号是为了让语音引擎稍微停顿一下
            audio_text += f"{row['Chinese']}, " 
        audio_text += "。 " # 每个单词结束后加句号停顿

    # 播放按钮区域
    st.markdown("---")
    
    # 判断发音语言：如果只显英文，就用纯正英文发音；如果有中文，用兼容发音
    tts_lang = 'en' if (show_english and not show_chinese) else 'zh-CN'
    
    if st.button("🔊 生成并播放本页全部单词 (可后台播放)"):
        with st.spinner("正在合成高音质音频，请稍等几秒..."):
            audio_bytes = generate_unit_audio(audio_text, tts_lang)
            st.audio(audio_bytes, format='audio/mp3', autoplay=True)
            st.success("合成完毕！点击播放器即可开始听力，你可以最小化网页挂在后台了。")

st.markdown("---")

# ================= 7. 列表渲染 (UI 展示) =================
# 表头
col1, col2 = st.columns(2)
with col1:
    st.markdown("**英文单词**" if show_english else "")
with col2:
    st.markdown("**中文释义**" if show_chinese else "")

st.divider()

# 逐行显示单词
for idx, row in df_unit.iterrows():
    col1, col2 = st.columns(2)
    with col1:
        if show_english:
            st.markdown(f"**{row['English']}**")
    with col2:
        if show_chinese:
            st.markdown(f"{row['Chinese']}")
    st.divider()

# ================= 8. 底部快捷翻页 =================
col_prev, col_mid, col_next = st.columns([1, 2, 1])
# 由于 Streamlit 的 selectbox 限制，底部按钮用来提示用户去侧边栏切换
with col_mid:
    st.caption("💡 提示：请在左侧边栏切换上下单元")
