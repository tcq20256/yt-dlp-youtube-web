#!/bin/bash
set -euo pipefail

APP_NAME="yt-dlp-youtube-web"
APP_PATH="/yt-dlp-youtube-web/app.py"
CONDA_ENV="python39"
LOG_DIR="/yt-dlp-youtube-web/log"
PID_FILE="/tmp/${APP_NAME}.pid"

# 如为 Miniconda，请改为 $HOME/miniconda3/etc/profile.d/conda.sh
CONDA_SH="$HOME/anaconda3/etc/profile.d/conda.sh"

mkdir -p "$LOG_DIR"

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    else
      # 清理陈旧 pid 文件
      rm -f "$PID_FILE"
    fi
  fi
  return 1
}

latest_log() {
  ls -t "$LOG_DIR"/${APP_NAME}_*.log 2>/dev/null | head -n 1
}

status_app() {
  if is_running; then
    echo "✅ $APP_NAME 正在运行 (PID: $(cat "$PID_FILE"))"
  else
    echo "❌ $APP_NAME 未运行"
  fi
  local ll
  ll="$(latest_log || true)"
  [[ -n "${ll:-}" ]] && echo "🗂️ 最新日志文件: $ll"
}

start_app() {
  if is_running; then
    echo "⚠️ $APP_NAME 已在运行 (PID: $(cat "$PID_FILE"))"
    return
  fi
  local ts log_file
  ts="$(date +"%Y-%m-%d_%H%M%S")"
  log_file="$LOG_DIR/${APP_NAME}_${ts}.log"

  echo "🚀 启动 $APP_NAME ..."
  nohup bash -c "
    source '$CONDA_SH'
    conda activate '$CONDA_ENV'
    python '$APP_PATH'
  " >"$log_file" 2>&1 &
  echo $! > "$PID_FILE"
  echo "✅ 已启动，PID: $(cat "$PID_FILE")"
  echo "📝 日志: $log_file"
}

stop_app() {
  if is_running; then
    local pid
    pid="$(cat "$PID_FILE")"
    echo "🛑 停止 $APP_NAME (PID: $pid) ..."
    kill "$pid" 2>/dev/null || true
    # 最多等 5 秒，仍未退出则强杀
    for i in {1..5}; do
      if kill -0 "$pid" 2>/dev/null; then
        sleep 1
      else
        break
      fi
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "⛔ 强制终止..."
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    echo "✅ 已停止"
  else
    echo "❌ $APP_NAME 未运行"
  fi
}

view_logs() {
  local ll
  ll="$(latest_log || true)"
  if [[ -n "${ll:-}" ]]; then
    echo "📜 正在查看最新日志: $ll (Ctrl+C 退出)"
    tail -f "$ll"
  else
    echo "⚠️ 没有找到日志文件"
  fi
}

restart_app() {
  stop_app
  sleep 1
  start_app
}

check_python() {
  echo "🔎 当前运行的 Python 进程："
  ps -ef | grep "[p]ython" || true
  echo
  read -p "请输入要终止的 PID (直接回车跳过): " kill_pid
  if [[ -n "${kill_pid:-}" ]]; then
    if kill -0 "$kill_pid" 2>/dev/null; then
      kill "$kill_pid" 2>/dev/null || true
      # 软杀后稍等再检查
      sleep 1
      if kill -0 "$kill_pid" 2>/dev/null; then
        echo "⛔ 进程未退出，强制终止..."
        kill -9 "$kill_pid" 2>/dev/null || true
      fi
      # 若被杀的是本应用，顺带清理 pid 文件
      if [[ -f "$PID_FILE" ]] && [[ "$(cat "$PID_FILE")" == "$kill_pid" ]]; then
        rm -f "$PID_FILE"
      fi
      echo "✅ 已终止进程 PID: $kill_pid"
    else
      echo "⚠️ 没有找到 PID: $kill_pid"
    fi
  else
    echo "ℹ️ 未输入 PID，跳过终止操作"
  fi
}

echo "========= 管理脚本 ========="
echo "1) 查看状态"
echo "2) 启动程序"
echo "3) 停止程序"
echo "4) 查看实时日志(最新)"
echo "5) 重启程序"
echo "6) 查看 Python 进程并可选择终止"
echo "============================"
read -p "请输入选项 [1-6]: " choice

case "$choice" in
  1) status_app ;;
  2) start_app ;;
  3) stop_app ;;
  4) view_logs ;;
  5) restart_app ;;
  6) check_python ;;
  *) echo "无效选项" ;;
esac
