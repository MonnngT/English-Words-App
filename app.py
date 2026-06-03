import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os
import base64
import json
import wave
import tempfile
import subprocess
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components

# ================= 1. 页面配置与数据库初始化 =================
st.set_page_config(page_title="AI 英语背单词-全能版", page_icon="🎧", layout="centered")

# 初始化随机种子
if 'shuffle_seed' not in st.session_state:
    st.session_state.shuffle_seed = 42

# 连接云端数据库 (Google Sheets)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_history = conn.read(ttl=0)

    # 【防崩溃：数据清洗】
    if not df_history.empty:
        df_history = df_history.dropna(subset=['English'])
        df_history['English'] = df_history['English'].astype(str).str.strip()
        df_history = df_history[(df_history['English'] != '') & (df_history['English'].str.lower() != 'nan')]

    if 'Unit_Name' not in df_history.columns:
        df_history['Unit_Name'] = '手动导入'

except Exception:
    st.warning("云端连接加载中，请检查 Secrets 配置。")
    conn = None
    df_history = pd.DataFrame(columns=['English', 'Chinese', 'Unit_Name'])

# ================= 2. 加载本地数据 (words.csv) =================
@st.cache_data
def load_local_data():
    for name in ["words.csv", "word.csv"]:
        if os.path.exists(name):
            # 优先 utf-8-sig，失败再退回 gbk，不再用裸 except 吞掉真实报错
            for enc in ("utf-8-sig", "gbk"):
                try:
                    return pd.read_csv(name, encoding=enc)
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
    return pd.DataFrame(columns=['English', 'Chinese'])

df_source = load_local_data()
if df_source.empty:
    st.error("未找到 words.csv，请确保文件已上传至 GitHub 仓库。")
    st.stop()

# 单元计算
WORDS_PER_UNIT = 20
total_words = len(df_source)
total_units = (total_words + WORDS_PER_UNIT - 1) // WORDS_PER_UNIT
unit_options = [f"第 {i+1} 单元 ({i*WORDS_PER_UNIT + 1}-{min((i+1)*WORDS_PER_UNIT, total_words)})" for i in range(total_units)]

# 复习库分页大小（避免一次性给上千个词逐个请求 TTS）
REVIEW_PAGE_SIZE = 20

# ================= 3. 核心音频与后台播放引擎 =================
@st.cache_data(show_spinner=False)
def get_audio_b64(word, slow_mode):
    """单词级容错：某个词 TTS 失败（限流/网络）时返回空串，不连累整页。"""
    try:
        safe_text = str(word).strip() or "error"
        tts = gTTS(text=safe_text, lang='en', slow=slow_mode)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return base64.b64encode(fp.getvalue()).decode('utf-8')
    except Exception:
        return ""

@st.cache_data(show_spinner=False)
def build_continuous_audio_b64(words, audio_b64_list, pause_sec):
    """Build one MP3 track so mobile background playback does not depend on JS timers."""
    playable_items = [(str(word), b64) for word, b64 in zip(words, audio_b64_list) if b64]
    if not playable_items:
        return "", []

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            silence_path = os.path.join(tmpdir, "silence.mp3")
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=24000:cl=mono",
                    "-t",
                    str(max(0.1, float(pause_sec))),
                    "-acodec",
                    "libmp3lame",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    silence_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            concat_path = os.path.join(tmpdir, "concat.txt")
            with open(concat_path, "w", encoding="utf-8") as concat_file:
                for idx, (_, audio_b64) in enumerate(playable_items):
                    word_path = os.path.join(tmpdir, f"word_{idx:03d}.mp3")
                    with open(word_path, "wb") as word_file:
                        word_file.write(base64.b64decode(audio_b64))
                    concat_file.write(f"file '{word_path.replace(os.sep, '/')}'\n")
                    if idx < len(playable_items) - 1:
                        concat_file.write(f"file '{silence_path.replace(os.sep, '/')}'\n")

            output_path = os.path.join(tmpdir, "continuous.mp3")
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    concat_path,
                    "-acodec",
                    "libmp3lame",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    output_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            with open(output_path, "rb") as output_file:
                return base64.b64encode(output_file.read()).decode("utf-8"), [w for w, _ in playable_items]
    except Exception:
        return "", [w for w, _ in playable_items]

