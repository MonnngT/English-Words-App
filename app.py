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

# 初始化历史记录存储 (使用 session_state 保证页面切换时不丢失)
if 'history_df' not in st.session_state:
    st.session_state.history_df = pd.DataFrame(columns=['English', 'Chinese'])

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

WORDS_PER_UNIT = 20
total_units = (total_words + WORDS_PER_UNIT - 1) // WORDS_PER_UNIT
unit_options = [f"第 {i+1} 单元 ({i*WORDS_PER_UNIT + 1}-{min((i+1)*WORDS_PER_UNIT, total_words)})" for i in range(total_units)]

# ================= 3. 核心：单词缓存机制 (极大提升历史记录加载速度) =================
@st.cache_data(show_spinner=False)
def get_single_audio_b64(word, slow_mode):
    """将单个单词的发音缓存，历史库中单词再多也只需生成新词"""
    tts = gTTS(text=word, lang='en', slow=slow_mode)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    return base64.b64encode(fp.getvalue()).decode('utf-8')

def get_all_audios(words_list, slow_mode):
    return [get_single_audio_b64(w, slow_mode) for w in words_list]

# ================= 4. 全局 UI 渲染模块 (学习页和历史页共用) =================
def render_word_list(df_render, pause_sec, slow_mode, show_en, show_zh):
    if df_render.empty:
        st.info("这里空空如也，快去添加单词吧！")
        return

    audio_words = df_render['English'].tolist()

    with st.spinner("正在准备高音质音频..."):
        b64_audios = get_all_audios(audio_words, slow_mode)

    # --- 顶部连播控制台 ---
    html_code = f"""
    <div style="font-family: sans-serif; padding: 15px; background-color: #f0f2f6; border-radius: 10px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
        <div style="display: flex; gap: 10px; width: 100%;">
            <button id="playBtn" style="flex: 1; background-color: #ff4b4b; color: white; border: none; padding: 12px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.3s; -webkit-tap-highlight-color: transparent;">
                🔊 开始连读磨耳朵 (精确停顿 {pause_sec} 秒)
            </button>
            <button id="pauseBtn" style="flex: 1; display: none; background-color: #ffc107; color: #333; border: none; padding: 12px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.3s; -webkit-tap-highlight-color: transparent;">
                ⏸️ 暂停播放
            </button>
            <button id="resetBtn" style="flex: 1; display: none; background-color: #666; color: white; border: none; padding: 12px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.3s; -webkit-tap-highlight-color: transparent;">
                🔄 从头重播
            </button>
        </div>
        <div id="status" style="margin-top: 15px; font-size: 16px; color: #31333F; font-weight: bold;">等待播放...</div>
        <audio id="audioPlayer"></audio>
    </div>
    <script>
        const words = {json.dumps(audio_words)};
        const audios = {json.dumps(b64_audios)};
        const pauseTime = {pause_sec} * 1000;
        let currentIndex = 0; let isPlaying = false; let isGap = false; let timer = null;
        
        const player = document.getElementById('audioPlayer');
        const playBtn = document.getElementById('playBtn');
        const pauseBtn = document.getElementById('pauseBtn');
        const resetBtn = document.getElementById('resetBtn');
        const status = document.getElementById('status');
        
        function resetAll() {{
            isPlaying = false; isGap = false; currentIndex = 0; clearTimeout(timer); player.pause(); player.src = "";
            playBtn.innerText = "🔊 开始连读磨耳朵 (精确停顿 {pause_sec} 秒)";
            playBtn.style.display = "block"; pauseBtn.style.display = "none"; resetBtn.style.display = "none";
            status.innerText = "等待播放..."; status.style.color = "#31333F";
        }}

        playBtn.onclick = () => {{
            isPlaying = true; playBtn.style.display = "none"; pauseBtn.style.display = "block"; resetBtn.style.display = "block";
            if (currentIndex >= words.length) currentIndex = 0;
            if (isGap) {{ isGap = false; playNext(); }} 
            else if (player.src && player.currentTime > 0 && !player.ended) {{
                status.innerText = "🔊 正在朗读: " + words[currentIndex]; status.style.color = "#ff4b4b"; player.play();
            }} else playNext();
        }};
        
        pauseBtn.onclick = () => {{
            isPlaying = false; playBtn.innerText = "▶️ 继续播放"; playBtn.style.display = "block"; pauseBtn.style.display = "none";
            player.pause(); clearTimeout(timer);
            status.innerText = "⏸️ 已暂停: " + (currentIndex < words.length ? words[currentIndex] : ""); status.style.color = "#888";
        }};
        
        resetBtn.onclick = resetAll;
        
        function playNext() {{
            if (!isPlaying) return;
            if (currentIndex < words.length) {{
                status.innerText = "🔊 正在朗读: " + words[currentIndex]; status.style.color = "#ff4b4b";
                player.src = "data:audio/mp3;base64," + audios[currentIndex]; player.play();
                player.onended = () => {{
                    if (!isPlaying) return;
                    currentIndex++;
                    if (currentIndex < words.length) {{
                        isGap = true; status.innerText = "⏳ 思考中 (" + {pause_sec} + "秒)..."; status.style.color = "#0083B8";
                        timer = setTimeout(() => {{ isGap = false; playNext(); }}, pauseTime);
                    }} else {{
                        resetAll(); status.innerText = "🎉 本组播放完毕！"; status.style.color = "#28a745";
                    }}
                }};
            }}
        }}
    </script>
    """
    components.html(html_code, height=160)
    st.markdown("---")

    # --- 底部列表渲染 (手机端防崩溃精美排版) ---
    for loop_idx, (idx, row) in enumerate(df_render.iterrows()):
        en_word = str(row['English']).replace('<', '&lt;').replace('>', '&gt;')
        zh_word = str(row['Chinese']).replace('<', '&lt;').replace('>', '&gt;')
        
        en_text = f"<div style='font-size: 18px; font-weight: bold; color: #2C3E50;'>{en_word}</div>" if show_en else "<div style='color:#ccc;'>[英文已遮挡]</div>"
        zh_text = f"<div style='font-size: 14px; color: #7F8C8D; margin-top: 4px;'>{zh_word}</div>" if show_zh else "<div style='color:#ccc; margin-top: 4px;'>[中文已遮挡]</div>"
        audio_tag = f"<audio controls src='data:audio/mp3;base64,{b64_audios[loop_idx]}' style='width: 140px; height: 35px; outline: none;'></audio>"
        
        row_html = f"""
        <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #EAECEE; padding: 12px 0;">
            <div style="flex: 1; min-width: 0; padding-right: 15px; word-wrap: break-word;">{en_text}{zh_text}</div>
            <div style="flex: 0 0 140px; text-align: right;">{audio_tag}</div>
        </div>
        """
        st.markdown(row_html, unsafe_allow_html=True)

