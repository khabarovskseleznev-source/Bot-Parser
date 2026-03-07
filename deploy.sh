#!/bin/bash
set -e

VPS_IP="85.239.51.247"
VPS_USER="root"
VPS_DIR="~/intelbot"
LOCAL_DIR="/Users/seleznevevgenij/Documents/Проекты Visual Studio/Projects/Project -10 (Bot- Reserch)"

SSH="ssh -o ConnectTimeout=15 -o BatchMode=yes -i /Users/seleznevevgenij/.ssh/id_rsa"
SCP="scp -o ConnectTimeout=15 -o BatchMode=yes -i /Users/seleznevevgenij/.ssh/id_rsa"

echo "=== [1/4] Загрузка кода на VPS ==="
$SSH "$VPS_USER@$VPS_IP" "mkdir -p ~/intelbot"
cd "$LOCAL_DIR"
tar czf /tmp/intelbot.tar.gz \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='data' \
  --exclude='.git' \
  --exclude='*.pyc' \
  --exclude='logs' \
  .
$SCP /tmp/intelbot.tar.gz "$VPS_USER@$VPS_IP:/tmp/intelbot.tar.gz"
$SSH "$VPS_USER@$VPS_IP" "cd ~/intelbot && tar xzf /tmp/intelbot.tar.gz && rm /tmp/intelbot.tar.gz"
rm /tmp/intelbot.tar.gz

echo "=== [2/4] Копирование .env ==="
$SCP "$LOCAL_DIR/.env" "$VPS_USER@$VPS_IP:$VPS_DIR/.env"

echo "=== [3/4] Установка Docker (если не установлен) ==="
$SSH "$VPS_USER@$VPS_IP" '
  if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
  else
    echo "Docker уже установлен: $(docker --version)"
  fi
'

echo "=== [4/4] Запуск контейнера ==="
$SSH "$VPS_USER@$VPS_IP" "
  cd $VPS_DIR
  docker compose down --remove-orphans 2>/dev/null || true
  docker compose up --build -d
  echo '--- Логи (Ctrl+C для выхода) ---'
  docker compose logs -f bot
"
