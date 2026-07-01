import os
import sys
import asyncio
import json
import datetime
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

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
        
        # 実行待ちキューのリスト
        self.queue_list = []  # List[Dict[str, Any]]: [{"task_id": "...", "name": "...", "context_info": "..."}]
        
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
            
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast({"type": "log", "data": cleaned_msg}))
        except RuntimeError:
            pass

    def broadcast_status(self):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast({
                "type": "status",
                "data": {
                    "status": self.status,
                    "current_task": self.current_task,
                    "ask_question": self.ask_question,
                    "queue_list": self.queue_list
                }
            }))
        except RuntimeError:
            pass

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
        # スケジュールと実行結果も初期化時に送信
        schedules = load_schedules_from_file()
        results = load_results_from_file()
        
        await websocket.send_json({
            "type": "init",
            "data": {
                "status": self.status,
                "current_task": self.current_task,
                "ask_question": self.ask_question,
                "log_history": self.log_history,
                "queue_list": self.queue_list,
                "schedules": schedules,
                "results": results
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
        if message and message != '\n':
            self.callback(message)

    def flush(self):
        self.original_stream.flush()

    def isatty(self):
        return False

# sys.stdout と sys.stderr のリダイレクト設定
sys.stdout = StdoutRedirector(sys.stdout, state.add_log)
sys.stderr = StdoutRedirector(sys.stderr, state.add_log)

# ==================== 非同期キューとワーカー ====================
task_queue = asyncio.Queue()

async def enqueue_task(task_id: str, context_info: str = ""):
    # 既にキューにあるか確認
    if any(item["task_id"] == task_id for item in state.queue_list):
        state.add_log(f"通知: タスク {task_id} はすでに実行待ちキューに存在するため、追加をスキップしました。")
        return False
        
    # 現在実行中のタスクと同じ場合もスキップ（二重実行防止）
    tasks = load_tasks()
    selected_task = next((t for t in tasks if t.get("id") == task_id), None)
    if not selected_task:
        state.add_log(f"エラー: タスク {task_id} が見つかりません。")
        return False
        
    if state.current_task == selected_task.get("name"):
        state.add_log(f"通知: タスク {selected_task.get('name')} は現在実行中のため、追加をスキップしました。")
        return False

    item = {
        "task_id": task_id,
        "name": selected_task.get("name"),
        "context_info": context_info
    }
    state.queue_list.append(item)
    state.broadcast_status()
    
    await task_queue.put(item)
    state.add_log(f"タスクをキューに追加しました: {selected_task.get('name')}")
    return True

async def task_worker():
    state.add_log("実行待ちキュー監視ワーカーを起動しました。")
    while True:
        try:
            item = await task_queue.get()
            task_id = item["task_id"]
            context_info = item["context_info"]
            
            # キューリストから削除
            state.queue_list = [i for i in state.queue_list if i["task_id"] != task_id]
            state.broadcast_status()
            
            # タスクを実行
            await execute_agent_task(task_id, context_info)
            
            task_queue.task_done()
        except Exception as e:
            state.add_log(f"ワーカー内部エラー: {e}")
            await asyncio.sleep(2)

# ==================== スケジューラーと永続化 ====================
scheduler = AsyncIOScheduler()
SCHEDULES_FILE = os.path.join(CURRENT_DIR, "schedules.json")
RESULTS_FILE = os.path.join(CURRENT_DIR, "results.json")

def load_schedules_from_file() -> Dict[str, Any]:
    if not os.path.exists(SCHEDULES_FILE):
        return {}
    try:
        with open(SCHEDULES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"スケジュールファイル読み込みエラー: {e}")
        return {}

def save_schedules_to_file(schedules: Dict[str, Any]):
    try:
        with open(SCHEDULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(schedules, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"スケジュールファイル保存エラー: {e}")

# ==================== 実行結果の永続化 ====================
def load_results_from_file() -> List[Dict[str, Any]]:
    if not os.path.exists(RESULTS_FILE):
        return []
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"結果ファイル読み込みエラー: {e}")
        return []

def save_result_to_file(task_id: str, status: str, result_text: str):
    results = load_results_from_file()
    
    tasks = load_tasks()
    selected_task = next((t for t in tasks if t.get("id") == task_id), None)
    task_name = selected_task.get("name") if selected_task else task_id
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_result = {
        "task_id": task_id,
        "task_name": task_name,
        "status": status,
        "timestamp": timestamp,
        "result": result_text
    }
    
    # 先頭に追加（最新順）
    results.insert(0, new_result)
    
    # 履歴件数を50件に制限
    results = results[:50]
    
    try:
        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"結果ファイル保存エラー: {e}")

async def scheduled_task_job(task_id: str):
    schedules = load_schedules_from_file()
    sched = schedules.get(task_id, {})
    sched_type = sched.get("type")
    
    if sched_type == "biweekly":
        # 隔週の判定: results.json（リスト）から該当タスクの最新の実行結果を探す
        results = load_results_from_file()
        last_run = next((r for r in results if r.get("task_id") == task_id), None)
        if last_run and last_run.get("timestamp"):
            try:
                last_time = datetime.datetime.strptime(last_run["timestamp"], "%Y-%m-%d %H:%M:%S")
                delta = datetime.datetime.now() - last_time
                if delta.days < 13:
                    state.add_log(f"[スケジュールスキップ]: タスク {task_id} は隔週設定ですが、前回実行（{last_run['timestamp']}）から2週間経過していないためスキップします。")
                    return
            except Exception as e:
                # 解析に失敗した場合は念のため実行する
                pass

    state.add_log(f"[スケジュール起動]: タスク {task_id} の自動実行時刻になりました。")
    await enqueue_task(task_id)

def apply_schedule_to_scheduler(task_id: str, sched_type: str, value: Any):
    if scheduler.get_job(task_id):
        scheduler.remove_job(task_id)
        
    if sched_type == "daily":
        try:
            hour, minute = map(int, value.split(":"))
            scheduler.add_job(
                scheduled_task_job,
                CronTrigger(hour=hour, minute=minute),
                id=task_id,
                args=[task_id]
            )
            return True
        except Exception as e:
            state.add_log(f"エラー: 定期実行設定(daily)の解析に失敗しました ({value}): {e}")
    elif sched_type == "weekly" or sched_type == "biweekly":
        # value: "mon 09:00" など
        try:
            day_of_week, time_str = value.split()
            hour, minute = map(int, time_str.split(":"))
            # 隔週(biweekly)の場合も、実行自体は毎週同じ曜日/時刻にトリガーさせ、ジョブ内でスキップ判定を行う
            scheduler.add_job(
                scheduled_task_job,
                CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute),
                id=task_id,
                args=[task_id]
            )
            return True
        except Exception as e:
            state.add_log(f"エラー: 定期実行設定({sched_type})の解析に失敗しました ({value}): {e}")
    elif sched_type == "interval":
        try:
            hours = int(value)
            scheduler.add_job(
                scheduled_task_job,
                IntervalTrigger(hours=hours),
                id=task_id,
                args=[task_id]
            )
            return True
        except Exception as e:
            state.add_log(f"エラー: 定期実行設定(interval)の解析に失敗しました ({value}時間): {e}")
    return False

def init_schedules():
    schedules = load_schedules_from_file()
    for task_id, sched in schedules.items():
        sched_type = sched.get("type")
        value = sched.get("value")
        if sched_type and value and sched_type != "none":
            apply_schedule_to_scheduler(task_id, sched_type, value)

# ==================== FastAPI イベントハンドラー ====================
@app.on_event("startup")
async def startup_event():
    # キュー監視ワーカー起動
    asyncio.create_task(task_worker())
    # スケジュール復元と開始
    init_schedules()
    scheduler.start()
    state.add_log("バックグラウンドスケジューラーを起動しました。")

# ==================== API ルーティング ====================

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
        "ask_question": state.ask_question,
        "queue_list": state.queue_list
    }

