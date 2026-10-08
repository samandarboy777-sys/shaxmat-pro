#!/usr/bin/env bash
set -e

pip install -r requirements.txt

if [ ! -f "stockfish_linux" ]; then
  echo "Linux uchun Stockfish yuklab olinmoqda..."
  curl -L -o stockfish.tar https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-avx2.tar
  tar -xf stockfish.tar
  find . -name "stockfish*" -type f -executable -not -name "*.sh" -not -name "*.tar" -not -name "*.py" -exec cp {} ./stockfish_linux \;
  chmod +x ./stockfish_linux
  echo "Stockfish muvaffaqiyatli o'rnatildi!"
fi
