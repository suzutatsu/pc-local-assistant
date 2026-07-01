const statusHeader = document.getElementById('status-header');
const statusText = document.getElementById('status-text');
const currentTaskDisplay = document.getElementById('current-task-display');
const tasksList = document.getElementById('tasks-list');
const extraContextInput = document.getElementById('extra-context');
const consoleOutput = document.getElementById('console-output');

const askingOverlay = document.getElementById('asking-overlay');
const askingQuestion = document.getElementById('asking-question');
const askingInput = document.getElementById('asking-input');
const askingSubmitBtn = document.getElementById('asking-submit-btn');

let socket;
let currentStatus = 'idle';

// APIからタスク一覧を取得して表示
async function fetchTasks() {
    try {
        const res = await fetch('/api/tasks');
        const data = await res.json();
        renderTasks(data.tasks);
    } catch (err) {
        console.error('タスク一覧の取得に失敗しました:', err);
        consoleOutput.innerHTML = `<div class="system-msg" style="color: #ef4444;">APIサーバーとの通信に失敗しました。サーバーが起動しているか確認してください。</div>`;
    }
}

function renderTasks(tasks) {
    tasksList.innerHTML = '';
    if (!tasks || tasks.length === 0) {
        tasksList.innerHTML = '<p>実行可能なタスクが定義されていません。</p>';
        return;
    }
    
    tasks.forEach(task => {
        const card = document.createElement('div');
        card.className = 'task-card';
        card.innerHTML = `
            <div class="task-info">
                <h3>${task.name}</h3>
                <p>${task.description || '説明なし'}</p>
            </div>
            <button class="run-btn" data-id="${task.id}">タスクを実行</button>
        `;
        tasksList.appendChild(card);
    });
    
    // イベントリスナーの追加
    document.querySelectorAll('.run-btn').forEach(btn => {
        btn.addEventListener('click', () => runTask(btn.getAttribute('data-id')));
    });
    
    updateButtonStates();
}

// タスクの起動
async function runTask(taskId) {
    if (currentStatus === 'running' || currentStatus === 'asking') return;
    
    const context = extraContextInput.value;
    try {
        const res = await fetch('/api/tasks/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: taskId, context_info: context })
        });
        
        if (!res.ok) {
            const errData = await res.json();
            alert(`起動エラー: ${errData.detail}`);
        } else {
            extraContextInput.value = ''; // 実行後にクリア
        }
    } catch (err) {
        alert('タスクの起動に失敗しました。');
    }
}

// ボタンの無効化/有効化状態の更新
function updateButtonStates() {
    const isBusy = currentStatus === 'running' || currentStatus === 'asking';
    document.querySelectorAll('.run-btn').forEach(btn => {
        btn.disabled = isBusy;
    });
    extraContextInput.disabled = isBusy;
}

// WebSocketのセットアップ
function setupWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    socket = new WebSocket(wsUrl);
    
    socket.onopen = () => {
        console.log('WebSocket connected');
    };
    
    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleSocketMessage(msg);
    };
    
    socket.onclose = () => {
        console.log('WebSocket disconnected. Reconnecting...');
        setTimeout(setupWebSocket, 3000);
    };
}

// ログ出力の追加
function appendLog(text) {
    const line = document.createElement('div');
    line.textContent = text;
    consoleOutput.appendChild(line);
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
}

// WebSocketメッセージの処理
function handleSocketMessage(msg) {
    if (msg.type === 'init') {
        const { status, current_task, ask_question, log_history } = msg.data;
        consoleOutput.innerHTML = '';
        if (log_history && log_history.length > 0) {
            log_history.forEach(log => appendLog(log));
        } else {
            appendLog('ログ接続成功。エージェント待機中...');
        }
        updateUIState(status, current_task, ask_question);
    } else if (msg.type === 'log') {
        appendLog(msg.data);
    } else if (msg.type === 'status') {
        const { status, current_task, ask_question } = msg.data;
        updateUIState(status, current_task, ask_question);
    }
}

// ステータスに応じたUIのアップデート
function updateUIState(status, currentTask, askQuestion) {
    currentStatus = status;
    updateButtonStates();
    
    statusHeader.className = '';
    
    let text = '待機中';
    switch (status) {
        case 'idle':
            statusHeader.classList.add('status-idle');
            text = '待機中';
            currentTaskDisplay.classList.add('hidden');
            askingOverlay.classList.add('hidden');
            break;
        case 'running':
            statusHeader.classList.add('status-running');
            text = `実行中`;
            currentTaskDisplay.classList.remove('hidden');
            currentTaskDisplay.textContent = currentTask ? `現在のタスク: ${currentTask}` : '';
            askingOverlay.classList.add('hidden');
            break;
        case 'asking':
            statusHeader.classList.add('status-asking');
            text = 'ユーザーの確認・入力待ち';
            currentTaskDisplay.classList.remove('hidden');
            currentTaskDisplay.textContent = currentTask ? `現在のタスク: ${currentTask}` : '';
            
            askingOverlay.classList.remove('hidden');
            askingQuestion.textContent = askQuestion || '認証情報を入力してください。';
            askingInput.value = '';
            // オーバーレイ表示直後に入力フォームにフォーカス
            setTimeout(() => {
                askingInput.focus();
            }, 100);
            break;
        case 'success':
            statusHeader.classList.add('status-success');
            text = 'タスク完了 (成功)';
            currentTaskDisplay.classList.add('hidden');
            askingOverlay.classList.add('hidden');
            break;
        case 'failed':
            statusHeader.classList.add('status-failed');
            text = 'エラー終了';
            currentTaskDisplay.classList.add('hidden');
            askingOverlay.classList.add('hidden');
            break;
    }
    
    statusText.textContent = text;
}

// ユーザーの回答送信
function submitAnswer() {
    const answer = askingInput.value.trim();
    if (!answer) return;
    
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'respond',
            data: { answer: answer }
        }));
    } else {
        fetch('/api/ask_user/respond', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answer: answer })
        });
    }
    askingInput.value = '';
    askingOverlay.classList.add('hidden');
}

// イベントリスナー
askingSubmitBtn.addEventListener('click', submitAnswer);
askingInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        submitAnswer();
    }
});

// 初期化実行
fetchTasks();
setupWebSocket();
