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
from flask import Flask, request, render_template_string, flash, send_file, url_for, redirect
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

# 页面模板：统一输入和结果展示样式
PAGE_TEMPLATE = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>YouTube 多功能解析器</title>
  <style>
    :root {
      --primary-color: #3b82f6;
      --primary-hover: #2563eb;
      --bg-light: #f5f7fa;
      --text-dark: #333;
      --container-max: 800px;
      --radius: 12px;
      --spacing: 16px;
      --shadow-light: rgba(0,0,0,0.08);
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0; padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
      background: var(--bg-light); color: var(--text-dark); line-height: 1.5;
    }
    header { text-align: center; padding: var(--spacing) 0; }
    header h1 { margin: 0; font-size: 1.75rem; font-weight: 700; }
    main { display: flex; justify-content: center; padding: var(--spacing); }
    .card {
      width: 90%; max-width: var(--container-max);
      background: #fff; padding: calc(var(--spacing)*1.5);
      border-radius: var(--radius);
      box-shadow: 0 10px 30px var(--shadow-light);
    }
    form {
      display: flex; flex-direction: column; gap: var(--spacing);
    }
    label { font-size: 1rem; color: #555; }
    input[type="file"], textarea {
      width: 100%; padding: 8px 12px;
      border: 2px solid var(--primary-color);
      border-radius: 8px; font-size: 1rem; resize: vertical;
    }
    textarea { min-height: 120px; }
    .btn {
      display: inline-flex; align-items: center; justify-content: center;
      padding: 12px 20px; font-size: 1rem; font-weight: 600;
      color: #fff; background: var(--primary-color);
      border: none; border-radius: 10px;
      cursor: pointer; text-decoration: none;
      box-shadow: 0 3px 10px var(--shadow-light);
      transition: background-color 0.3s;
    }
    .btn:hover, .btn:focus { background: var(--primary-hover); }
    .downloads {
      display: grid; row-gap: calc(var(--spacing)*2);
      margin-top: calc(var(--spacing)*2);
    }
    .download-group {
      display: flex; flex-direction: column;
      gap: var(--spacing);
    }
    .download-group h3 {
      margin: 0; font-size: 1.1rem; color: var(--text-dark);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 14px;
    }
    @media(max-width: 600px) {
      .grid { grid-template-columns: 1fr; }
      .btn { padding: 10px 16px; font-size: 0.9rem; }
    }
    .error { color: #dc2626; font-weight: bold; text-align: center; margin-bottom: var(--spacing); }
    img.thumbnail {
      display: block; width: 100%; max-width: 320px;
      margin: var(--spacing) auto;
      border-radius: var(--radius);
      box-shadow: 0 6px 12px var(--shadow-light);
    }
  </style>
</head>
<body>
  <header>
    <h1>YouTube 多功能解析器</h1>
  </header>
  <main>
    <div class="card" role="region" aria-live="polite">
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          <div class="error" role="alert">{{ messages[0] }}</div>
        {% endif %}
      {% endwith %}
      <form method="post" enctype="multipart/form-data" novalidate>
        <fieldset>
          <legend>上传 Cookie（可选，.txt，最大300KB）</legend>
          <label for="cookiefile">选择 Cookie 文件：</label>
          <input id="cookiefile" type="file" name="cookiefile" accept=".txt" />
        </fieldset>
        <fieldset>
          <legend>视频链接（多行，每行一个链接）</legend>
          <label for="linktextarea" class="sr-only">视频链接</label>
          <textarea id="linktextarea" name="linktextarea" placeholder="https://www.youtube.com/watch?v=...">{{ request.form.linktextarea or '' }}</textarea>
        </fieldset>
        <button type="submit" class="btn">开始解析</button>
      </form>

      {% if info %}
      <section class="downloads">
        <div class="download-group">
          <h3>下载视频</h3>
          <div class="grid">
            <a class="btn" href="{{ info.url }}" target="_blank" rel="noopener">⬇️ 最佳画质</a>
            {% for f in formats if f.vcodec!='none' %}
            <a class="btn" href="{{ f.url }}" target="_blank" rel="noopener" download>
              {{ f.format_note or f.format }}
              {% if f.filesize %}( {{ (f.filesize/1048576)|round(2) }}MB ){% endif %}
              {% if f.acodec=='none' %}<span aria-label="无音频">🔇</span>{% endif %}
            </a>
            {% endfor %}
          </div>
        </div>
        <div class="download-group">
          <h3>下载音频</h3>
          <div class="grid">
            {% for f in formats if f.vcodec=='none' and f.acodec!='none' %}
            <a class="btn" href="{{ f.url }}" target="_blank" rel="noopener" download>
              {{ f.format_note or f.format }}
              {% if f.filesize %}( {{ (f.filesize/1048576)|round(2) }}MB ){% endif %}
            </a>
            {% endfor %}
          </div>
        </div>
      </section>
      {% endif %}

      {% if download_url %}
      <section class="section">
        <h2>批量解析结果</h2>
        <a class="btn" href="{{ download_url }}" download>⬇️ 下载全部结果</a>
      </section>
      {% endif %}
    </div>
  </main>
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
        cf = request.files.get('cookiefile')
        if cf and cf.filename:
            if not allowed_file(cf.filename):
                flash('只允许上传 .txt 格式的 Cookie 文件。')
                return render_template_string(PAGE_TEMPLATE)
            tmp = tempfile.NamedTemporaryFile(delete=False)
            cf.save(tmp.name)
            cookie_path = tmp.name

        text = request.form.get('linktextarea','').strip()
        if not text:
            flash('请输入至少一个视频链接。')
            if cookie_path: os.remove(cookie_path)
            return render_template_string(PAGE_TEMPLATE)

        links = [l.strip() for l in text.splitlines() if l.strip()]
        if len(links) == 1:
            try:
                info = get_video_info(links[0], cookie_path)
                formats = info.get('formats', [])
            except Exception as e:
                flash(f'解析失败: {e}')
            finally:
                if cookie_path: os.remove(cookie_path)
        else:
            results = []
            for u in links:
                try:
                    vu = get_best_video_url(u, cookie_path)
                    results.append(f"{u} {vu}")
                except Exception as e:
                    results.append(f"解析失败 {u} 错误:{e}")
            if cookie_path: os.remove(cookie_path)
            tmpf = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.txt')
            tmpf.write("\n".join(results))
            tmpf.close()
            fid = os.path.basename(tmpf.name)
            parsed_results[fid] = tmpf.name
            download_url = url_for('download_file', file_id=fid)

    return render_template_string(PAGE_TEMPLATE, info=info, formats=formats, download_url=download_url)

@app.route('/download/<file_id>')
def download_file(file_id):
    path = parsed_results.get(file_id)
    if not path or not os.path.exists(path):
        flash('下载文件不存在或已过期')
        return redirect(url_for('index'))
    resp = send_file(path, as_attachment=True, download_name='parsed_results.txt')
    resp.call_on_close(lambda: (os.remove(path), parsed_results.pop(file_id, None)))
    return resp

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