class TaskRunRequest(BaseModel):
    task_id: str
    context_info: str = ""

# エージェント実行処理 (ワーカーから順次呼び出される)
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

        llm, model_name = initialize_llm()
        profile_path = os.path.join(CURRENT_DIR, "browser_profile")
        os.makedirs(profile_path, exist_ok=True)

        def web_ask_user(question):
            state.ask_question = question
            state.set_status("asking")
            state.ask_answer = None
            state.ask_event.clear()
            
            state.add_log(f"[ユーザー入力要求]: {question}")
            
            loop = asyncio.get_event_loop()
            future = asyncio.run_coroutine_threadsafe(wait_for_answer(), loop)
            return future.result()

        async def wait_for_answer():
            await state.ask_event.wait()
            return state.ask_answer

        final_res = await run_sequence(
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
        
        # 最終結果の保存
        save_result_to_file(task_id, "success", final_res)
        
        # クライアントへ最終結果をブロードキャスト
        task_name = selected_task.get("name") if selected_task else task_id
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        asyncio.create_task(state.broadcast({
            "type": "task_result",
            "data": {
                "task_id": task_id,
                "task_name": task_name,
                "status": "success",
                "timestamp": timestamp,
                "result": final_res
            }
        }))
        
    except Exception as e:
        state.add_log(f"システムエラーが発生しました: {e}")
        state.set_status("failed")
        
        error_msg = f"システムエラー: {e}"
        save_result_to_file(task_id, "failed", error_msg)
        
        tasks = load_tasks()
        selected_task = next((t for t in tasks if t.get("id") == task_id), None)
        task_name = selected_task.get("name") if selected_task else task_id
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        asyncio.create_task(state.broadcast({
            "type": "task_result",
            "data": {
                "task_id": task_id,
                "task_name": task_name,
                "status": "failed",
                "timestamp": timestamp,
                "result": error_msg
            }
        }))
    finally:
        state.current_task = None
        state.ask_question = None
        state.broadcast_status()

@app.post("/api/tasks/run")
async def run_task(req: TaskRunRequest):
    success = await enqueue_task(req.task_id, req.context_info)
    if not success:
        raise HTTPException(status_code=400, detail="既に実行待ちか、現在稼働中のタスクです。")
    return {"message": "タスクをキューに追加しました。"}

# ==================== スケジュールAPI ====================

@app.get("/api/schedules")
async def get_schedules():
    return load_schedules_from_file()

class ScheduleSettings(BaseModel):
    task_id: str
    type: str  # "daily", "interval", "none"
    value: str  # "09:00" または "3" (時間)

@app.post("/api/schedules")
async def set_schedule(req: ScheduleSettings):
    schedules = load_schedules_from_file()
    
    if req.type == "none":
        if req.task_id in schedules:
            del schedules[req.task_id]
        if scheduler.get_job(req.task_id):
            scheduler.remove_job(req.task_id)
        save_schedules_to_file(schedules)
        state.add_log(f"スケジュールを解除しました: タスク {req.task_id}")
        return {"message": "スケジュールを削除しました。"}
        
    success = apply_schedule_to_scheduler(req.task_id, req.type, req.value)
    if not success:
        raise HTTPException(status_code=400, detail="スケジュール設定の解析に失敗しました。")
        
    schedules[req.task_id] = {
        "type": req.type,
        "value": req.value
    }
    save_schedules_to_file(schedules)
    
    readable_type = "毎日" if req.type == "daily" else "インターバル"
    readable_val = req.value + ("" if req.type == "daily" else "時間ごと")
    state.add_log(f"スケジュールを設定しました: タスク {req.task_id} ({readable_type} {readable_val})")
    
    return {"message": "スケジュールを設定しました。"}

@app.delete("/api/schedules/{task_id}")
async def delete_schedule(task_id: str):
    schedules = load_schedules_from_file()
    if task_id in schedules:
        del schedules[task_id]
        save_schedules_to_file(schedules)
    if scheduler.get_job(task_id):
        scheduler.remove_job(task_id)
    state.add_log(f"スケジュールを解除しました: タスク {task_id}")
    return {"message": "スケジュールを削除しました。"}

# ==================== 実行結果API ====================

@app.get("/api/results")
async def get_results():
    return load_results_from_file()

# ==================== WebSocket ====================

class RespondRequest(BaseModel):
    answer: str

@app.post("/api/ask_user/respond")
async def respond_to_agent(req: RespondRequest):
    if state.status != "asking":
        raise HTTPException(status_code=400, detail="現在エージェントは入力を求めていません。")
    
    state.ask_answer = req.answer
    state.ask_question = None
    state.set_status("running")
    state.ask_event.set()
    return {"message": "回答を受け付けました。エージェントを再開します。"}

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

# 静的ファイルルーティング
if os.path.exists(WEB_DIR):
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