@st.cache_data(show_spinner=False)
def generate_silence_b64(seconds):
    """生成无声 WAV，防止手机系统休眠或掐断后台进程"""
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

    df_to_show = df_to_show[df_to_show['English'].astype(str).str.strip() != '']
    audio_words = df_to_show['English'].astype(str).tolist()
    zh_words = df_to_show['Chinese'].astype(str).tolist()

    with st.spinner("准备音频焦点恢复引擎..."):
        b64_audios = [get_audio_b64(w, is_slow) for w in audio_words]
        silence_uri = generate_silence_b64(pause_sec)
        continuous_b64, continuous_words = build_continuous_audio_b64(audio_words, b64_audios, pause_sec)
    # 连读播放器只收录成功生成音频的词，避免空 src 卡住自动续播
    play_words = continuous_words or [w for w, b in zip(audio_words, b64_audios) if b]
    play_b64 = [b for b in b64_audios if b]
    if play_words and not continuous_b64:
        st.warning("后台连续播放增强未启用：当前环境未找到 ffmpeg，将使用普通逐词续播。")

    # 【核心：带有心跳监测和焦点夺回功能的 JS 播放器】
    html_code = f"""
    <div style="font-family: sans-serif; padding: 15px; background-color: #f0f2f6; border-radius: 12px; text-align: center; border: 1px solid #ddd;">
        <button id="pBtn" style="width:100%; background:#ff4b4b; color:white; border:none; padding:15px; border-radius:8px; cursor:pointer; font-weight:bold; font-size:16px; -webkit-tap-highlight-color: transparent;">
            🔊 开始息屏后台连读 (停顿 {pause_sec}s)
        </button>
        <div id="st" style="margin-top:12px; font-weight:bold; color:#31333F;">准备就绪</div>
        <audio id="player" preload="auto" playsinline style="width:100%; margin-top:10px;"></audio>
    </div>

    <script>
        const words = {json.dumps(play_words)};
        const audios = {json.dumps(play_b64)};
        const silenceUri = "{silence_uri}";
        const continuousAudio = "{continuous_b64}";

        let cur = 0, playing = false, isGap = false;
        const p = document.getElementById('player');
        const b = document.getElementById('pBtn');
        const s = document.getElementById('st');
        const hasContinuousAudio = Boolean(continuousAudio);

        if (hasContinuousAudio) {{
            p.src = "data:audio/mp3;base64," + continuousAudio;
            s.innerText = "已准备整段音频，可切后台播放 " + words.length + " 个单词";
        }}

        function updateMetadata() {{
            if ('mediaSession' in navigator) {{
                navigator.mediaSession.metadata = new MediaMetadata({{
                    title: 'AI 英语背诵 - 自动续播版',
                    artist: '当前: ' + (words[cur] || '完成'),
                    album: '后台运行中',
                    artwork: [{{ src: 'https://cdn-icons-png.flaticon.com/512/3039/3039403.png', sizes: '512x512', type: 'image/png' }}]
                }});
            }}
        }}

        async function tryToPlay() {{
            try {{
                await p.play();
                playing = true;
                b.innerText = "⏸️ 暂停播放";
                updateMetadata();
            }} catch (e) {{
                console.log("播放被拦截，等待恢复");
            }}
        }}

        // 【核心：焦点夺回监听】
        document.addEventListener('visibilitychange', () => {{
            if (!document.hidden && playing && p.paused) tryToPlay();
        }});

        // 【核心：心跳监测】每 2 秒检查，被系统掐断后尝试自动唤醒
        setInterval(() => {{
            if (playing && p.paused && !isGap) {{
                tryToPlay();
            }}
        }}, 2000);

        b.onclick = () => {{
            if(playing) {{
                playing = false; p.pause(); b.innerText="▶️ 继续播放"; s.innerText="已暂停";
            }} else {{
                playing = true; b.innerText="⏸️ 暂停播放";
                if (hasContinuousAudio) {{
                    if (p.ended) p.currentTime = 0;
                    s.innerText = "整段音频播放中，可切到后台";
                    tryToPlay();
                }} else if (p.src && !p.ended) tryToPlay(); else playNext();
            }}
        }};

        p.onended = () => {{
            if (hasContinuousAudio) {{
                playing = false;
                b.innerText = "🔊 重新开始";
                s.innerText = "🎉 播放完毕";
            }}
        }};

        function playNext() {{
            if(!playing) return;
            if(hasContinuousAudio) return;
            updateMetadata();

            if(isGap) {{
                s.innerText = "⏳ 思考中...";
                p.src = silenceUri;
                p.play().catch(tryToPlay);
                p.onended = () => {{ if(playing) {{ isGap = false; playNext(); }} }};
            }} else {{
                if(cur < words.length) {{
                    s.innerText = "🔊 正在朗读: " + words[cur];
                    p.src = "data:audio/mp3;base64," + audios[cur];
                    p.play().catch(tryToPlay);
                    p.onended = () => {{
                        cur++;
                        if(cur < words.length) {{ isGap = true; playNext(); }}
                        else {{ s.innerText="🎉 播放完毕"; playing=false; b.innerText="🔊 重新开始"; cur=0; }}
                    }};
                }}
            }}
        }}

        if ('mediaSession' in navigator) {{
            navigator.mediaSession.setActionHandler('play', tryToPlay);
            navigator.mediaSession.setActionHandler('pause', () => {{ playing=false; p.pause(); b.innerText="▶️ 继续"; }});
        }}
    </script>
    """
    components.html(html_code, height=150)

    # 列表展示：O(n) 遍历，不再做 list.index 线性查找，也不重复打包音频
    for en_word, zh_word, b64 in zip(audio_words, zh_words, b64_audios):
        en_safe = en_word.replace('<', '&lt;').replace('>', '&gt;')
        zh_safe = zh_word.replace('<', '&lt;').replace('>', '&gt;')
        en = f"<b>{en_safe}</b>" if show_en else "***"
        zh = zh_safe if show_zh else "***"
        if b64:
            tag = f"<audio controls src='data:audio/mp3;base64,{b64}' style='width:145px;height:35px;'></audio>"
        else:
            tag = "<span style='color:#bbb;font-size:0.8em;'>音频生成失败</span>"
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #eee;padding:12px 0;">'
            f'<div style="flex:1;">{en}<br><span style="color:#666;font-size:0.9em;">{zh}</span></div>'
            f'<div style="flex:0 0 150px;text-align:right;">{tag}</div></div>',
            unsafe_allow_html=True
        )

