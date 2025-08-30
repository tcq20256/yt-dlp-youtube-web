# 🎬 yt-dlp-youtube-web

基于 **Python Flask** 的 Web 界面封装工具，支持通过 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 下载视频，适配 Cookie 验证，提供简洁易用的网页端体验。  

- 需要 **Python 3.9+** 环境

---

## 🔑 功能特点
- 🖥️ 提供 Flask Web 界面，一键提交视频链接下载
- 🍪 支持导入 Cookie 验证，更好地兼容登录后资源
- 🎥 内置 `yt-dlp`，支持多站点视频音频下载
- 🎶 支持 `ffmpeg`，可进行音视频转码

---

## 🔗 相关插件与工具

- 📥 导出浏览器 Cookie 插件：  [Get cookies.txt locally](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)

- 📱 Android 视频下载器：  [Seal](https://github.com/JunkFood02/Seal)

- ⚡ 核心下载工具：  [yt-dlp](https://github.com/yt-dlp/yt-dlp)

---

## 📦 安装方法

### 🚀 方法一：一键脚本安装（推荐）

项目内置 `install.sh`，可自动完成依赖安装与环境配置：

```bash
chmod +x install.sh
./install.sh
