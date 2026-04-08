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

# ================= 1. 页面配置与数据库初始化 =================
st.set_page_config(page_title="AI 英语背单词-终极版", page_icon="🎧", layout="centered")

# 初始化随机种子（用于多次乱序）
if 'shuffle_seed' not in st.session_state:
    st.session_state.shuffle_seed = 42

# 连接云端数据库 (Google Sheets)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_history = conn.read(ttl=0)
    
    # 【防崩溃：数据深度清洗】
    if not df_history.empty:
        df_history = df_history.dropna(subset=['English'])
        df_history['English'] = df_history['English'].astype(str).str.strip()
        df_history = df_history[(df_history['English'] != '') & (df_history['English'].str.lower() != 'nan')]
    
    if 'Unit_Name' not in df_history.columns:
        df_history['Unit_Name'] = '手动入库'
        
except Exception as e:
    st.warning("云端连接加载中，请确保已正确配置 Secrets。")
    df_history = pd.DataFrame(columns=['English', 'Chinese', 'Unit_Name'])

# ================= 2. 加载本地数据 (words.csv) =================
@st.cache_data
def load_local_data():
    for name in ["words.csv", "word.csv"]:
        if os.path.exists(name):
            try:
                return pd.read_csv(name, encoding="utf-8-sig")
            except:
                return pd.read_csv(name, encoding="gbk")
    return pd.DataFrame(columns=['English', 'Chinese'])

df_source = load_local_data()
if df_source.empty:
    st.error("未找到 words.csv，请上传单词表到仓库。")
    st.stop()

# 单元计算
WORDS_PER_UNIT = 20
total_words = len(df_source)
total_units = (total_words + WORDS_PER_UNIT - 1) // WORDS_PER_UNIT
unit_options = [f"第 {i+1} 单元 ({i*WORDS_PER_UNIT + 1}-{min((i+1)*WORDS_PER_UNIT, total_words)})" for i in range(total_units)]

# ================= 3. 核心音频引擎 =================
@st.cache_data(show_spinner=False)
def get_audio_b64(word, slow_mode):
    safe_text = str(word).strip() or "error"
    tts = gTTS(text=safe_text, lang='en', slow=slow_mode)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    return base64.b64encode(fp.getvalue()).decode('utf-8')

