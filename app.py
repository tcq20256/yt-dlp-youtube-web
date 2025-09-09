# app.py —— 单页版：三按钮（最高视频 / 最高音频 / 可播放的音频+视频 非m3u8）
import subprocess, sys
def install_packages():
    pkgs = ["Flask>=2.0.0", "yt-dlp>=2025.6.30"]
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *pkgs])
        print("依赖安装完成！")
    except subprocess.CalledProcessError as e:
        print(f"安装依赖失败: {e}"); sys.exit(1)
install_packages()

import os, tempfile
from flask import Flask, request, render_template_string, flash
import yt_dlp
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "your_secret_key_here"
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024  # 仅限制 cookie 文本大小
ALLOWED_EXT = {"txt"}

last_result = None
cookie_file_path = None

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
    if not cands: return None
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

def extract_info(url, cookiefile=None):
    opts = {"quiet": True, "noplaylist": True}
    if cookiefile: opts["cookiefile"] = cookiefile
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

# ---------- 单页模板 ----------
PAGE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>YouTube 解析</title>
<style>
body {font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen,Ubuntu,Cantarell,"Open Sans","Helvetica Neue",sans-serif;background:#f0f4f8;margin:0;padding:20px;color:#333;}
.container {max-width:860px;margin:0 auto;background:#fff;padding:28px 30px;border-radius:16px;box-shadow:0 12px 30px rgb(0 0 0 / 0.08);}
h1 {margin:0 0 16px;font-size:26px;}
label {display:block;margin:12px 0 6px;color:#555;}
input[type=file], input[type=text] {width:100%;box-sizing:border-box;font-size:16px;padding:10px 12px;border:2px solid #3b82f6;border-radius:10px;outline:none;box-shadow:inset 0 4px 12px rgb(0 0 0 / 0.05);}
input[type=file]:focus, input[type=text]:focus {border-color:#2563eb;box-shadow:0 0 12px #2563eb;}
button {display:inline-flex;align-items:center;gap:6px;background:linear-gradient(90deg,#3b82f6 0%,#2563eb 100%);color:#fff;border:0;border-radius:12px;padding:12px 18px;font-weight:700;cursor:pointer;box-shadow:0 6px 18px rgb(59 130 246 / 0.5);}
button:hover {background:linear-gradient(90deg,#2563eb 0%,#1e40af 100%);}
.row {display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;}
.badge {margin-top:6px;font-size:12px;color:#10b981;}
.error {margin-top:10px;color:#dc2626;font-weight:600;}
.card {margin-top:18px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:18px;}
.center {text-align:center;}
.btn-row {display:flex;justify-content:center;gap:14px;flex-wrap:wrap;margin-top:10px;}
.download-btn {background:#3b82f6;color:#fff;border:0;border-radius:10px;padding:12px 16px;font-weight:700;cursor:pointer;box-shadow:0 3px 10px rgb(59 130 246 / 0.45);}
.download-btn:hover {background:#2563eb;}
.tip {margin-top:8px;font-size:12px;color:#666;}
.codebox {padding:8px 10px;background:#111827;color:#e5e7eb;border-radius:6px;display:inline-block;font-family:ui-monospace,Menlo,Consolas,monospace;}
.thumb {max-width:360px;border-radius:12px;box-shadow:0 6px 12px rgb(0 0 0 / .08);margin:10px auto;display:block;}
a.link {color:#3b82f6;text-decoration:none;} a.link:hover {text-decoration:underline;}
.dlmeta {font-size:12px;opacity:.8;margin-left:6px;}
</style>
</head>
<body>
  <div class="container">
    <h1>YouTube 一键解析</h1>
    <form method="post" enctype="multipart/form-data">
      <label>（可选）上传一次 Cookie（txt）：</label>
      <input type="file" name="cookiefile" accept=".txt" />
      {% if cookie_ready %}<div class="badge">✅ Cookie 已加载并将自动复用</div>{% endif %}

      <label style="margin-top:12px;">输入单个视频链接：</label>
      <input type="text" name="link" placeholder="https://www.youtube.com/watch?v=..." value="{{ link or '' }}" />

      <div class="row">
        <button type="submit" name="action" value="parse">开始解析</button>
        <a class="link" href="https://github.com/tcq20256/yt-dlp-youtube-web" target="_blank">项目地址</a>
      </div>

      {% with messages = get_flashed_messages() %}
        {% if messages %}<div class="error">{{ messages[0] }}</div>{% endif %}
      {% endwith %}
    </form>

    {% if info %}
    <div class="card">
      <div class="center">
        <h2 style="margin:6px 0 8px;">{{ info.title }}</h2>
        <img class="thumb" src="{{ info.thumbnail }}" alt="视频封面" />
      </div>

      <div class="btn-row">
        {% if max_video %}
          <button class="download-btn" onclick="window.open('{{ max_video.url }}', '_blank')">
            ⬇️ 最高画质·仅视频
            <span class="dlmeta">({{ (max_video.format_note or (max_video.height ~ 'p')) }} {{ max_video.ext }})</span>
          </button>
        {% endif %}

        {% if best_av %}
          <button class="download-btn" onclick="window.open('{{ best_av.url }}', '_blank')">
            ▶️ 音频+视频（可直接播放）
            <span class="dlmeta">({{ (best_av.format_note or (best_av.height ~ 'p')) }} {{ best_av.ext }})</span>
          </button>
        {% else %}
          <button class="download-btn" disabled title="未找到可直连的含音轨渐进式">
            ▶️ 音频+视频（无可直连）
          </button>
        {% endif %}

        {% if max_audio %}
          <button class="download-btn" onclick="window.open('{{ max_audio.url }}', '_blank')">
            🎵 最高质量·仅音频
            <span class="dlmeta">({{ (max_audio.abr or max_audio.tbr or '?' ) }}kbps {{ max_audio.ext }})</span>
          </button>
        {% endif %}
      </div>

      <div class="center tip" style="margin-top:10px;">
        直链接口带签名，可能数小时内过期；长期可复现请使用命令：
        <div class="codebox">
          {% if max_video and max_video.format_id %}
            yt-dlp -f "{{ max_video.format_id }}+bestaudio/best" "{{ link }}"
          {% else %}
            yt-dlp -f "bestvideo+bestaudio/best" "{{ link }}"
          {% endif %}
        </div>
      </div>

      <div class="center" style="margin-top:12px;">
        <button class="download-btn" onclick="window.open('{{ info.thumbnail }}', '_blank')">🖼️ 下载封面</button>
      </div>
    </div>
    {% endif %}
  </div>
</body>
</html>
"""

# ---------- 路由 ----------
@app.route("/", methods=["GET", "POST"])
def index():
    global cookie_file_path, last_result
    info = None; max_video = None; max_audio = None; best_av = None
    link = ""

    if request.method == "POST" and request.form.get("action") == "parse":
        # Cookie（可选，持久一次）
        f = request.files.get("cookiefile")
        if f and f.filename:
            if "." not in f.filename or f.filename.rsplit(".",1)[1].lower() not in ALLOWED_EXT:
                flash("只允许上传 txt 格式的 cookie 文件。")
                return render_template_string(PAGE, cookie_ready=bool(cookie_file_path), info=None, link="")
            tmp = tempfile.NamedTemporaryFile(delete=False)
            f.save(tmp.name); tmp.close()
            if cookie_file_path and os.path.exists(cookie_file_path):
                try: os.remove(cookie_file_path)
                except Exception: pass
            cookie_file_path = tmp.name

        # 链接
        link = (request.form.get("link") or "").strip()
        if not link:
            flash("请输入视频链接。")
            return render_template_string(PAGE, cookie_ready=bool(cookie_file_path), info=None, link=link)

        # 解析
        try:
            data = extract_info(link, cookiefile=cookie_file_path)
            best_av = pick_best_progressive_playable(data.get("formats"))
            max_video = pick_max_video_only(data.get("formats"))
            max_audio = pick_max_audio_only(data.get("formats"))
            info = data
            last_result = {"info": data, "link": link, "best_av": best_av, "max_video": max_video, "max_audio": max_audio}
        except Exception as e:
            flash(f"解析失败：{e}")

    # GET 回显
    if request.method == "GET" and last_result:
        info = last_result["info"]
        best_av = last_result.get("best_av")
        max_video = last_result.get("max_video")
        max_audio = last_result.get("max_audio")
        link = last_result["link"]

    return render_template_string(
        PAGE,
        cookie_ready=bool(cookie_file_path),
        info=info,
        best_av=best_av,
        max_video=max_video,
        max_audio=max_audio,
        link=link,
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
