const statusHeader = document.getElementById('status-header');
const statusText = document.getElementById('status-text');
const currentTaskDisplay = document.getElementById('current-task-display');
const tasksList = document.getElementById('tasks-list');
const extraContextInput = document.getElementById('extra-context');
const consoleOutput = document.getElementById('console-output');

const queueContainer = document.getElementById('queue-container');
const queueItems = document.getElementById('queue-items');

const askingOverlay = document.getElementById('asking-overlay');
const askingQuestion = document.getElementById('asking-question');
const askingInput = document.getElementById('asking-input');
const askingSubmitBtn = document.getElementById('asking-submit-btn');

let socket;
let currentStatus = 'idle';
let currentSchedules = {};
let currentResults = {};

// APIからタスク一覧、スケジュール一覧、実行結果一覧を取得して表示
async function fetchTasksSchedulesAndResults() {
    try {
        const [tasksRes, schedulesRes, resultsRes] = await Promise.all([
            fetch('/api/tasks'),
            fetch('/api/schedules'),
            fetch('/api/results')
        ]);
        
        const tasksData = await tasksRes.json();
        currentSchedules = await schedulesRes.json();
        currentResults = await resultsRes.json();
        
        renderTasks(tasksData.tasks);
    } catch (err) {
        console.error('データの取得に失敗しました:', err);
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
        const schedule = currentSchedules[task.id];
        let badgeHtml = '';
        let selectVal = 'none';
        let valInput = '';
        let showInputStyle = 'style="display:none;"';
        let placeholder = '';

        if (schedule) {
            selectVal = schedule.type;
            valInput = schedule.value;
            showInputStyle = '';
            
            if (schedule.type === 'daily') {
                badgeHtml = `<span class="schedule-badge sched-badge-daily">⏱ 毎日 ${schedule.value}</span>`;
                placeholder = '例: 09:00';
            } else if (schedule.type === 'interval') {
                badgeHtml = `<span class="schedule-badge sched-badge-interval">⏳ ${schedule.value}時間ごと</span>`;
                placeholder = '例: 3 (時間)';
            }
        }

        // 前回の実行結果エリアのHTML生成
        const taskResult = currentResults[task.id];
        let resultAreaHtml = '';
        if (taskResult) {
            const isSuccess = taskResult.status === 'success';
            const statusClass = isSuccess ? 'result-status-success' : 'result-status-failed';
            const statusText = isSuccess ? '成功' : '失敗';
            
            resultAreaHtml = `
                <div class="result-container" data-id="${task.id}">
                    <div class="result-header" onclick="toggleResultBody('${task.id}')">
                        <span>前回の実行結果 (${taskResult.timestamp})</span>
                        <span class="result-status-indicator ${statusClass}">${statusText}</span>
                    </div>
                    <div class="result-body" id="result-body-${task.id}">
${escapeHtml(taskResult.result)}
                    </div>
                </div>
            `;
        } else {
            resultAreaHtml = `
                <div class="result-container hidden" data-id="${task.id}">
                    <div class="result-header" onclick="toggleResultBody('${task.id}')">
                        <span>前回の実行結果</span>
                        <span class="result-status-indicator"></span>
                    </div>
                    <div class="result-body" id="result-body-${task.id}"></div>
                </div>
            `;
        }

        const card = document.createElement('div');
        card.className = 'task-card';
        card.innerHTML = `
            <div class="task-info">
                <h3>${task.name}${badgeHtml}</h3>
                <p>${task.description || '説明なし'}</p>
            </div>
            
            <!-- 実行ボタン -->
            <button class="run-btn" data-id="${task.id}">タスクを実行</button>
            
            <!-- 前回の最終結果エリア -->
            ${resultAreaHtml}
            
            <!-- 定期実行設定フォーム -->
            <div class="schedule-config-area">
                <div class="schedule-title-sm">定期実行スケジュールの設定</div>
                <div class="schedule-form">
                    <select class="schedule-select" data-id="${task.id}">
                        <option value="none" ${selectVal === 'none' ? 'selected' : ''}>なし (手動のみ)</option>
                        <option value="daily" ${selectVal === 'daily' ? 'selected' : ''}>毎日指定時刻</option>
                        <option value="interval" ${selectVal === 'interval' ? 'selected' : ''}>時間おき</option>
                    </select>
                    <input type="text" class="schedule-val-input" data-id="${task.id}" value="${valInput}" placeholder="${placeholder}" ${showInputStyle}>
                    <button class="schedule-save-btn" data-id="${task.id}">保存</button>
                    ${schedule ? `<button class="schedule-delete-btn" data-id="${task.id}">解除</button>` : ''}
                </div>
            </div>
        `;
        tasksList.appendChild(card);
    });
    
    // イベントリスナーの追加
    document.querySelectorAll('.run-btn').forEach(btn => {
        btn.addEventListener('click', () => runTask(btn.getAttribute('data-id')));
    });

    // スケジュール設定のイベント制御
    document.querySelectorAll('.schedule-select').forEach(select => {
        select.addEventListener('change', (e) => {
            const taskId = select.getAttribute('data-id');
            const input = document.querySelector(`.schedule-val-input[data-id="${taskId}"]`);
            const val = e.target.value;
            
            if (val === 'none') {
                input.style.display = 'none';
                input.value = '';
            } else {
                input.style.display = 'inline-block';
                input.placeholder = val === 'daily' ? '例: 09:00' : '例: 3 (時間)';
                input.focus();
            }
        });
    });

    document.querySelectorAll('.schedule-save-btn').forEach(btn => {
        btn.addEventListener('click', () => saveSchedule(btn.getAttribute('data-id')));
    });

    document.querySelectorAll('.schedule-delete-btn').forEach(btn => {
        btn.addEventListener('click', () => deleteSchedule(btn.getAttribute('data-id')));
    });
    
    updateButtonStates();
}

