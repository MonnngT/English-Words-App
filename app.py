import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os
import base64
import json
import wave 
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components

# ================= 1. 页面配置与数据库连接 =================
st.set_page_config(page_title="AI 听力单词本-终极版", page_icon="🎧", layout="centered")

# 初始化随机种子（用于多次乱序功能）
if 'shuffle_seed' not in st.session_state:
    st.session_state.shuffle_seed = 42

# 连接到 Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_history = conn.read(ttl=0)
    
    # 【防崩溃】：彻底清理 Google 表格中的空行、NaN 和无意义数据
    if not df_history.empty:
        df_history = df_history.dropna(subset=['English'])
        df_history['English'] = df_history['English'].astype(str).str.strip()
        df_history = df_history[df_history['English'] != '']
        df_history = df_history[df_history['English'].str.lower() != 'nan']
    
    # 自动升级数据库列
    if 'Unit_Name' not in df_history.columns:
        df_history['Unit_Name'] = '未知单元'
        
except Exception as e:
    st.error("云端数据库连接尚未生效，请检查 Secrets 配置。目前使用临时数据。")
    df_history = pd.DataFrame(columns=['English', 'Chinese', 'Unit_Name'])

# ================= 2. 加载本地单词表 =================
@st.cache_data
def load_data():
    # 优先加载 words.csv，找不到则加载 word.csv
    file_name = "words.csv" if os.path.exists("words.csv") else "word.csv"
    try:
        return pd.read_csv(file_name, encoding="utf-8-sig")
    except:
        try:
            return pd.read_csv(file_name, encoding="gbk")
        except:
            return pd.DataFrame(columns=['English', 'Chinese'])

df_source = load_data()
if df_source.empty:
    st.error("找不到单词本文件！请确保仓库里有 words.csv。")
    st.stop()

# 计算总单元数并生成列表
WORDS_PER_UNIT = 20
total_words = len(df_source)
total_units = (total_words + WORDS_PER_UNIT - 1) // WORDS_PER_UNIT
unit_options = [f"第 {i+1} 单元 ({i*WORDS_PER_UNIT + 1}-{min((i+1)*WORDS_PER_UNIT, total_words)})" for i in range(total_units)]

# ================= 3. 核心音频模块 =================
@st.cache_data(show_spinner=False)
def get_audio_b64(word, slow_mode):
    safe_word = str(word).strip()
    if not safe_word: safe_word = "error"
    tts = gTTS(text=safe_word, lang='en', slow=slow_mode)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    return base64.b64encode(fp.getvalue()).decode('utf-8')

@st.cache_data(show_spinner=False)
def generate_silence_wav_b64(seconds):
    """生成 N 秒的纯空白音频流，用来维持手机系统的后台播放权限"""
    sample_rate = 44100
    num_samples = int(sample_rate * max(0.1, seconds))
    fp = io.BytesIO()
    with wave.open(fp, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2) 
        wav.setframerate(sample_rate)
        wav.writeframes(b'\x00' * (num_samples * 2)) 
    return "data:audio/wav;base64," + base64.b64encode(fp.getvalue()).decode('utf-8')

