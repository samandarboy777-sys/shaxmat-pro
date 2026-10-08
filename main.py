import os
import math
import asyncio
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import chess
import chess.engine
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ==================== SOZLAMALAR VA BOT TOKEN ==================== #
# O'zingizning @BotFather bergan bot tokeningizni shu yerga qo'ying:
BOT_TOKEN = os.getenv("BOT_TOKEN", "8927652673:AAGnNDYFug8WjzzyDGFIoiYkTu4iRfWEnqA")

# Render bergan domeningiz (yoki avtomatik muhitdan oladi)
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stockfish yo'li (Render Linux va Windows uchun)
if os.path.exists("./stockfish_linux"):
    STOCKFISH_PATH = "./stockfish_linux"
elif os.path.exists("/usr/games/stockfish"):
    STOCKFISH_PATH = "/usr/games/stockfish"
elif os.path.exists("/usr/bin/stockfish"):
    STOCKFISH_PATH = "/usr/bin/stockfish"
else:
    STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "stockfish.exe")

# ==================== TELEGRAM BOT LOGIKASI (AIOGRAM) ==================== #
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN and "BU_YERGA" not in BOT_TOKEN else None
dp = Dispatcher() if bot else None

if dp and bot:
    @dp.message(CommandStart())
    async def start_handler(message: types.Message):
        # WebApp ochiladigan manzil
        web_url = RENDER_EXTERNAL_URL if RENDER_EXTERNAL_URL else "https://telegram.org"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="♟ Shaxmat o‘ynash (Mini App)",
                    web_app=WebAppInfo(url=web_url)
                )
            ]
        ])
        await message.answer(
            f"Assalomu alaykum, {message.from_user.first_name}!\n\n"
            "♟ <b>Shaxmat Pro</b> platformasiga xush kelibsiz.\n"
            "• 5 xil qiyinchilikdagi Stockfish AI bilan o'ynang\n"
            "• Do'stingiz bilan real-vaqtda onlayn bellashing\n"
            "• O'yindan so'ng har bir yurishni chuqur tahlil qiling!\n\n"
            "<i>Muallif: Reyimbayev Baxram Maxsudovich</i>\n\n"
            "O'yinni boshlash uchun quyidagi tugmani bosing:",
            reply_markup=kb,
            parse_mode="HTML"
        )

# ==================== SERVERNI 24/7 UYG'OQ USHLASH (KEEP-ALIVE) ==================== #
async def keep_alive_ping():
    await asyncio.sleep(30)
    while True:
        try:
            target_url = RENDER_EXTERNAL_URL if RENDER_EXTERNAL_URL else "http://127.0.0.1:10000"
            async with httpx.AsyncClient() as client:
                await client.get(f"{target_url}/ping", timeout=10.0)
                print("[Keep-Alive] Ping muvaffaqiyatli yuborildi.")
        except Exception as e:
            print(f"[Keep-Alive] Ping xatosi: {e}")
        await asyncio.sleep(300)

async def start_telegram_bot():
    if bot and dp:
        print("[Telegram Bot] Bot ishga tushmoqda...")
        try:
            await dp.start_polling(bot)
        except Exception as e:
            print(f"[Telegram Bot] Xatolik: {e}")

@app.on_event("startup")
async def startup_event():
    # 1. 24/7 uyg'oq turish signalini fonda yoqish
    asyncio.create_task(keep_alive_ping())
    # 2. Telegram botni fonda ishga tushirish
    if bot and dp:
        asyncio.create_task(start_telegram_bot())

@app.get("/ping")
def ping():
    return {"status": "alive", "message": "Server faol ishlamoqda!"}

# ==================== 1. AI BILAN O'YIN (5 TA DARAJA) ==================== #
class MoveRequest(BaseModel):
    fen: str
    level: int

LEVEL_SETTINGS = {
    1: {"skill": 0, "depth": 1},
    2: {"skill": 4, "depth": 3},
    3: {"skill": 9, "depth": 6},
    4: {"skill": 14, "depth": 10},
    5: {"skill": 20, "depth": 15},
}

@app.post("/api/bot-move")
def bot_move(data: MoveRequest):
    board = chess.Board(data.fen)
    if board.is_game_over():
        return {"status": "game_over"}

    setting = LEVEL_SETTINGS.get(data.level, LEVEL_SETTINGS[3])
    with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
        engine.configure({"Skill Level": setting["skill"]})
        result = engine.play(board, chess.engine.Limit(depth=setting["depth"]))
        best_move = result.move

    return {
        "from": chess.square_name(best_move.from_square),
        "to": chess.square_name(best_move.to_square),
        "san": board.san(best_move)
    }

# ==================== 2. O'YIN TAHLILI (STOCKFISH) ==================== #
class AnalysisRequest(BaseModel):
    moves: List[str]

