# app.py
import subprocess
import sys

# ===== 可选：自动安装依赖（保留你的写法） =====
def install_packages():
    packages = [
        "Flask>=2.0.0",
        "yt-dlp>=2025.6.30"
    ]
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *packages])
        print("依赖安装完成！")
    except subprocess.CalledProcessError as e:
        print(f"安装依赖失败: {e}")
        sys.exit(1)

install_packages()
# ============================================

import os
import tempfile
from flask import Flask, request, render_template_string, redirect, url_for, flash, send_file
import yt_dlp
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# 上传大小限制：仅用于 cookie 文本，默认 300KB
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024
ALLOWED_EXTENSIONS = {'txt'}

# 解析结果缓存（内存级）
parsed_results = {}
# 全局持久化 cookie 文件路径（进程级，复用）
cookie_file_path = None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_video_info(youtube_url, cookiefile=None):
    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
    }
    if cookiefile:
        ydl_opts['cookiefile'] = cookiefile
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
    return info

# ===== 渐进式直链选择逻辑（含音轨） =====
def pick_best_progressive(formats):
    """
    从 formats 里挑选同时含音/视频轨的渐进式格式（可直接点击下载），
    选分辨率高、码率高者优先。
    """
    candidates = []
    for f in formats or []:
        if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('url'):
            height = f.get('height') or 0
            tbr = f.get('tbr') or 0  # total bitrate
            fps = f.get('fps') or 0
            candidates.append((height, tbr, fps, f))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    return candidates[-1][3]

def get_best_progressive_url(youtube_url, cookiefile=None):
    """
    返回 (best_progressive_url, info)。若无渐进式直链则 best_progressive_url 为 None。
    """
    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
    }
    if cookiefile:
        ydl_opts['cookiefile'] = cookiefile
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
    best_prog = pick_best_progressive(info.get('formats'))
    return (best_prog.get('url') if best_prog else None), info
# ========================================

INPUT_PAGE = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<link rel="shortcut icon" href="https://github.githubassets.com/favicons/favicon.svg">
<title>YouTube-视频预览</title>
<style>
 body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen,
    Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
  background: #f0f4f8;
  margin: 0;
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  color: #333;
  padding: 20px;
  box-sizing: border-box;
}

.container {
  background: #fff;
  padding: 40px 48px;
  border-radius: 16px;
  box-shadow: 0 12px 30px rgb(0 0 0 / 0.1);
  width: 100%;
  max-width: 700px;
  box-sizing: border-box;
  text-align: center;
}

h1 {
  font-weight: 700;
  font-size: 28px;
  margin-bottom: 24px;
  user-select: none;
  color: #222;
}

form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

label {
  font-size: 16px;
  color: #555;
  user-select: none;
  text-align: left;
  margin: 0 auto;
  max-width: 600px;
}

input[type=file],
input[type=text] {
  margin: 0 auto;
  font-size: 16px;
  max-width: 600px;
  width: 90%;
  padding: 8px 12px;
  border: 2px solid #3b82f6;
  border-radius: 8px;
  box-shadow: inset 0 4px 12px rgb(0 0 0 / 0.1);
  outline: none;
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
  box-sizing: border-box;
}

input[type=file]:focus,
input[type=text]:focus {
  border-color: #2563eb;
  box-shadow: 0 0 14px #2563eb;
}

button {
  width: 220px;
  padding: 14px 0;
  margin: 0 auto;
  font-size: 20px;
  font-weight: 700;
  color: white;
  background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
  border: none;
  border-radius: 14px;
  cursor: pointer;
  box-shadow: 0 6px 18px rgb(59 130 246 / 0.6);
  transition: background 0.3s ease, box-shadow 0.3s ease;
  user-select: none;
}

