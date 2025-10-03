# app.py —— 单页版：三按钮（最高视频 / 最高音频 / 可播放的音频+视频 非m3u8）
import os
import sys
import json
import uuid
import shutil
import tempfile
import subprocess
from pathlib import Path

def install_packages():
    # === CHG: 升级到更近版本；若仍遇 nsig 可切 nightly（见下方 NOTE）
    pkgs = ["Flask>=2.0.0", "yt-dlp>=2025.9.15"]
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *pkgs])
        print("依赖安装完成！")
    except subprocess.CalledProcessError as e:
        print(f"安装依赖失败: {e}")
        sys.exit(1)

install_packages()

from flask import Flask, request, render_template_string, flash, session, redirect, url_for
import yt_dlp
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change_this_to_a_random_secret")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # === CHG: 合理限制请求体大小为 5MB（避免超大 cookie 文件）
ALLOWED_EXT = {"txt"}

# ========== 会话与数据目录 ==========
DATA_ROOT = Path(tempfile.gettempdir()) / "yt_web"  # 例如 /tmp/yt_web
DATA_ROOT.mkdir(parents=True, exist_ok=True)

def get_sid():
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]

def get_user_dir():
    sid = get_sid()
    p = DATA_ROOT / sid
    p.mkdir(parents=True, exist_ok=True)
    return p

def user_cookie_path():
    return get_user_dir() / "cookies.txt"

def user_result_path():
    return get_user_dir() / "last_result.json"

def save_last_result(payload: dict):
    p = user_result_path()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

def load_last_result():
    p = user_result_path()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

# ---------- 过滤&挑选工具 ----------
STREAMING_PROTOCOLS = {"m3u8", "m3u8_native", "http_dash_segments", "dash", "ism", "hls"}

def is_non_m3u8_playable(f):
    """可直连播放：排除 m3u8/hls/dash，必须有直连 url。"""
    if not f or not f.get("url"):
        return False
    proto = (f.get("protocol") or "").lower()
    ext = (f.get("ext") or "").lower()
    if proto in STREAMING_PROTOCOLS or ext == "m3u8" or f.get("manifest_url"):
        return False
    return True

def pick_best_progressive_playable(formats):
    """
    可直接播放（非m3u8）的【含音轨】渐进式格式。
    先挑 mp4，其次其他；优先级：height > tbr > fps。
    """
    mp4, others = [], []
    for f in formats or []:
        if f.get("vcodec") != "none" and f.get("acodec") != "none" and is_non_m3u8_playable(f):
            bucket = mp4 if (f.get("ext") or "").lower() == "mp4" else others
            height = f.get("height") or 0
            tbr = f.get("tbr") or 0
            fps = f.get("fps") or 0
            bucket.append((height, tbr, fps, f))
    for bag in (mp4, others):
        if bag:
            bag.sort(key=lambda x: (x[0], x[1], x[2]))
            return bag[-1][3]
    return None

def pick_max_video_only(formats):
    """最高画质【仅视频】（非m3u8）"""
    cands = []
    for f in formats or []:
        if f.get("vcodec") != "none" and (f.get("acodec") in (None, "none")) and is_non_m3u8_playable(f):
            height = f.get("height") or 0
            tbr = f.get("tbr") or 0
            fps = f.get("fps") or 0
            cands.append((height, tbr, fps, f))
    if not cands:
        return None
    cands.sort(key=lambda x: (x[0], x[1], x[2]))
    return cands[-1][3]

def pick_max_audio_only(formats):
    """最高质量【仅音频】（非m3u8）——优先 m4a/mp4，其次 webm/opus；按 abr/tbr"""
    pref1, pref2 = [], []
    for f in formats or []:
        if (f.get("vcodec") in (None, "none")) and f.get("acodec") != "none" and is_non_m3u8_playable(f):
            abr = f.get("abr") or f.get("tbr") or 0
            ext = (f.get("ext") or "").lower()
            bucket = pref1 if ext in {"m4a", "mp4"} else pref2
            bucket.append((abr, f))
    for bag in (pref1, pref2):
        if bag:
            bag.sort(key=lambda x: x[0])
            return bag[-1][1]
    return None

# === NEW: 支持“优先客户端 + 自动回退”的提取逻辑 ===
CLIENT_FALLBACK = ["android", "tv", "mweb", "ios", "web"]

