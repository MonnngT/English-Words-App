import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os

# ================= 1. 页面与状态初始化 =================
st.set_page_config(page_title="AI 单词本", page_icon="📚")
st.title("📚 专属背单词模块")

# 初始化 Session State，记录进度和遮挡状态
if 'word_index' not in st.session_state:
    st.session_state.word_index = 0
if 'show_answer' not in st.session_state:
    st.session_state.show_answer = False

# ================= 2. 加载词汇表 (带多重保险) =================
@st.cache_data
def load_data():
    # 自动识别文件名：优先找 words.csv，找不到就找 word.csv
    file_name = "words.csv" if os.path.exists("words.csv") else "word.csv"
    
    try:
        # 尝试用 utf-8-sig 读取 (能自动过滤 Windows 系统的隐藏字符)
        return pd.read_csv(file_name, encoding="utf-8-sig")
    except UnicodeDecodeError:
        # 如果报错，自动切换为 Windows 常用的 gbk 编码
        return pd.read_csv(file_name, encoding="gbk")

# 尝试加载数据，拦截文件不存在的错误
try:
    df_words = load_data()
    total_words = len(df_words)
except FileNotFoundError:
    st.error("找不到单词本文件！请确保你的 GitHub 仓库里有 words.csv 或 word.csv 文件。")
    st.stop()

# ================= 3. 云端发音功能 =================
def play_audio(text):
    try:
        tts = gTTS(text=text, lang='en')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        st.audio(fp, format='audio/mp3')
    except Exception as e:
        st.error("语音加载失败，请检查网络或稍后重试。")

# ================= 4. 侧边栏与进度控制 =================
with st.sidebar:
    st.header("⚙️ 学习设置")
    mode = st.radio("模式选择：", ["英译中 (遮挡中文)", "中译英 (遮挡英文)"])
    
    # 防止替换文件后，旧进度超过新单词总数导致崩溃
    if st.session_state.word_index >= total_words:
        st.session_state.word_index = 0
        
    # 显示进度条
    st.progress((st.session_state.word_index + 1) / total_words)
    st.write(f"当前进度: {st.session_state.word_index + 1} / {total_words}")

# ================= 5. 主体交互逻辑 =================
current_word = df_words.iloc[st.session_state.word_index]
st.markdown("---")

if mode == "英译中 (遮挡中文)":
    st.header(f"🔤 {current_word['English']}")
    play_audio(current_word['English']) # 自动发音
    
    if st.button("👁️ 显示中文释义", use_container_width=True):
        st.session_state.show_answer = True
        
    if st.session_state.show_answer:
        st.success(f"💡 释义：{current_word['Chinese']}")

elif mode == "中译英 (遮挡英文)":
    st.header(f"🇨🇳 {current_word['Chinese']}")
    
    if st.button("👁️ 显示英文单词", use_container_width=True):
        st.session_state.show_answer = True
        
    if st.session_state.show_answer:
        st.success(f"💡 单词：{current_word['English']}")
        play_audio(current_word['English']) # 显示答案后发音

st.markdown("---")

# ================= 6. 翻页控制 =================
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("⬅️ 上一个"):
        if st.session_state.word_index > 0:
            st.session_state.word_index -= 1
            st.session_state.show_answer = False
            st.rerun()

with col3:
    if st.button("下一个 ➡️"):
        if st.session_state.word_index < total_words - 1:
            st.session_state.word_index += 1
            st.session_state.show_answer = False
            st.rerun()
