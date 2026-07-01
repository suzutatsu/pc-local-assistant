import os
import sys
import asyncio
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# main.py からインポート
from main import load_tasks, initialize_llm, run_sequence

app = FastAPI(title="PC Local Assistant API")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(CURRENT_DIR, "web")
os.makedirs(WEB_DIR, exist_ok=True)

# グローバルステータス管理
class AppState:
    def __init__(self):
        self.status = "idle"  # idle, running, asking, success, failed
        self.current_task = None
        self.log_history = []
        self.max_log_history = 200
        
        # ask_user 同期用
        self.ask_event = asyncio.Event()
        self.ask_question = None
        self.ask_answer = None
        
        # WebSocket接続クライアント
        self.active_connections: List[WebSocket] = []

    def set_status(self, status: str):
        self.status = status
        self.broadcast_status()

    def add_log(self, message: str):
        cleaned_msg = message.rstrip('\n')
        if not cleaned_msg:
            return
        
        self.log_history.append(cleaned_msg)
        if len(self.log_history) > self.max_log_history:
            self.log_history.pop(0)
            
        asyncio.create_task(self.broadcast({"type": "log", "data": cleaned_msg}))

    def broadcast_status(self):
        asyncio.create_task(self.broadcast({
            "type": "status",
            "data": {
                "status": self.status,
                "current_task": self.current_task,
                "ask_question": self.ask_question
            }
        }))

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        await websocket.send_json({
            "type": "init",
            "data": {
                "status": self.status,
                "current_task": self.current_task,
                "ask_question": self.ask_question,
                "log_history": self.log_history
            }
        })

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

state = AppState()

# 標準出力と標準エラーのキャプチャラッパー
class StdoutRedirector:
    def __init__(self, original_stream, callback):
        self.original_stream = original_stream
        self.callback = callback

    def write(self, message):
        self.original_stream.write(message)
        self.original_stream.flush()
        # メッセージがただの改行コードのみでないかチェック
        if message and message != '\n':
            self.callback(message)

    def flush(self):
        self.original_stream.flush()

    def isatty(self):
        return False

# sys.stdout と sys.stderr のリダイレクト設定
sys.stdout = StdoutRedirector(sys.stdout, state.add_log)
sys.stderr = StdoutRedirector(sys.stderr, state.add_log)

@app.get("/")
async def get_index():
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Web UI index.html not found.</h1>")

@app.get("/web/{file_name:path}")
async def get_web_file(file_name: str):
    file_path = os.path.join(WEB_DIR, file_name)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/api/tasks")
def get_tasks_endpoint():
    tasks = load_tasks()
    return {"tasks": tasks}

@app.get("/api/status")
def get_status_endpoint():
    return {
        "status": state.status,
        "current_task": state.current_task,
        "ask_question": state.ask_question
    }

class TaskRunRequest(BaseModel):
    task_id: str
    context_info: str = ""

# エージェント実行のためのバックグラウンド処理
async def execute_agent_task(task_id: str, context_info: str):
    state.set_status("running")
    state.log_history.clear()
    state.add_log(f"--- タスク実行開始: {task_id} ---")
    
    try:
        tasks = load_tasks()
        selected_task = next((t for t in tasks if t.get("id") == task_id), None)
        if not selected_task:
            state.add_log(f"エラー: タスク {task_id} が見つかりません。")
            state.set_status("failed")
            return

        state.current_task = selected_task.get("name")
        state.broadcast_status()

        # Sequence解析
        is_sequence = selected_task.get("type") == "sequence"
        if is_sequence:
            sequence_steps = selected_task.get("steps", [])
            pass_context = selected_task.get("pass_context", False)
            tasks_to_run = []
            for step_id in sequence_steps:
                step_task = next((t for t in tasks if t.get("id") == step_id), None)
                if step_task:
                    tasks_to_run.append(step_task)
                else:
                    state.add_log(f"エラー: Sequenceのステップ '{step_id}' が見つかりません。")
                    state.set_status("failed")
                    return
        else:
            tasks_to_run = [selected_task]
            pass_context = False

        # LLMの初期化
        llm, model_name = initialize_llm()
        profile_path = os.path.join(CURRENT_DIR, "browser_profile")
        os.makedirs(profile_path, exist_ok=True)

        # Web用の ask_user コールバック関数
        def web_ask_user(question):
            state.ask_question = question
            state.set_status("asking")
            state.ask_answer = None
            state.ask_event.clear()
            
            state.add_log(f"[ユーザー入力要求]: {question}")
            
            # FastAPIのスレッドセーフなループ上で実行を一時停止
            loop = asyncio.get_event_loop()
            future = asyncio.run_coroutine_threadsafe(wait_for_answer(), loop)
            return future.result()

        async def wait_for_answer():
            await state.ask_event.wait()
            return state.ask_answer

        # エージェント実行
        await run_sequence(
            tasks_to_run=tasks_to_run,
            llm=llm,
            browser_profile_path=profile_path,
            ask_user_fn=web_ask_user,
            context_info=context_info,
            pass_context=pass_context,
            model_name=model_name
        )
        
        state.add_log("--- タスク実行完了 ---")
        state.set_status("success")
    except Exception as e:
        state.add_log(f"システムエラーが発生しました: {e}")
        state.set_status("failed")
    finally:
        state.current_task = None
        state.ask_question = None
        state.broadcast_status()

@app.post("/api/tasks/run")
def run_task(req: TaskRunRequest):
    if state.status == "running" or state.status == "asking":
        raise HTTPException(status_code=400, detail="別のタスクが実行中です。")
    
    asyncio.create_task(execute_agent_task(req.task_id, req.context_info))
    return {"message": "タスクを開始しました。"}

class RespondRequest(BaseModel):
    answer: str

@app.post("/api/ask_user/respond")
def respond_to_agent(req: RespondRequest):
    if state.status != "asking":
        raise HTTPException(status_code=400, detail="現在エージェントは入力を求めていません。")
    
    state.ask_answer = req.answer
    state.ask_question = None
    state.set_status("running")
    state.ask_event.set()
    return {"message": "回答を受け付けました。エージェントを再開します。"}

# WebSocketエンドポイント
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await state.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "respond":
                answer = data.get("data", {}).get("answer", "")
                if state.status == "asking":
                    state.ask_answer = answer
                    state.ask_question = None
                    state.set_status("running")
                    state.ask_event.set()
    except WebSocketDisconnect:
        state.disconnect(websocket)
    except Exception as e:
        state.disconnect(websocket)

# 静的ファイルがあるディレクトリをマウント
if os.path.exists(WEB_DIR):
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
