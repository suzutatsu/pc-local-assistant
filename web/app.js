const statusHeader = document.getElementById('status-header');
const statusText = document.getElementById('status-text');
const currentTaskDisplay = document.getElementById('current-task-display');
const tasksList = document.getElementById('tasks-list');
const extraContextInput = document.getElementById('extra-context');
const consoleOutput = document.getElementById('console-output');

const queueContainer = document.getElementById('queue-container');
const queueItems = document.getElementById('queue-items');
const resultsList = document.getElementById('results-list');

const askingOverlay = document.getElementById('asking-overlay');
const askingQuestion = document.getElementById('asking-question');
const askingInput = document.getElementById('asking-input');
const askingSubmitBtn = document.getElementById('asking-submit-btn');

let socket;
let currentStatus = 'idle';
let currentSchedules = {};
let currentResults = {};
let allTasks = []; // タスク一覧の保持用

// APIからタスク一覧、スケジュール一覧、実行結果一覧を取得して表示
async function fetchTasksSchedulesAndResults() {
    try {
        const [tasksRes, schedulesRes, resultsRes] = await Promise.all([
            fetch('/api/tasks'),
            fetch('/api/schedules'),
            fetch('/api/results')
        ]);
        
        const tasksData = await tasksRes.json();
        allTasks = tasksData.tasks || [];
        currentSchedules = await schedulesRes.json();
        currentResults = await resultsRes.json();
        
        renderTasks(allTasks);
        renderFinalResults(allTasks);
    } catch (err) {
        console.error('データの取得に失敗しました:', err);
        consoleOutput.innerHTML = `<div class="system-msg" style="color: #ef4444;">APIサーバーとの通信に失敗しました。サーバーが起動しているか確認してください。</div>`;
    }
}

function translateDay(day) {
    const days = {
        'mon': '月曜', 'tue': '火曜', 'wed': '水曜', 'thu': '木曜',
        'fri': '金曜', 'sat': '土曜', 'sun': '日曜'
    };
    return days[day] || day;
}