@st.cache_data(show_spinner=False)
def generate_silence_b64(seconds):
    """生成一段无声波形文件，用以维持手机后台焦点"""
    fps = 44100
    n_samples = int(fps * max(0.1, seconds))
    fp = io.BytesIO()
    with wave.open(fp, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(fps)
        wav.writeframes(b'\x00' * (n_samples * 2))
    return "data:audio/wav;base64," + base64.b64encode(fp.getvalue()).decode('utf-8')

def render_list(df_to_show, pause_sec, is_slow, show_en, show_zh):
    if df_to_show.empty:
        st.info("列表为空。")
        return
    
    # 最终清洗
    df_to_show = df_to_show[df_to_show['English'].astype(str).str.strip() != '']
    audio_words = df_to_show['English'].astype(str).tolist()
    
    with st.spinner("准备音频流 (已开启焦点恢复引擎)..."):
        b64_audios = [get_audio_b64(w, is_slow) for w in audio_words]
        silence_uri = generate_silence_b64(pause_sec)

    # 【核心：带有焦点夺回与MediaSession支持的 JS 播放器】
    html_code = f"""
    <div style="font-family: sans-serif; padding: 15px; background-color: #f0f2f6; border-radius: 12px; text-align: center; border: 1px solid #ddd;">
        <button id="pBtn" style="width:100%; background:#ff4b4b; color:white; border:none; padding:15px; border-radius:8px; cursor:pointer; font-weight:bold; font-size:16px;">
            🔊 开始后台连播 (停顿 {pause_sec}s)
        </button>
        <div id="st" style="margin-top:12px; font-weight:bold; color:#31333F;">就绪：共 {len(audio_words)} 词</div>
        <audio id="player" style="display:none;"></audio>
    </div>

    <script>
        const words = {json.dumps(audio_words)};
        const audios = {json.dumps(b64_audios)};
        const silence = "{silence_uri}";
        
        let cur = 0, playing = false, isGap = false;
        const p = document.getElementById('player');
        const b = document.getElementById('pBtn');
        const s = document.getElementById('st');

        // 更新手机系统媒体中心信息
        function syncMedia() {{
            if ('mediaSession' in navigator) {{
                navigator.mediaSession.metadata = new MediaMetadata({{
                    title: '英语听力连读中',
                    artist: '正在播: ' + (words[cur] || '结束'),
                    artwork: [{{ src: 'https://cdn-icons-png.flaticon.com/512/3039/3039403.png', sizes: '512x512', type: 'image/png' }}]
                }});
            }}
        }}

        // 尝试夺回播放权限
        async function tryPlay() {{
            try {{
                await p.play();
                playing = true;
                b.innerText = "⏸️ 暂停播放";
            }} catch (e) {{
                console.log("需要用户交互才能恢复声音");
                s.innerText = "⚠️ 播放被系统中断，请点此按钮恢复";
                playing = false;
                b.innerText = "▶️ 恢复播放";
            }}
        }}

        // 焦点恢复监听：当从微信/广告切回时
        document.addEventListener('visibilitychange', () => {{
            if (!document.hidden && playing && p.paused) tryPlay();
        }});

        b.onclick = () => {{
            if(playing) {{
                playing = false; p.pause(); b.innerText="▶️ 继续播放"; s.innerText="已暂停";
            }} else {{
                playing = true; b.innerText="⏸️ 暂停播放";
                if (p.src && !p.ended) p.play(); else playNext();
            }}
        }};

        function playNext() {{
            if(!playing) return;
            syncMedia();
            
            if(isGap) {{
                s.innerText = "⏳ 停顿中...";
                p.src = silence;
                p.play();
                p.onended = () => {{ if(playing) {{ isGap = false; playNext(); }} }};
            }} else {{
                if(cur < words.length) {{
                    s.innerText = "🔊 正在朗读: " + words[cur];
                    p.src = "data:audio/mp3;base64," + audios[cur];
                    p.play();
                    p.onended = () => {{
                        cur++;
                        if(cur < words.length) {{ isGap = true; playNext(); }}
                        else {{ s.innerText="🎉 本组已读完"; playing=false; b.innerText="🔊 重新开始"; cur=0; }}
                    }};
                }}
            }}
        }}

        if ('mediaSession' in navigator) {{
            navigator.mediaSession.setActionHandler('play', tryPlay);
            navigator.mediaSession.setActionHandler('pause', () => {{ playing=false; p.pause(); b.innerText="▶️ 继续"; }});
        }}
    </script>
    """
    components.html(html_code, height=150)

    # 列表展示渲染
    for i, row in df_to_show.iterrows():
        en_word = str(row['English']).replace('<', '&lt;').replace('>', '&gt;')
        zh_word = str(row['Chinese']).replace('<', '&lt;').replace('>', '&gt;')
        en = f"<b>{en_word}</b>" if show_en else "***"
        zh = zh_word if show_zh else "***"
        # 单词独立点读
        word_b64 = b64_audios[audio_words.index(str(row['English']))]
        tag = f"<audio controls src='data:audio/mp3;base64,{word_b64}' style='width:145px;height:35px;'></audio>"
        st.markdown(f'<div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #eee;padding:12px 0;"><div style="flex:1;">{en}<br><span style="color:#666;font-size:0.9em;">{zh}</span></div><div style="flex:0 0 150px;text-align:right;">{tag}</div></div>', unsafe_allow_html=True)

# ================= 4. 侧边栏 =================
with st.sidebar:
    st.title("🎧 背词控制台")
    nav = st.radio("功能切换：", ["📖 学习与添加", "📚 云端复习库"])
    st.divider()
    show_en = st.checkbox("显示英文", value=True)
    show_zh = st.checkbox("显示中文", value=True)
    
    st.divider()
    is_shuffle = st.toggle("乱序洗牌模式")
    if is_shuffle:
        if st.button("🔄 换个新顺序", use_container_width=True):
            st.session_state.shuffle_seed += 1
            
    st.divider()
    pause_sec = st.slider("停顿时间 (秒)", 1, 30, 2)
    is_slow = st.radio("语速", ["正常", "慢速"], horizontal=True) == "慢速"

# ================= 5. 逻辑分发 =================
if nav == "📖 学习与添加":
    st.title("📖 单元学习")
    
    # 进度展示
    added = [u for u in df_history['Unit_Name'].unique() if pd.notna(u) and "第" in str(u)]
    st.info(f"📍 **已记录单元**：{', '.join(added) if added else '库中暂无记录'}")
    
    t1, t2 = st.tabs(["🎯 当前单元", "📦 批量导入"])
    
    with t1:
        unit = st.selectbox("选择单元", unit_options)
        idx = unit_options.index(unit)
        df_unit = df_source.iloc[idx*WORDS_PER_UNIT : (idx+1)*WORDS_PER_UNIT].copy()
        df_unit['Unit_Name'] = unit

        if st.button("⭐ 存入云端复习库", type="primary", use_container_width=True):
            new_df = pd.concat([df_history, df_unit]).drop_duplicates(subset=['English'])
            new_df = new_df.dropna(subset=['English']).query("English != ''")
            conn.update(data=new_df)
            st.success("入库成功！")
            st.rerun()

        if is_shuffle:
            df_unit = df_unit.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)
        render_list(df_unit, pause_sec, is_slow, show_en, show_zh)

    with t2:
        st.subheader("批量入库助手")
        to_add = st.multiselect("勾选单元批量存入云端：", options=unit_options)
        if st.button("🚀 确认批量导入", use_container_width=True):
            if not to_add:
                st.warning("请选择单元")
            else:
                batch_list = []
                for u in to_add:
                    u_idx = unit_options.index(u)
                    tmp_df = df_source.iloc[u_idx*WORDS_PER_UNIT : (u_idx+1)*WORDS_PER_UNIT].copy()
                    tmp_df['Unit_Name'] = u
                    batch_list.append(tmp_df)
                final_df = pd.concat([df_history] + batch_list).drop_duplicates(subset=['English'])
                final_df = final_df.dropna(subset=['English']).query("English != ''")
                conn.update(data=final_df)
                st.success(f"已批量导入 {len(to_add)} 个单元！")
                st.rerun()

else:
    st.title("📚 云端复习库")
    st.write(f"目前永久存储了 **{len(df_history)}** 个单词")
    
    if st.button("🗑️ 清空所有云端数据"):
        empty = pd.DataFrame(columns=['English', 'Chinese', 'Unit_Name'])
        conn.update(data=empty)
        st.rerun()

    df_rev = df_history.copy()
    if is_shuffle and not df_rev.empty:
        df_rev = df_rev.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)
    render_list(df_rev, pause_sec, is_slow, show_en, show_zh)
