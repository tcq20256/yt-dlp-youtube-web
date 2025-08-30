# 🎬 yt-dlp-youtube-web

基于 **Python Flask** 的 油管视频预览，仅供测试，适配 Cookie 验证。  

---

## 🔑 环境和功能
- 🐍 需要 **Python 3.9+** 环境
- 🖥️ 提供 Flask Web 界面
- 🍪 支持导入 Cookie 验证


---

## 🔗 相关插件与工具

- 📥 导出浏览器 Cookie 插件：[Get cookies.txt locally](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)

- 📱 Android 视频下载器：[Seal](https://github.com/JunkFood02/Seal)

- ⚡ 核心下载工具：[yt-dlp](https://github.com/yt-dlp/yt-dlp)

---

## 📦 安装方法

### 🚀 方法一：一键脚本安装（推荐）

项目内置 `install.sh`，可自动完成依赖安装与环境配置：

```bash
chmod +x install.sh
./install.sh
```

### 🛠️ 方法二：手动安装（Centos7.6）
#### 👉 http://127.0.0.1:5000

```
curl -O https://repo.anaconda.com/miniconda/Miniconda3-py39_24.7.1-0-Linux-x86_64.sh
bash Miniconda3-py39_24.7.1-0-Linux-x86_64.sh

conda create -n yt-dlp-web python=3.9 -y
conda activate yt-dlp-web

git clone https://github.com/tcq20256/yt-dlp-youtube-web.git
cd yt-dlp-youtube-web
sudo apt update && sudo apt install -y python3 python3-venv python3-pip ffmpeg
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python app.py
```