def render_list(df_to_show, pause_sec, is_slow, show_en, show_zh):
    if df_to_show.empty:
        st.info("库里还没有单词。")
        return
    
    # 渲染前最后一次清洗
    df_to_show = df_to_show[df_to_show['English'].astype(str).str.strip() != '']
    audio_words = df_to_show['English'].astype(str).tolist()
    
    with st.spinner("正在加载音频引擎 (支持手机息屏后台连播)..."):
        b64_audios = [get_audio_b64(w, is_slow) for w in audio_words]
        silence_audio_uri = generate_silence_wav_b64(pause_sec)

    # 包含 MediaSession API 的终极 JS 播放器，解决后台被杀问题
    html_code = f"""
    <div style="font-family: sans-serif; padding: 15px; background-color: #f0f2f6; border-radius: 10px; text-align: center;">
        <button id="pBtn" style="width:100%; background:#ff4b4b; color:white; border:none; padding:12px; border-radius:6px; cursor:pointer; font-weight:bold; -webkit-tap-highlight-color: transparent;">
            🔊 开始息屏后台连读 (停顿 {pause_sec}s)
        </button>
        <div id="st" style="margin-top:10px; font-weight:bold; color:#31333F;">等待开始...</div>
        <audio id="player"></audio>
    </div>
    <script>
        const ws = {json.dumps(audio_words)}; 
        const as = {json.dumps(b64_audios)};
        const silenceUri = "{silence_audio_uri}";
        
        let cur = 0; let playing = false; let isGap = false;
        const p = document.getElementById('player');
        const b = document.getElementById('pBtn'); const s = document.getElementById('st');

        // 更新手机锁屏界面的媒体信息
        function updateMetadata() {{
            if ('mediaSession' in navigator) {{
                navigator.mediaSession.metadata = new MediaMetadata({{
                    title: '英语听力背诵中...',
                    artist: '正在读: ' + (ws[cur] || '完成'),
                    album: '单词库',
                    artwork: [{{ src: 'https://cdn-icons-png.flaticon.com/512/3039/3039403.png', sizes: '512x512', type: 'image/png' }}]
                }});
                navigator.mediaSession.setActionHandler('nexttrack', () => {{ isGap = false; cur++; playNext(); }});
            }}
        }}

        b.onclick = () => {{
            if(playing) {{ 
                playing=false; b.innerText="▶️ 继续播放"; s.innerText="已暂停"; p.pause(); 
            }} else {{ 
                playing=true; b.innerText="⏸️ 暂停"; 
                if (p.src && p.currentTime > 0 && !p.ended) p.play(); else playNext(); 
            }}
            updateMetadata();
        }};

        function playNext() {{
            if(!playing) return;
            updateMetadata();
            
            if (isGap) {{
                s.innerText = "⏳ 思考中...";
                p.src = silenceUri; 
                p.play();
                p.onended = () => {{ if(playing) {{ isGap = false; playNext(); }} }};
            }} else {{
                if(cur < ws.length) {{
                    s.innerText = "🔊 正在读: " + ws[cur];
                    p.src = "data:audio/mp3;base64," + as[cur]; 
                    p.play();
                    p.onended = () => {{
                        cur++;
                        if(cur < ws.length) {{ isGap = true; playNext(); }} 
                        else {{ s.innerText="🎉 播放完毕"; playing=false; b.innerText="🔊 重新开始"; cur=0; }}
                    }};
                }}
            }}
        }}
        
        if ('mediaSession' in navigator) {{
            navigator.mediaSession.setActionHandler('play', () => {{ playing = true; playNext(); }});
            navigator.mediaSession.setActionHandler('pause', () => {{ playing = false; p.pause(); }});
        }}
    </script>
    """
    components.html(html_code, height=130)

    # 列表展示渲染
    for i, row in df_to_show.iterrows():
        en_word = str(row['English']).replace('<', '&lt;').replace('>', '&gt;')
        zh_word = str(row['Chinese']).replace('<', '&lt;').replace('>', '&gt;')
        en = f"<b>{en_word}</b>" if show_en else "<span style='color:#ccc;'>***</span>"
        zh = zh_word if show_zh else "<span style='color:#ccc;'>***</span>"
        # 为每个单词生成独立播放器
        word_audio_b64 = b64_audios[audio_words.index(str(row['English']))]
        tag = f"<audio controls src='data:audio/mp3;base64,{word_audio_b64}' style='width:140px;height:35px;'></audio>"
        st.markdown(f'<div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #eee;padding:10px 0;"><div style="flex:1;">{en}<br>{zh}</div><div style="flex:0 0 140px;">{tag}</div></div>', unsafe_allow_html=True)

