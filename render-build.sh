#!/usr/bin/env bash
# Tizim paketlarini yangilash va Linux Stockfish o'rnatish
apt-get update && apt-get install -y stockfish
# Python kutubxonalarini o'rnatish
pip install -r requirements.txt