# ================= 5. 左侧边栏 (导航与全局设置) =================
with st.sidebar:
    st.header("🧭 导航菜单")
    # 核心新增：页面切换路由
    page_mode = st.radio("请选择模式：", ["📖 单元学习", "📚 历史复习库"])
    
    st.markdown("---")
    st.header("⚙️ 全局控制台")
    show_english = st.checkbox("👁️ 显示英文 (English)", value=True)
    show_chinese = st.checkbox("👁️ 显示中文 (释义)", value=True)
    
    is_shuffle = st.toggle("🔀 开启打乱顺序")
    if is_shuffle:
        if 'shuffle_seed' not in st.session_state:
            st.session_state.shuffle_seed = 42
        if st.button("🔄 换一种打乱方式"):
            st.session_state.shuffle_seed += 1

    st.markdown("---")
    speed_option = st.radio("🔊 朗读语速：", ["正常语速", "放慢发音 (Slow)"])
    is_slow_mode = (speed_option == "放慢发音 (Slow)")
    pause_seconds = st.slider("⏱️ 单词间停顿 (秒)：", min_value=1, max_value=30, value=2)

# ================= 6. 页面路由分发 =================

if page_mode == "📖 单元学习":
    st.title("📖 单元学习")
    
    # 单元选择框放在页面内，保持侧边栏干净
    selected_unit_str = st.selectbox("📚 选择要学习的单元：", unit_options)
    current_unit_idx = unit_options.index(selected_unit_str)
    
    start_index = current_unit_idx * WORDS_PER_UNIT
    end_index = min((current_unit_idx + 1) * WORDS_PER_UNIT, total_words)
    df_unit = df_words.iloc[start_index:end_index].copy()
    
    # 一键加入历史库按钮
    if st.button("⭐ 将本页单词加入【历史复习库】", type="primary", use_container_width=True):
        # 将当前单词与历史单词合并，并自动去重
        new_history = pd.concat([st.session_state.history_df, df_unit]).drop_duplicates(subset=['English']).reset_index(drop=True)
        st.session_state.history_df = new_history
        st.success(f"成功加入！目前复习库中共 {len(new_history)} 个单词。")
    
    if is_shuffle:
        df_unit = df_unit.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)
        
    render_word_list(df_unit, pause_seconds, is_slow_mode, show_english, show_chinese)


elif page_mode == "📚 历史复习库":
    st.title("📚 历史复习库")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**当前库中共有 {len(st.session_state.history_df)} 个待复习单词**")
    with col2:
        if st.button("🗑️ 清空记录", use_container_width=True):
            st.session_state.history_df = pd.DataFrame(columns=['English', 'Chinese'])
            st.rerun()
            
    df_history = st.session_state.history_df.copy()
    
    if is_shuffle and not df_history.empty:
        df_history = df_history.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)
        
    render_word_list(df_history, pause_seconds, is_slow_mode, show_english, show_chinese)