// 左側：タスク一覧（手動起動とスケジュール設定のみ）の描画
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
        let dayVal = 'mon';
        let showInputStyle = 'style="display:none;"';
        let showDaySelectStyle = 'style="display:none;"';
        let placeholder = '';

        if (schedule) {
            selectVal = schedule.type;
            
            if (schedule.type === 'daily') {
                badgeHtml = `<span class="schedule-badge sched-badge-daily">⏱ 毎日 ${schedule.value}</span>`;
                valInput = schedule.value;
                placeholder = '例: 09:00';
                showInputStyle = '';
            } else if (schedule.type === 'weekly') {
                const parts = schedule.value.split(' ');
                dayVal = parts[0] || 'mon';
                valInput = parts[1] || '';
                badgeHtml = `<span class="schedule-badge sched-badge-interval">📅 毎週 (${translateDay(dayVal)}) ${valInput}</span>`;
                placeholder = '例: 09:00';
                showInputStyle = '';
                showDaySelectStyle = '';
            } else if (schedule.type === 'biweekly') {
                const parts = schedule.value.split(' ');
                dayVal = parts[0] || 'mon';
                valInput = parts[1] || '';
                badgeHtml = `<span class="schedule-badge sched-badge-interval">📅 隔週 (${translateDay(dayVal)}) ${valInput}</span>`;
                placeholder = '例: 09:00';
                showInputStyle = '';
                showDaySelectStyle = '';
            } else if (schedule.type === 'interval') {
                badgeHtml = `<span class="schedule-badge sched-badge-interval">⏳ ${schedule.value}時間ごと</span>`;
                valInput = schedule.value;
                placeholder = '例: 3';
                showInputStyle = '';
            }
        }

        const card = document.createElement('div');
        card.className = 'task-card';
        card.innerHTML = `
            <div class="task-info">
                <h3>${task.name}${badgeHtml}</h3>
                <p>${task.description || '説明なし'}</p>
            </div>
            
            <!-- アクションエリア -->
            <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <button class="run-btn" data-id="${task.id}">タスクを実行</button>
                <button class="toggle-schedule-btn" data-id="${task.id}">📅 スケジュール設定</button>
            </div>
            
            <!-- 定期実行設定フォーム（デフォルト非表示） -->
            <div class="schedule-config-area" id="schedule-config-area-${task.id}" style="display:none;">
                <div class="schedule-form">
                    <!-- タイプ選択 -->
                    <select class="schedule-select" data-id="${task.id}">
                        <option value="none" ${selectVal === 'none' ? 'selected' : ''}>なし (手動のみ)</option>
                        <option value="daily" ${selectVal === 'daily' ? 'selected' : ''}>毎日指定時刻</option>
                        <option value="weekly" ${selectVal === 'weekly' ? 'selected' : ''}>毎週指定曜日</option>
                        <option value="biweekly" ${selectVal === 'biweekly' ? 'selected' : ''}>隔週指定曜日</option>
                        <option value="interval" ${selectVal === 'interval' ? 'selected' : ''}>時間おき</option>
                    </select>
                    
                    <!-- 曜日選択 (毎週・隔週用) -->
                    <select class="schedule-day-select" data-id="${task.id}" ${showDaySelectStyle}>
                        <option value="mon" ${dayVal === 'mon' ? 'selected' : ''}>月曜日</option>
                        <option value="tue" ${dayVal === 'tue' ? 'selected' : ''}>火曜日</option>
                        <option value="wed" ${dayVal === 'wed' ? 'selected' : ''}>水曜日</option>
                        <option value="thu" ${dayVal === 'thu' ? 'selected' : ''}>木曜日</option>
                        <option value="fri" ${dayVal === 'fri' ? 'selected' : ''}>金曜日</option>
                        <option value="sat" ${dayVal === 'sat' ? 'selected' : ''}>土曜日</option>
                        <option value="sun" ${dayVal === 'sun' ? 'selected' : ''}>日曜日</option>
                    </select>
                    
                    <!-- 時刻/間隔の数値入力 -->
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

    document.querySelectorAll('.toggle-schedule-btn').forEach(btn => {
        btn.addEventListener('click', () => toggleScheduleForm(btn.getAttribute('data-id')));
    });

    // スケジュール設定のイベント制御
    document.querySelectorAll('.schedule-select').forEach(select => {
        select.addEventListener('change', (e) => {
            const taskId = select.getAttribute('data-id');
            const daySelect = document.querySelector(`.schedule-day-select[data-id="${taskId}"]`);
            const input = document.querySelector(`.schedule-val-input[data-id="${taskId}"]`);
            const val = e.target.value;
            
            if (val === 'none') {
                daySelect.style.display = 'none';
                input.style.display = 'none';
                input.value = '';
            } else if (val === 'weekly' || val === 'biweekly') {
                daySelect.style.display = 'inline-block';
                input.style.display = 'inline-block';
                input.placeholder = '例: 09:00';
                input.focus();
            } else {
                daySelect.style.display = 'none';
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

// スケジュール設定アコーディオンの開閉トグル
function toggleScheduleForm(taskId) {
    const area = document.getElementById(`schedule-config-area-${taskId}`);
    if (area.style.display === 'none') {
        area.style.display = 'block';
    } else {
        area.style.display = 'none';
    }
}

// 右上：タスク最終回答一覧の描画
function renderFinalResults(tasks) {
    resultsList.innerHTML = '';
    if (!tasks || tasks.length === 0) {
        resultsList.innerHTML = '<div class="system-msg">タスクが定義されていません。</div>';
        return;
    }

    tasks.forEach(task => {
        const result = currentResults[task.id];
        const card = document.createElement('div');
        card.className = 'result-card';
        card.setAttribute('data-id', task.id);
        
        if (result) {
            const isSuccess = result.status === 'success';
            const statusClass = isSuccess ? 'result-status-success' : 'result-status-failed';
            const statusText = isSuccess ? '成功' : '失敗';
            
            card.innerHTML = `
                <div class="result-card-header">
                    <span class="result-card-title">${task.name}</span>
                    <div>
                        <span style="margin-right: 8px; font-weight: normal; color: #71717a;">${result.timestamp}</span>
                        <span class="result-status-indicator ${statusClass}">${statusText}</span>
                    </div>
                </div>
                <div class="result-card-body">${escapeHtml(result.result)}</div>
            `;
        } else {
            card.innerHTML = `
                <div class="result-card-header">
                    <span class="result-card-title">${task.name}</span>
                    <span class="result-status-indicator" style="background-color: #f4f4f5; color: #71717a;">未実行</span>
                </div>
                <div class="result-card-body" style="color: #a1a1aa; font-style: italic;">まだタスクが実行されていません。</div>
            `;
        }
        resultsList.appendChild(card);
    });
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
    const daySelect = document.querySelector(`.schedule-day-select[data-id="${taskId}"]`);
    const input = document.querySelector(`.schedule-val-input[data-id="${taskId}"]`);
    
    const type = select.value;
    let value = input.value.trim();
    
    if (type !== 'none' && !value) {
        alert('実行時刻または時間間隔を入力してください。');
        return;
    }

    if (type === 'weekly' || type === 'biweekly') {
        const day = daySelect.value;
        value = `${day} ${value}`;
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
        renderFinalResults(allTasks);
    } else if (msg.type === 'log') {
        appendLog(msg.data);
    } else if (msg.type === 'status') {
        const { status, current_task, ask_question, queue_list } = msg.data;
        updateUIState(status, current_task, ask_question, queue_list);
    } else if (msg.type === 'task_result') {
        const { task_id, status, timestamp, result } = msg.data;
        currentResults[task_id] = { status, timestamp, result };
        
        // 右上の最終結果一覧の該当カードをリアルタイム更新
        updateResultCardDOM(task_id, status, timestamp, result);
    }
}

// 特定の結果カードDOMを直接更新
function updateResultCardDOM(taskId, status, timestamp, result) {
    const card = document.querySelector(`.result-card[data-id="${taskId}"]`);
    if (!card) return;

    const isSuccess = status === 'success';
    const statusClass = isSuccess ? 'result-status-success' : 'result-status-failed';
    const statusText = isSuccess ? '成功' : '失敗';

    // 対象タスクのタイトルを取得
    const task = allTasks.find(t => t.id === taskId);
    const taskName = task ? task.name : taskId;

    card.innerHTML = `
        <div class="result-card-header">
            <span class="result-card-title">${taskName}</span>
            <div>
                <span style="margin-right: 8px; font-weight: normal; color: #71717a;">${timestamp}</span>
                <span class="result-status-indicator ${statusClass}">${statusText}</span>
            </div>
        </div>
        <div class="result-card-body">${escapeHtml(result)}</div>
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
