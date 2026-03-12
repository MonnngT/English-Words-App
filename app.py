import streamlit as st
import pandas as pd
from gtts import gTTS
import io

st.set_page_config(page_title="在线单词本", page_icon="📚")
st.title("📚 专属背单词模块")

# 初始化状态
if 'word_index' not in st.session_state:
    st.session_state.word_index = 0
if 'show_answer' not in st.session_state:
    st.session_state.show_answer = False

# 加载整理好的单词数据
@st.cache_data
def load_data():
    # 读取你准备好的 CSV 文件
    return pd.read_csv("words.csv")

try:
    df_words = load_data()
    total_words = len(df_words)
except FileNotFoundError:
    st.error("找不到 words.csv 文件，请确保它与 app.py 在同一目录下。")
    st.stop()

# 云端发音函数
def play_audio(text):
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    st.audio(fp, format='audio/mp3')

# 侧边栏设置
with st.sidebar:
    st.header("⚙️ 学习设置")
    mode = st.radio("模式选择：", ["英译中 (遮挡中文)", "中译英 (遮挡英文)"])
    st.progress((st.session_state.word_index + 1) / total_words)
    st.write(f"当前进度: {st.session_state.word_index + 1} / {total_words}")

# 主体显示区域
current_word = df_words.iloc[st.session_state.word_index]
st.markdown("---")

if mode == "英译中 (遮挡中文)":
    st.header(f"🔤 {current_word['English']}")
    play_audio(current_word['English']) 
    
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
        play_audio(current_word['English']) 

st.markdown("---")

# 翻页按钮
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
