import subprocess
import sys

# 安装依赖
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

import os
import tempfile
from flask import Flask, request, render_template_string, flash, send_file
import yt_dlp

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024  # 300KB 上传 Cookie 文件限制
ALLOWED_EXTENSIONS = {'txt'}
parsed_results = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_video_info(youtube_url, cookie_path=None):
    ydl_opts = {'quiet': True, 'noplaylist': True}
    if cookie_path:
        ydl_opts['cookiefile'] = cookie_path
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(youtube_url, download=False)

def get_best_video_url(youtube_url, cookie_path=None):
    ydl_opts = {'quiet': True, 'noplaylist': True, 'format': 'bestvideo+bestaudio/best'}
    if cookie_path:
        ydl_opts['cookiefile'] = cookie_path
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        best_url = info.get('url')
        if not best_url:
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    best_url = f.get('url')
                    break
        return best_url

# 单页面模板，支持单链接详情和批量解析下载
PAGE_TEMPLATE = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>YouTube 多功能解析器</title>
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
    .download-btn:hover {
      background-color: #2563eb;
    }
    .no-audio-icon {
      font-size: 16px;
      color: #f87171;
      user-select: none;
    }
    a.back-link {
      display: inline-block;
      margin-top: 20px;
      font-size: 14px;
      color: #3b82f6;
      cursor: pointer;
      text-decoration: none;
    }
    a.back-link:hover {
      text-decoration: underline;
    }
    @media (max-width: 600px) {
      img {
        max-width: 100%;
      }
      .btn-grid {
        justify-content: center;
      }
      .download-btn {
        min-width: 120px;
        font-size: 13px;
        padding: 10px 16px;
      }
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>YouTube 多功能解析器</h1>
    <form method="post" enctype="multipart/form-data">
      <label>上传 Cookie 文件（可选，.txt，最大300KB）：</label>
      <input type="file" name="cookiefile" accept=".txt" />
      <label>请输入视频链接（多行，每行一个链接）：</label>
      <textarea name="linktextarea" placeholder="https://www.youtube.com/watch?v=..." rows="6"></textarea>
      <button type="submit">开始解析</button>
    </form>
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        <div class="error">{{ messages[0] }}</div>
      {% endif %}
    {% endwith %}

    {% if info %}
      <div class="result">
        <h2>{{ info.title }}</h2>
        <img src="{{ info.thumbnail }}" alt="封面" />
        <p>时长: {{ info.duration }}秒</p>
        <div>
          <a href="{{ info.url }}" target="_blank">下载最佳画质</a>
        </div>
        <h3>可选格式</h3>
        <ul>
        {% for f in formats %}
          <li>
            <a href="{{ f.url }}" target="_blank">{{ f.format_note or f.format }} ({{ f.ext }}){% if f.filesize %} - {{ (f.filesize/1024/1024)|round(2) }}MB{% endif %}</a>
            {% if f.acodec=='none' %}🔇{% endif %}
          </li>
        {% endfor %}
        </ul>
      </div>
    {% endif %}

    {% if download_url %}
      <div class="batch-result">
        <a href="{{ download_url }}" class="download-link" download>⬇️ 下载批量解析结果</a>
      </div>
    {% endif %}
  </div>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    info = None
    formats = []
    download_url = None
    cookie_path = None

    if request.method == 'POST':
        # Cookie 文件
        cf = request.files.get('cookiefile')
        if cf and cf.filename:
            if not allowed_file(cf.filename):
                flash('只允许上传 .txt 格式的 Cookie 文件。')
                return render_template_string(PAGE_TEMPLATE)
            tmp = tempfile.NamedTemporaryFile(delete=False)
            cf.save(tmp.name)
            cookie_path = tmp.name

        content = request.form.get('linktextarea', '').strip()
        if not content:
            flash('请输入至少一个视频链接。')
            if cookie_path: os.remove(cookie_path)
            return render_template_string(PAGE_TEMPLATE)

        links = [l.strip() for l in content.splitlines() if l.strip()]
        if len(links) == 1:
            # 单链接详情
            try:
                info = get_video_info(links[0], cookie_path)
                formats = info.get('formats', [])
            except Exception as e:
                flash(f'解析失败: {e}')
            finally:
                if cookie_path: os.remove(cookie_path)
        else:
            # 批量解析下载链接
            results = []
            for url in links:
                try:
                    vurl = get_best_video_url(url, cookie_path)
                    results.append(f"{url} {vurl}")
                except Exception as e:
                    results.append(f"解析失败 {url} 错误: {e}")
            if cookie_path: os.remove(cookie_path)
            tmp = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.txt')
            tmp.write('\n'.join(results))
            tmp.close()
            fid = os.path.basename(tmp.name)
            parsed_results[fid] = tmp.name
            download_url = url_for('download_file', file_id=fid)

    return render_template_string(PAGE_TEMPLATE, info=info, formats=formats, download_url=download_url)

@app.route('/download/<file_id>')
def download_file(file_id):
    path = parsed_results.get(file_id)
    if not path or not os.path.exists(path):
        flash('下载文件不存在或已过期')
        return redirect('/')
    resp = send_file(path, as_attachment=True, download_name='parsed_results.txt')
    resp.call_on_close(lambda: (os.remove(path), parsed_results.pop(file_id, None)))
    return resp

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