def build_ydl_opts(cookiefile: str | None, client: str | None):
    # yt-dlp API 的 extractor_args 建议使用字典形式
    # 等价于 CLI: --extractor-args "youtube:player_client=android"
    ea = {"youtube": {"player_client": [client or "android"]}}
    opts = {
        "quiet": True,
        "noplaylist": True,
        "force_ipv4": True,                 # 降低 403/连接异常概率
        "concurrent_fragment_downloads": 1, # SABR/HLS/DASH 时更稳（虽然我们尽量不用它们）
        "retries": 10,
        "fragment_retries": 10,
        "extractor_args": ea,
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile
    return opts

def try_extract_with_fallback(url: str, cookiefile: str | None, prefer_client: str | None):
    last_exc = None
    tried = []
    order = [prefer_client] + [c for c in CLIENT_FALLBACK if c != prefer_client] if prefer_client else CLIENT_FALLBACK
    for client in order:
        tried.append(client)
        try:
            with yt_dlp.YoutubeDL(build_ydl_opts(cookiefile, client)) as ydl:
                data = ydl.extract_info(url, download=False)
                # 打一些标记，便于上层渲染/诊断
                data["_used_client"] = client
                return data
        except Exception as e:
            last_exc = e
            continue
    # 全部失败则抛出最后一次异常，并附带尝试过的客户端
    raise RuntimeError(f"提取失败，已尝试客户端：{tried}. 最后错误：{last_exc}")

def extract_info(url, cookiefile=None, prefer_client: str | None = None):
    return try_extract_with_fallback(url, cookiefile, prefer_client)

# ---------- 单页模板 ----------
PAGE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>YouTube 解析</title>
<style>
:root{
  --brand:#3b82f6; --brand-deep:#2563eb; --bg:#f0f4f8; --card:#ffffff;
  --text:#222; --muted:#666; --ok:#10b981; --shadow:0 12px 30px rgb(0 0 0 / .08);
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0; padding:16px;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen,Ubuntu,Cantarell,"Open Sans","Helvetica Neue",sans-serif;
  background:var(--bg); color:var(--text);
}
.container{max-width:920px; margin:0 auto; background:var(--card); padding:24px 20px; border-radius:16px; box-shadow:var(--shadow);}
h1{margin:0 0 12px; font-size:24px; font-weight:800;}
label{display:block; margin:12px 0 6px; color:#444; font-size:15px;}
.help{font-size:12px; color:var(--muted); margin-top:6px}
.badge{font-size:12px; color:var(--ok); margin-top:6px}
.error{margin-top:10px; color:#dc2626; font-weight:600;}
.input, .file, .select{
  width:100%; font-size:16px; padding:10px 12px; border:2px solid var(--brand);
  border-radius:10px; outline:none; background:#fff; box-shadow:inset 0 4px 12px rgb(0 0 0 / .05);
}
.input:focus, .file:focus, .select:focus{border-color:var(--brand-deep); box-shadow:0 0 10px var(--brand-deep)}
.row{display:flex; flex-wrap:wrap; gap:12px; margin-top:12px;}
.btn{
  appearance:none; border:0; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; gap:6px;
  border-radius:12px; padding:12px 18px; font-weight:800; text-decoration:none; transition:transform .02s ease, background .2s ease, box-shadow .2s ease;
  box-shadow:0 6px 18px rgb(59 130 246 / .5);
}
.btn:active{transform:translateY(1px)}
.btn-primary{background:linear-gradient(90deg, var(--brand) 0%, var(--brand-deep) 100%); color:#fff}
.btn-primary:hover{background:linear-gradient(90deg, var(--brand-deep) 0%, #1e40af 100%)}
.btn-ghost{background:#eef2ff; color:var(--brand-deep); box-shadow:none; border:1px solid #dbeafe;}
.btn-ghost:hover{background:#e0e7ff}
.card{margin-top:16px; background:#f9fafb; border:1px solid #e5e7eb; border-radius:12px; padding:16px;}
.center{text-align:center}
.thumb{max-width:360px; width:100%; border-radius:12px; box-shadow:0 6px 12px rgb(0 0 0 / .08); margin:10px auto; display:block;}
.btn-row{display:flex; justify-content:center; gap:12px; flex-wrap:wrap; margin-top:10px}
.dlbtn{min-width:220px}
.tip{margin-top:8px; font-size:12px; color:var(--muted)}
.codebox{
  display:inline-block; margin-top:6px; padding:8px 10px; border-radius:6px;
  background:#111827; color:#e5e7eb; font-family:ui-monospace,Menlo,Consolas,monospace;
}
.meta{font-size:12px; opacity:.8; margin-left:6px}
.kv{font-size:12px; color:#444; margin-top:8px}
.kv code{background:#111827;color:#e5e7eb;padding:2px 6px;border-radius:6px}
@media (max-width: 720px){
  .container{padding:18px 14px; border-radius:14px}
  h1{font-size:20px}
  .btn, .dlbtn{width:100%}
  .row{gap:10px}
  .thumb{max-width:100%}
}
</style>
</head>
<body>
  <div class="container">
    <h1>YT 视频预览版</h1>

    <form method="post" enctype="multipart/form-data">
      <label>（可选）上传一次 Cookie（txt）</label>
      <input class="file" type="file" name="cookiefile" accept=".txt" />
      {% if cookie_ready %}<div class="badge">✅ Cookie 已加载并将自动复用（仅本会话）</div>{% endif %}
      <div class="help">提示：只需上传一次；需要更换时再上传新文件即可。本页已禁用缓存。</div>

      <label style="margin-top:12px;">输入单个视频链接：</label>
      <input class="input" type="text" name="link" placeholder="https://www.youtube.com/watch?v=..." value="{{ link or '' }}" inputmode="url" autocapitalize="off" autocomplete="off" autocorrect="off" />

      <!-- === NEW: 客户端选择（默认 android），用于规避 SABR 与 nsig 相关问题 -->
      <label style="margin-top:12px;">客户端（解析优先使用；失败将自动回退）</label>
      <select class="select" name="client">
        {% for c in ["android","tv","mweb","ios","web"] %}
          <option value="{{ c }}" {% if client==c %}selected{% endif %}>{{ c }}</option>
        {% endfor %}
      </select>

      <div class="row">
        <button type="submit" name="action" value="parse" class="btn btn-primary">开始预览</button>
        <a class="btn btn-ghost" href="https://github.com/tcq20256/yt-dlp-youtube-web" target="_blank" rel="noopener">项目地址</a>
        <a class="btn btn-ghost" href="https://regurl.cn" target="_blank" rel="noopener">注册域名</a>
        <a class="btn btn-ghost" href="https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank" rel="noopener">获取 Cookie 插件</a>
      </div>

      <div class="row">
        <button type="submit" formaction="{{ url_for('clear_cookies') }}" class="btn btn-ghost">🧹 清除本会话 Cookie</button>
        <button type="submit" formaction="{{ url_for('clear_result') }}" class="btn btn-ghost">🧽 清除本会话解析记录</button>
      </div>

      {% with messages = get_flashed_messages() %}
        {% if messages %}<div class="error">{{ messages[0] }}</div>{% endif %}
      {% endwith %}
    </form>

    {% if info %}
    <div class="card">
      <div class="center">
        <h2 style="margin:6px 0 8px; font-size:18px">{{ info.title }}</h2>
        <img class="thumb" src="{{ info.thumbnail }}" alt="视频封面" />
      </div>

      <div class="btn-row">
        {% if max_video %}
          <a class="btn btn-primary dlbtn" href="{{ max_video.url }}" target="_blank" rel="noopener">
            ⬇️ 最高画质·仅视频
            <span class="meta">({{ (max_video.format_note or (max_video.height ~ 'p')) }} {{ max_video.ext }})</span>
          </a>
        {% endif %}

        {% if best_av %}
          <a class="btn btn-primary dlbtn" href="{{ best_av.url }}" target="_blank" rel="noopener">
            ▶️ 音频+视频（可直接播放）
            <span class="meta">({{ (best_av.format_note or (best_av.height ~ 'p')) }} {{ best_av.ext }})</span>
          </a>
        {% else %}
          <button class="btn btn-ghost dlbtn" disabled title="未找到可直连的含音轨渐进式">▶️ 音频+视频（无可直连）</button>
        {% endif %}

        {% if max_audio %}
          <a class="btn btn-primary dlbtn" href="{{ max_audio.url }}" target="_blank" rel="noopener">
            🎵 最高质量·仅音频
            <span class="meta">({{ (max_audio.abr or max_audio.tbr or '?' ) }}kbps {{ max_audio.ext }})</span>
          </a>
        {% endif %}
      </div>

      <div class="center tip">
        直链接口可能数小时内过期；长期可复现请使用命令：
        <div class="codebox">
          {% if max_video and max_video.format_id %}
            yt-dlp -f "{{ max_video.format_id }}+bestaudio/best" "{{ link }}"
          {% else %}
            yt-dlp -f "bestvideo+bestaudio/best" "{{ link }}"
          {% endif %}
        </div>
        <div class="kv">使用的客户端：<code>{{ info._used_client or "unknown" }}</code></div>
      </div>

      <div class="center" style="margin-top:12px;">
        <a class="btn btn-ghost" href="{{ info.thumbnail }}" target="_blank" rel="noopener">🖼️ 下载封面</a>
      </div>
    </div>
    {% endif %}
  </div>
</body>
</html>
"""

# ---------- 路由 ----------
@app.after_request
def add_no_cache_headers(resp):
    # 禁止中间层与浏览器缓存带有个人状态的页面
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.route("/", methods=["GET", "POST"])
def index():
    info = None; max_video = None; max_audio = None; best_av = None
    link = ""
    client = request.form.get("client") or (load_last_result() or {}).get("client") or "android"  # === NEW/CHG
    cookie_path = user_cookie_path()

    if request.method == "POST" and request.form.get("action") == "parse":
        # Cookie（可选，持久到本会话目录）
        f = request.files.get("cookiefile")
        if f and f.filename:
            if "." not in f.filename or f.filename.rsplit(".", 1)[1].lower() not in ALLOWED_EXT:
                flash("只允许上传 txt 格式的 cookie 文件。")
                return render_template_string(PAGE, cookie_ready=cookie_path.exists(), info=None, link="", client=client)
            tmp = tempfile.NamedTemporaryFile(delete=False)
            f.save(tmp.name); tmp.close()
            shutil.move(tmp.name, cookie_path)  # 覆盖当前会话的 cookie

        # 链接
        link = (request.form.get("link") or "").strip()
        if not link:
            flash("请输入视频链接。")
            return render_template_string(PAGE, cookie_ready=cookie_path.exists(), info=None, link=link, client=client)

        # 解析（带客户端优先与回退）
        try:
            data = extract_info(link, cookiefile=str(cookie_path) if cookie_path.exists() else None, prefer_client=client)
            best_av_f = pick_best_progressive_playable(data.get("formats"))
            max_video_f = pick_max_video_only(data.get("formats"))
            max_audio_f = pick_max_audio_only(data.get("formats"))

            # 准备渲染用的精简字段
            info = {
                "title": data.get("title"),
                "thumbnail": data.get("thumbnail"),
                "_used_client": data.get("_used_client", client)
            }
            best_av = best_av_f and {
                "format_id": best_av_f.get("format_id"),
                "url": best_av_f.get("url"),
                "ext": best_av_f.get("ext"),
                "format_note": best_av_f.get("format_note"),
                "height": best_av_f.get("height"),
            }
            max_video = max_video_f and {
                "format_id": max_video_f.get("format_id"),
                "url": max_video_f.get("url"),
                "ext": max_video_f.get("ext"),
                "format_note": max_video_f.get("format_note"),
                "height": max_video_f.get("height"),
            }
            max_audio = max_audio_f and {
                "url": max_audio_f.get("url"),
                "ext": max_audio_f.get("ext"),
                "abr": max_audio_f.get("abr"),
                "tbr": max_audio_f.get("tbr"),
            }

            save_last_result({
                "link": link,
                "client": info["_used_client"],
                "info": info,
                "best_av": best_av,
                "max_video": max_video,
                "max_audio": max_audio,
            })
        except Exception as e:
            flash(f"解析失败：{e}")

    # GET 回显（或 POST 失败/无解析结果时的再次渲染）
    if request.method == "GET":
        lr = load_last_result()
        if lr:
            link = lr.get("link", "")
            client = lr.get("client", client)
            info = lr.get("info")
            best_av = lr.get("best_av")
            max_video = lr.get("max_video")
            max_audio = lr.get("max_audio")

    return render_template_string(
        PAGE,
        cookie_ready=user_cookie_path().exists(),
        info=info,
        best_av=best_av,
        max_video=max_video,
        max_audio=max_audio,
        link=link,
        client=client,
    )

# 清理接口（仅本会话）
@app.post("/clear_cookies")
def clear_cookies():
    p = user_cookie_path()
    if p.exists():
        try:
            p.unlink()
            flash("已清除当前会话的 Cookie。")
        except Exception as e:
            flash(f"清除 Cookie 失败：{e}")
    else:
        flash("当前会话没有已保存的 Cookie。")
    return redirect(url_for("index"))

@app.post("/clear_result")
def clear_result():
    p = user_result_path()
    if p.exists():
        try:
            p.unlink()
            flash("已清除当前会话的解析记录。")
        except Exception as e:
            flash(f"清除解析记录失败：{e}")
    else:
        flash("当前会话没有可清除的解析记录。")
    return redirect(url_for("index"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # 生产环境建议用 gunicorn 等前置；此处开发模式关闭 reloader 以避免多进程造成困惑
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
