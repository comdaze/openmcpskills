#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 清理已有进程
cleanup() {
    echo "停止服务..."
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null
    exit 0
}
trap cleanup INT TERM

# 检查端口占用
for port in 8000 5173; do
    if fuser $port/tcp >/dev/null 2>&1; then
        echo "⚠️  端口 $port 被占用，正在释放..."
        fuser -k $port/tcp 2>/dev/null || true
        sleep 1
    fi
done

# 启动后端
echo "🚀 启动后端..."
cd "$SCRIPT_DIR/backend"
[ ! -f ".env" ] && cp .env.example .env
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 等待后端就绪
for i in $(seq 1 15); do
    if curl -s --max-time 1 http://localhost:8000/health >/dev/null 2>&1; then
        echo "✅ 后端就绪"
        break
    fi
    [ $i -eq 15 ] && echo "❌ 后端启动超时" && cleanup
    sleep 1
done

# 启动前端
echo "🚀 启动前端..."
cd "$SCRIPT_DIR/frontend"
[ ! -f ".env" ] && echo "VITE_API_BASE_URL=http://localhost:8000" > .env
[ ! -d "node_modules" ] && echo "📦 安装依赖..." && npm install
npm run dev &
FRONTEND_PID=$!

echo ""
echo "========================================="
echo "  前端:     http://localhost:5173"
echo "  后端:     http://localhost:8000"
echo "  API文档:  http://localhost:8000/docs"
echo "========================================="
echo "按 Ctrl+C 停止服务"

wait