button:hover {
  background: linear-gradient(90deg, #2563eb 0%, #1e40af 100%);
  box-shadow: 0 8px 22px rgb(37 99 235 / 0.7);
}

.error {
  margin-top: 10px;
  color: #dc2626;
  font-weight: 600;
  user-select: none;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
  text-align: center;
}

a.download-link {
  display: block;
  margin-top: 30px;
  font-size: 18px;
  color: #3b82f6;
  text-decoration: none;
}

a.download-link:hover {
  text-decoration: underline;
}

/* 响应式适配 */
@media (max-width: 768px) {
  .container { padding: 30px 24px; }
  h1 { font-size: 24px; margin-bottom: 18px; }
  button { width: 100%; font-size: 18px; padding: 12px 0; }
  input[type=file], input[type=text] { width: 100%; max-width: none; }
  label { max-width: none; }
}

@media (max-width: 480px) {
  h1 { font-size: 20px; margin-bottom: 14px; }
  button { font-size: 18px; padding: 12px 0; }
}
</style>
</head>
<body>
  <div class="container">
    <h1>YouTube 直观解析</h1>
    <form method="post" enctype="multipart/form-data">
      <label>
        上传一次 <a href="https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank" style="margin-left:8px; font-size:14px; color:#3b82f6; text-decoration:none;">Cookie</a>（txt，可选）：
      </label>
      <input type="file" name="cookiefile" accept=".txt" />

      <label>输入单个视频链接：</label>
      <input type="text" name="linktextarea" placeholder="https://www.youtube.com/watch?v=..." />

      <button type="submit">开始解析</button>

      <div style="display: flex; justify-content: center; gap: 24px; margin-top: 10px;">
        <a href="https://github.com/tcq20256/yt-dlp-youtube-web"
           style="font-size:14px; color:#3b82f6; text-decoration:none; align-self: center;">
          项目地址
        </a>
        <a href="https://cloud.tencent.com/act/cps/redirect?redirect=33387&cps_key=615609c54e8bcced8b02c202a43b5570" target="_blank"
           style="font-size:14px; color:#3b82f6; text-decoration:none; align-self: center;">
          域名注册
        </a>
      </div>
    </form>

    {% with messages = get_flashed_messages() %}
      {% if messages %}
        <div class="error">{{ messages[0] }}</div>
      {% endif %}
    {% endwith %}

    {% if cookie_ready %}
      <div style="margin-top:10px; font-size:12px; color:#10b981;">✅ Cookie 已加载，后续解析将自动复用。</div>
    {% endif %}
  </div>
</body>
</html>
'''

RESULT_PAGE = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>解析结果 - {{ info.title }}</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen,
        Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
      background: #f5f7fa;
      margin: 20px;
      color: #333;
      text-align: center;
    }
    h1 {
      font-weight: 700;
      font-size: 26px;
      margin-bottom: 20px;
    }
    .container {
      max-width: 720px;
      margin: 0 auto;
      background: #fff;
      padding: 24px 28px;
      border-radius: 12px;
      box-shadow: 0 10px 30px rgb(0 0 0 / 0.08);
    }
    h2 {
      font-weight: 700;
      font-size: 20px;
      margin-bottom: 16px;
      word-break: break-word;
    }
    img {
      max-width: 320px;
      border-radius: 12px;
      margin-bottom: 20px;
      box-shadow: 0 6px 12px rgb(0 0 0 / 0.08);
    }
    .btn-grid {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 14px 18px;
      margin-top: 20px;
    }
    .download-btn {
      background-color: #3b82f6;
      color: white;
      border-radius: 10px;
      padding: 14px 22px;
      font-size: 15px;
      font-weight: 600;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      box-shadow: 0 3px 10px rgb(59 130 246 / 0.45);
      transition: background-color 0.3s ease;
      user-select: none;
      cursor: pointer;
      white-space: nowrap;
      border: none;
      min-width: 150px;
      justify-content: center;
    }
    .download-btn:hover { background-color: #2563eb; }
    .no-audio-icon { font-size: 16px; color: #f87171; user-select: none; }
    a.back-link {
      display: inline-block;
      margin-top: 20px;
      font-size: 14px;
      color: #3b82f6;
      cursor: pointer;
      text-decoration: none;
    }
    a.back-link:hover { text-decoration: underline; }
    .tip {
      margin-top:10px; font-size:12px; color:#666;
    }
    .codebox {
      padding:10px 12px; background:#111827; color:#e5e7eb; border-radius:6px;
      display:inline-block; margin-top:6px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }
  </style>
</head>
<body>
  <h1>解析结果</h1>
  <div class="container">
    <h2>{{ info.title }}</h2>
    <img src="{{ info.thumbnail }}" alt="视频封面" />

    <div>
      {% if best_progressive_url %}
        <button class="download-btn" onclick="window.open('{{ best_progressive_url }}', '_blank')">
          ⬇️ 下载视频（渐进式直链，含音轨）
        </button>
        <button class="download-btn" onclick="window.open('{{ info.thumbnail }}', '_blank')">
          🖼️ 下载封面
        </button>
        <div class="tip">提示：直链带有平台签名，通常数小时内过期；长期可复现下载请使用下方命令。</div>
      {% else %}
        <div style="padding:12px 16px; border:1px solid #e5e7eb; background:#f9fafb; border-radius:10px; line-height:1.6;">
          未检测到可用的“含音轨直链”（高码率视频常见分离音/视频流）。<br />
          推荐使用命令行合并下载（需本地 ffmpeg）：<br />
          <span class="codebox">yt-dlp -f "bestvideo+bestaudio/best" "{{ page_video_url }}"</span>
        </div>
        <div style="margin-top:14px;">
          <button class="download-btn" onclick="window.open('{{ info.thumbnail }}', '_blank')">
            🖼️ 下载封面
          </button>
        </div>
      {% endif %}
    </div>

    <h3 style="margin-top: 30px;">更多视频分辨率下载选项</h3>
    <div class="btn-grid">
      {% for f in formats %}
        {% if f.vcodec != 'none' %}
          <a class="download-btn" href="{{ f.url }}" target="_blank" download>
            {{ f.format_note or f.format }} ({{ f.ext }})
            {% if f.filesize %} - {{ (f.filesize / 1024 / 1024) | round(2) }}MB{% endif %}
            {% if f.acodec == 'none' %}
              <span class="no-audio-icon" title="无声音轨">🔇</span>
            {% endif %}
          </a>
        {% endif %}
      {% endfor %}
    </div>

    <h3 style="margin-top: 30px;">所有音频格式</h3>
    <div class="btn-grid">
      {% for f in formats %}
        {% if f.vcodec == 'none' and f.acodec != 'none' %}
          <a class="download-btn" href="{{ f.url }}" target="_blank" download>
            {{ f.format_note or f.format }} ({{ f.ext }})
            {% if f.filesize %} - {{ (f.filesize / 1024 / 1024) | round(2) }}MB{% endif %}
          </a>
        {% endif %}
      {% endfor %}
    </div>

    <a href="{{ url_for('index') }}" class="back-link">← 返回首页</a>
  </div>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    global cookie_file_path
    error = None
    url = ''

    if request.method == 'POST':
        # ===== 仅当本次上传了 cookie 时才更新全局 cookie_file_path =====
        cookiefile = request.files.get('cookiefile')
        if cookiefile and cookiefile.filename != '':
            if not allowed_file(cookiefile.filename):
                flash('只允许上传 txt 格式的 cookie 文件。')
                return render_template_string(INPUT_PAGE, error=None, url='', cookie_ready=bool(cookie_file_path))
            filename = secure_filename(cookiefile.filename)
            tmp = tempfile.NamedTemporaryFile(delete=False)
            cookiefile.save(tmp.name)
            tmp.close()
            # 替换旧 cookie 文件
            if cookie_file_path and os.path.exists(cookie_file_path):
                try:
                    os.remove(cookie_file_path)
                except Exception:
                    pass
            cookie_file_path = tmp.name

        # ===== 单行链接输入 =====
        url = request.form.get('linktextarea', '').strip()
        if not url:
            flash('请输入视频链接。')
            return render_template_string(INPUT_PAGE, error=None, url='', cookie_ready=bool(cookie_file_path))

        try:
            best_url, data = get_best_progressive_url(url, cookiefile=cookie_file_path)
            parsed_results[url] = {'info': data, 'best_progressive_url': best_url}
            return redirect(url_for('result', video_url=url))
        except Exception as e:
            error = f"解析失败: {e}"

    return render_template_string(INPUT_PAGE, error=error, url=url, cookie_ready=bool(cookie_file_path))

@app.route('/result')
def result():
    video_url = request.args.get('video_url')
    payload = parsed_results.get(video_url)
    if not payload:
        return redirect(url_for('index'))
    data = payload['info']
    best_progressive_url = payload.get('best_progressive_url')
    return render_template_string(
        RESULT_PAGE,
        info=data,
        formats=data.get('formats', []),
        best_progressive_url=best_progressive_url,
        page_video_url=video_url
    )

#（可保留：批量下载结果文件接口；当前页面未使用此功能）
@app.route('/download/<file_id>')
def download_file(file_id):
    filepath = parsed_results.get(file_id)
    if filepath and os.path.exists(filepath):
        response = send_file(filepath, as_attachment=True, download_name='parsed_results.txt')
        def cleanup(response):
            try:
                os.remove(filepath)
                parsed_results.pop(file_id, None)
            except Exception:
                pass
            return response
        response.call_on_close(cleanup)
        return response
    else:
        flash("下载文件不存在或已过期")
        return redirect(url_for('index'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