# ================= 4. 侧边栏 =================
with st.sidebar:
    st.title("🎧 背词控制台")
    nav = st.radio("功能切换：", ["📖 学习与添加", "📚 云端复习库"])
    st.divider()
    show_en = st.checkbox("显示英文", value=True)
    show_zh = st.checkbox("显示中文", value=True)

    st.divider()
    is_shuffle = st.toggle("开启乱序模式")
    if is_shuffle:
        if st.button("🔄 换个随机顺序 (洗牌)", use_container_width=True):
            st.session_state.shuffle_seed += 1

    st.divider()
    pause_sec = st.slider("单词间停顿 (秒)", 1, 30, 2)
    is_slow = st.radio("语速选择", ["正常", "慢速"], horizontal=True) == "慢速"

# ================= 5. 页面路由逻辑 =================
if nav == "📖 学习与添加":
    st.title("📖 单元学习")

    added = [u for u in df_history['Unit_Name'].unique() if pd.notna(u) and "第" in str(u)]
    st.info(f"📍 **已入库单元**：{', '.join(added) if added else '库中暂无记录'}")

    t1, t2 = st.tabs(["🎯 当前单元", "📦 批量导入"])

    with t1:
        unit = st.selectbox("选择要学习的单元", unit_options)
        idx = unit_options.index(unit)
        df_unit = df_source.iloc[idx*WORDS_PER_UNIT : (idx+1)*WORDS_PER_UNIT].copy()
        df_unit['Unit_Name'] = unit

        if st.button("⭐ 永久存入云端复习库", type="primary", use_container_width=True):
            if conn is None:
                st.error("云端未连接，无法存入。")
            else:
                new_df = pd.concat([df_history, df_unit]).drop_duplicates(subset=['English'])
                new_df = new_df.dropna(subset=['English']).query("English != ''")
                conn.update(data=new_df)
                st.success("存入云端成功！")
                st.rerun()

        if is_shuffle:
            df_unit = df_unit.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)
        render_list(df_unit, pause_sec, is_slow, show_en, show_zh)

    with t2:
        st.subheader("📦 批量入库助手")
        available = [u for u in unit_options if u not in added]
        to_add = st.multiselect("勾选单元批量存入云端：", options=unit_options, default=available[:3] if available else None)

        if st.button("🚀 确认批量导入", use_container_width=True):
            if conn is None:
                st.error("云端未连接，无法导入。")
            elif not to_add:
                st.warning("请至少勾选一个单元")
            else:
                batch_list = []
                for u in to_add:
                    u_idx = unit_options.index(u)
                    tmp = df_source.iloc[u_idx*WORDS_PER_UNIT : (u_idx+1)*WORDS_PER_UNIT].copy()
                    tmp['Unit_Name'] = u
                    batch_list.append(tmp)
                final = pd.concat([df_history] + batch_list).drop_duplicates(subset=['English'])
                final = final.dropna(subset=['English']).query("English != ''")
                conn.update(data=final)
                st.success(f"已批量导入 {len(to_add)} 个单元！")
                st.rerun()

else:
    st.title("📚 云端复习库")
    st.write(f"目前云端永久存储了 **{len(df_history)}** 个单词")

    if st.button("🗑️ 清空所有云端数据"):
        if conn is None:
            st.error("云端未连接，无法清空。")
        else:
            empty = pd.DataFrame(columns=['English', 'Chinese', 'Unit_Name'])
            conn.update(data=empty)
            st.rerun()

    df_rev = df_history.copy()
    if is_shuffle and not df_rev.empty:
        df_rev = df_rev.sample(frac=1, random_state=st.session_state.shuffle_seed).reset_index(drop=True)

    # 分页：一次只渲染 REVIEW_PAGE_SIZE 个词，避免一次性给上千词逐个请求 TTS
    if not df_rev.empty:
        total_pages = (len(df_rev) + REVIEW_PAGE_SIZE - 1) // REVIEW_PAGE_SIZE
        c1, c2 = st.columns([3, 1])
        with c1:
            page = st.number_input("页码", min_value=1, max_value=max(total_pages, 1), value=1, step=1)
        with c2:
            st.write("")
            st.caption(f"共 {total_pages} 页")
        start = (page - 1) * REVIEW_PAGE_SIZE
        df_rev = df_rev.iloc[start : start + REVIEW_PAGE_SIZE]

    render_list(df_rev, pause_sec, is_slow, show_en, show_zh)