def win_percent(cp):
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)

def generate_uz_comment(board_before, move, cat, is_check, is_capture, best_san):
    if board_before.is_checkmate():
        return "Mot! O'yin yakunlandi — ajoyib g'alaba!"
    if is_check:
        return "Shoh! Raqib shohiga to'g'ridan-to'g'ri xavf."
        
    if cat == "best":
        return "Eng yaxshi yurish — Stockfish tavsiyasi bilan bir xil!"
    elif cat == "excellent":
        return "A'lo yurish — pozitsiya mustahkam ushlab turilibdi."
    elif cat == "good":
        return "Yaxshi yurish."
    elif cat == "inaccuracy":
        return f"Noaniqlik. Bu vaziyatda yaxshiroq variant: {best_san}"
    elif cat == "mistake":
        return f"Xato! Kuchsiz yurish. Tavsiya etilgan eng yaxshi yurish: {best_san}"
    elif cat == "blunder":
        return f"Qo'pol xato! Katta moddiy yoki pozitsion yo'qotish. To'g'ri yurish: {best_san}"
    return "O'rinli yurish."

@app.post("/api/analyze")
def analyze_game(data: AnalysisRequest):
    board = chess.Board()
    evaluations = []
    white_diffs = []
    black_diffs = []

    with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
        for idx, move_san in enumerate(data.moves):
            try:
                move = board.parse_san(move_san)
            except ValueError:
                break

            turn = board.turn
            board_before = board.copy()
            
            info_before = engine.analyse(board, chess.engine.Limit(depth=10))
            score_before = info_before["score"].white().score(mate_score=10000) or 0
            best_move_engine = info_before.get("pv", [None])[0]
            best_san = board.san(best_move_engine) if best_move_engine else move_san

            is_capture = board.is_capture(move)
            board.push(move)
            is_check = board.is_check()

            info_after = engine.analyse(board, chess.engine.Limit(depth=10))
            score_after = info_after["score"].white().score(mate_score=10000) or 0

            if turn == chess.WHITE:
                diff = win_percent(score_after) - win_percent(score_before)
                white_diffs.append(max(0, 100 + diff))
            else:
                diff = win_percent(-score_after) - win_percent(-score_before)
                black_diffs.append(max(0, 100 + diff))

            if move == best_move_engine or diff > -1.5:
                cat = "best"
                symbol = "★"
            elif diff >= -3.5:
                cat = "excellent"
                symbol = "◆"
            elif diff >= -7.0:
                cat = "good"
                symbol = "!"
            elif diff >= -15.0:
                cat = "inaccuracy"
                symbol = "?!"
            elif diff >= -30.0:
                cat = "mistake"
                symbol = "?"
            else:
                cat = "blunder"
                symbol = "??"

            comment = generate_uz_comment(board_before, move, cat, is_check, is_capture, best_san)
            eval_formatted = f"+{score_after/100:.1f}" if score_after > 0 else f"{score_after/100:.1f}"

            evaluations.append({
                "index": idx,
                "san": move_san,
                "fen": board.fen(),
                "from": chess.square_name(move.from_square),
                "to": chess.square_name(move.to_square),
                "best_from": chess.square_name(best_move_engine.from_square) if best_move_engine else "",
                "best_to": chess.square_name(best_move_engine.to_square) if best_move_engine else "",
                "best_san": best_san,
                "color": "white" if turn == chess.WHITE else "black",
                "cat": cat,
                "symbol": symbol,
                "eval": eval_formatted,
                "comment": comment
            })

    white_acc = round(sum(white_diffs) / len(white_diffs), 1) if white_diffs else 100.0
    black_acc = round(sum(black_diffs) / len(black_diffs), 1) if black_diffs else 100.0

    return {
        "white_accuracy": min(100.0, white_acc),
        "black_accuracy": min(100.0, black_acc),
        "evaluations": evaluations
    }

# ==================== 3. REAL-TIME XONALAR (WEBSOCKETS) ==================== #
rooms: Dict[str, List[WebSocket]] = {}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    if room_id not in rooms:
        rooms[room_id] = []
    
    if len(rooms[room_id]) >= 2:
        await websocket.send_json({"type": "error", "message": "Xona to'la!"})
        await websocket.close()
        return

    rooms[room_id].append(websocket)
    role = "white" if len(rooms[room_id]) == 1 else "black"
    await websocket.send_json({"type": "start", "role": role})

    try:
        while True:
            data = await websocket.receive_json()
            for conn in rooms[room_id]:
                if conn != websocket:
                    await conn.send_json(data)
    except WebSocketDisconnect:
        rooms[room_id].remove(websocket)
        if not rooms[room_id]:
            del rooms[room_id]

# Frontend statik fayllarini tarqatish
app.mount("/", StaticFiles(directory=os.path.dirname(__file__), html=True), name="static")