# ================= 4. 侧边栏控制 =================
with st.sidebar:
    st.header("🎮 导航控制")
    mode = st.radio("模式选择：", ["📖 单元学习与添加", "📚 历史复习库(永久保存)"])
    
    st.divider()
    st.header("👁️ 显隐设置")
    show_en = st.checkbox("显示英文", value=True)
    show_zh = st.checkbox("显示中文", value=True)
    
    st.divider()
    st.header("🔀 乱序功能")
    is_shuffle = st.toggle("开启乱序模式")
    if is_shuffle:
        if st.button("🔄 换一种随机顺序", use_container_width=True):
            st.session_state.shuffle_seed += 1
            
    st.divider()
    st.header("🔊 语音设置")
    pause_sec = st.slider("单词间停顿 (秒)", 1, 30, 2)
    speed_mode = st.radio("语速选择", ["正常", "放慢"], horizontal=True)
    is_slow = (speed_mode == "放慢")

# ================= 5. 页面逻辑 =================
if mode == "📖 单元学习与添加":
    st.title("📖 单元学习与添加")
    
    # 提取已添加记录
    added_units = [u for u in df_history['Unit_Name'].unique() if pd.notna(u) and str(u).startswith("第")]
    st.info(f"📌 **已入库单元**：{', '.join(added_units) if added_units else '暂无记录'}")
    
    tab1, tab2 = st.tabs(["🎯 单单元学习", "📦 批量存入复习库"])
    
    with tab1:
        unit = st.selectbox("选择当前要学的单元", unit_options)
        idx = unit_options.index(unit)
        df_unit = df_source.iloc[idx*WORDS_PER_UNIT : (idx+1)*WORDS_PER_UNIT].copy()
        df_unit['Unit_Name'] = unit 

        if st.button("⭐ 永久存入云端复习库", type="primary", use_container_width=True):
            new_data = pd.concat([df_history, df_unit]).drop_duplicates(subset=['English'])
            # 存入前清洗
            new_data = new_data.dropna(subset=['English']).query("English != ''")
            conn.update(data=new_data)
            st.success(f"已成功将 {unit} 存入云端！")
            st.rerun()

        if is_shuffle: 
            df_unit = df_unit.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)
        render_list(df_unit, pause_sec, is_slow, show_en, show_zh)

    with tab2:
        st.markdown("#### 批量导入助手")
        # 排除已添加的，默认勾选接下来的单元
        available_units = [u for u in unit_options if u not in added_units]
        batch_units = st.multiselect("请勾选要批量加入的单元：", options=unit_options, default=available_units[:3] if available_units else None)
        
        if st.button("🚀 一键确认批量存入", type="primary", use_container_width=True):
            if not batch_units:
                st.warning("请至少选择一个单元！")
            else:
                dfs_to_add = []
                for bu in batch_units:
                    b_idx = unit_options.index(bu)
                    b_df = df_source.iloc[b_idx*WORDS_PER_UNIT : (b_idx+1)*WORDS_PER_UNIT].copy()
                    b_df['Unit_Name'] = bu
                    dfs_to_add.append(b_df)
                
                new_all = pd.concat([df_history] + dfs_to_add).drop_duplicates(subset=['English'])
                # 最终清洗
                new_all = new_all.dropna(subset=['English'])
                new_all = new_all[new_all['English'].astype(str).str.strip() != '']
                
                conn.update(data=new_all)
                st.success(f"🎉 批量导入成功！已存入 {len(batch_units)} 个单元。")
                st.rerun()

else:
    st.title("📚 历史复习库")
    st.caption(f"当前云端共永久存储了 {len(df_history)} 个单词")
    
    if st.button("🗑️ 清空所有云端数据"):
        empty_df = pd.DataFrame(columns=['English', 'Chinese', 'Unit_Name'])
        conn.update(data=empty_df)
        st.rerun()

    df_rev = df_history.copy()
    if is_shuffle and not df_rev.empty: 
        df_rev = df_rev.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)
        
    render_list(df_rev, pause_sec, is_slow, show_en, show_zh)