// 最終結果表示エリアの開閉トグル
window.toggleResultBody = function(taskId) {
    const body = document.getElementById(`result-body-${taskId}`);
    if (body.style.display === 'none') {
        body.style.display = 'block';
    } else {
        body.style.display = 'none';
    }
}

// HTMLエスケープ処理
function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// スケジュール保存
async function saveSchedule(taskId) {
    const select = document.querySelector(`.schedule-select[data-id="${taskId}"]`);
    const input = document.querySelector(`.schedule-val-input[data-id="${taskId}"]`);
    
    const type = select.value;
    const value = input.value.trim();
    
    if (type !== 'none' && !value) {
        alert('実行時刻または時間間隔を入力してください。');
        return;
    }

    try {
        const res = await fetch('/api/schedules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: taskId, type: type, value: value })
        });
        
        if (!res.ok) {
            const errData = await res.json();
            alert(`設定保存エラー: ${errData.detail}`);
        } else {
            fetchTasksSchedulesAndResults();
        }
    } catch (err) {
        alert('スケジュールの保存に失敗しました。');
    }
}

// スケジュール削除
async function deleteSchedule(taskId) {
    try {
        const res = await fetch(`/api/schedules/${taskId}`, {
            method: 'DELETE'
        });
        
        if (res.ok) {
            fetchTasksSchedulesAndResults();
        } else {
            alert('スケジュールの削除に失敗しました。');
        }
    } catch (err) {
        alert('通信エラーが発生しました。');
    }
}

// タスクの起動 (キューに追加)
async function runTask(taskId) {
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
            extraContextInput.value = '';
        }
    } catch (err) {
        alert('タスクの起動に失敗しました。');
    }
}

function updateButtonStates() {
    document.querySelectorAll('.run-btn').forEach(btn => {
        btn.disabled = false;
    });
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
        const { status, current_task, ask_question, log_history, queue_list, results } = msg.data;
        consoleOutput.innerHTML = '';
        if (log_history && log_history.length > 0) {
            log_history.forEach(log => appendLog(log));
        } else {
            appendLog('ログ接続成功。エージェント待機中...');
        }
        
        if (results) {
            currentResults = results;
        }
        
        updateUIState(status, current_task, ask_question, queue_list);
    } else if (msg.type === 'log') {
        appendLog(msg.data);
    } else if (msg.type === 'status') {
        const { status, current_task, ask_question, queue_list } = msg.data;
        updateUIState(status, current_task, ask_question, queue_list);
    } else if (msg.type === 'task_result') {
        // エージェントが実行完了またはエラー終了した際、最終結果をリアルタイム反映
        const { task_id, status, timestamp, result } = msg.data;
        currentResults[task_id] = { status, timestamp, result };
        updateTaskCardResult(task_id, status, timestamp, result);
    }
}

// 特定のタスクカードの結果表示を更新する
function updateTaskCardResult(taskId, status, timestamp, result) {
    const container = document.querySelector(`.result-container[data-id="${taskId}"]`);
    if (!container) return;

    const isSuccess = status === 'success';
    const statusClass = isSuccess ? 'result-status-success' : 'result-status-failed';
    const statusText = isSuccess ? '成功' : '失敗';

    container.classList.remove('hidden');
    container.innerHTML = `
        <div class="result-header" onclick="toggleResultBody('${taskId}')">
            <span>前回の実行結果 (${timestamp})</span>
            <span class="result-status-indicator ${statusClass}">${statusText}</span>
        </div>
        <div class="result-body" id="result-body-${taskId}" style="display: block;">
${escapeHtml(result)}
        </div>
    `;
}

// ステータスに応じたUIのアップデート
function updateUIState(status, currentTask, askQuestion, queueList) {
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
    renderQueueList(queueList);
}

// 待機キューのレンダリング
function renderQueueList(queueList) {
    queueItems.innerHTML = '';
    if (!queueList || queueList.length === 0) {
        queueContainer.classList.add('hidden');
        return;
    }

    queueContainer.classList.remove('hidden');
    queueList.forEach(item => {
        const badge = document.createElement('span');
        badge.className = 'queue-item-badge';
        badge.textContent = item.name;
        queueItems.appendChild(badge);
    });
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
fetchTasksSchedulesAndResults();
setupWebSocket();
