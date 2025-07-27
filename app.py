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

# 页面模板，支持单链接详情与批量解析下载
PAGE_TEMPLATE = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>YouTube 多功能解析器</title>
<style>
/* 样式保持一致，省略重复，可按需调整 */
 body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif; background: #f0f4f8; margin: 0; min-height: 100vh; display: flex; justify-content: center; align-items: center; color: #333; padding: 20px; box-sizing: border-box; }
.container { background: #fff; padding: 40px 48px; border-radius: 16px; box-shadow: 0 12px 30px rgb(0 0 0 / 0.1); width: 100%; max-width: 700px; box-sizing: border-box; text-align: center; }
 h1 { font-weight: 700; font-size: 28px; margin-bottom: 40px; user-select: none; color: #222; }
 form { display: flex; flex-direction: column; gap: 20px; }
 label { font-size: 16px; color: #555; user-select: none; text-align: left; margin: 0 auto; max-width: 600px; }
 input[type=file], textarea { margin: 0 auto; font-size: 16px; max-width: 600px; width: 90%; padding: 8px 12px; border: 2px solid #3b82f6; border-radius: 8px; box-shadow: inset 0 4px 12px rgb(0 0 0 / 0.1); outline: none; resize: vertical; transition: border-color 0.3s ease, box-shadow 0.3s ease; box-sizing: border-box; }
 button { width: 220px; padding: 16px 0; margin: 0 auto; font-size: 22px; font-weight: 700; color: white; background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%); border: none; border-radius: 14px; cursor: pointer; box-shadow: 0 6px 18px rgb(59 130 246 / 0.6); transition: background 0.3s ease, box-shadow 0.3s ease; user-select: none; }
 .error { margin-top: 24px; color: #dc2626; font-weight: 600; }
 a.download-link { display: block; margin-top: 30px; font-size: 18px; color: #3b82f6; text-decoration: none; }
/* 响应式省略 */
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
        <img src="{{ info.thumbnail }}" alt="封面" style="max-width:320px;border-radius:12px;box-shadow:0 6px 12px rgb(0 0 0 / 0.08);"/>
        <p>时长: {{ info.duration }}秒</p>
        <button onclick="window.open('{{ info.url }}','_blank')">⬇️ 下载最佳画质</button>
        <h3>更多格式</h3>
        <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:14px;">
          {% for f in formats %}
            {% if f.vcodec!='none' %}
              <a class="download-link" href="{{ f.url }}" target="_blank" download>{{ f.format_note or f.format }}({{ f.ext }}){% if f.filesize %}-{{ (f.filesize/1024/1024)|round(2) }}MB{% endif %}{% if f.acodec=='none' %}🔇{% endif %}</a>
            {% endif %}
          {% endfor %}
        </div>
      </div>
    {% endif %}
    {% if download_url %}
      <a class="download-link" href="{{ download_url }}" download>⬇️ 下载批量解析结果</a>
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
        # 处理 Cookie
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

        links = [l for l in text.splitlines() if l.strip()]
        if len(links)==1:
            try:
                info = get_video_info(links[0], cookie_path)
                formats = info.get('formats', [])
            except Exception as e:
                flash(f'解析失败: {e}')
            finally:
                if cookie_path: os.remove(cookie_path)
        else:
            results=[]
            for u in links:
                try:
                    vu=get_best_video_url(u,cookie_path)
                    results.append(f"{u} {vu}")
                except Exception as e:
                    results.append(f"解析失败 {u} 错误:{e}")
            if cookie_path: os.remove(cookie_path)
            tmpf=tempfile.NamedTemporaryFile(delete=False,mode='w',encoding='utf-8',suffix='.txt')
            tmpf.write("\n".join(results))
            tmpf.close()
            fid=os.path.basename(tmpf.name)
            parsed_results[fid]=tmpf.name
            download_url=url_for('download_file',file_id=fid)

    return render_template_string(PAGE_TEMPLATE, info=info, formats=formats, download_url=download_url)

@app.route('/download/<file_id>')
def download_file(file_id):
    path=parsed_results.get(file_id)
    if not path or not os.path.exists(path):
        flash('下载文件不存在或已过期')
        return redirect(url_for('index'))
    resp=send_file(path,as_attachment=True,download_name='parsed_results.txt')
    resp.call_on_close(lambda: (os.remove(path), parsed_results.pop(file_id, None)))
    return resp

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)))
