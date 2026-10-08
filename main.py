import os
import math
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import chess
import chess.engine

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agar Windows bo'lsa .exe, Linux (Render) bo'lsa tizim Stockfish'ini oladi
if os.path.exists("/usr/games/stockfish"):
    STOCKFISH_PATH = "/usr/games/stockfish"
elif os.path.exists("/usr/bin/stockfish"):
    STOCKFISH_PATH = "/usr/bin/stockfish"
else:
    STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "stockfish.exe")

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
                "fen_before": board_before.fen(),
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

app.mount("/", StaticFiles(directory=os.path.dirname(__file__), html=True), name="static")