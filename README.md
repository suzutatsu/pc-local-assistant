# PC Local Assistant

Mac上で動作する、AI主導のブラウザ操作アシスタントです。
Chromeブラウザを自動操作し、認証が必要な社内ページなどからの情報収集を行います。

## 特徴
- **Web UI ダッシュボード**: ブラウザ（`http://localhost:8000`）からタスクの起動やリアルタイムな実行ログの確認が行えます。
- **一瞥（いちべつ）視認性**: カーソルを合わせなくても遠目から現在の状況（待機中/実行中/エラー/入力要求）が一目でわかるように設計されています。MFAコード等の入力が必要な際は、画面全体を覆う巨大な「入力要求オーバーレイ」が自動で表示されます。
- **Gemini 3.5 Flash**: 高速なGemini 3.5 FlashモデルをGoogle Cloud Vertex AI経由で使用（デフォルト）。
- **browser-use**: 高度なブラウザ操作エージェントライブラリを使用。
- **永続化プロファイル**: `browser_profile` ディレクトリを使用し、ログイン状態やCookieを保持します。

## セットアップ

### 1. 前提条件
- Python 3.11以上推奨
- Google Chromeがインストールされていること

### 2. インストール
```bash
# 仮想環境の作成（推奨）
python3 -m venv venv
source venv/bin/activate

# 依存関係のインストール
pip install -r requirements.txt
playwright install

# 実行権限の付与 (ショートカットスクリプト)
chmod +x run
```

### 3. Google Cloud設定と認証（Service Account）
本ツールはGoogle Cloud Vertex AIを使用します。

1. **Google Cloudプロジェクトの作成・確認**:
   - Google Cloudコンソールでプロジェクトを作成（または既存プロジェクトを選択）します。
   - **Vertex AI API** を有効化します。

2. **サービスアカウントの作成**:
   - 「IAMと管理」 > 「サービスアカウント」で新しいサービスアカウントを作成します。
   - ロールとして **「Vertex AI ユーザー」** (`roles/aiplatform.user`) を付与します。
   - 「キー」タブで **JSONキー** を作成し、ダウンロードします。
   - ダウンロードしたJSONファイルをプロジェクトフォルダに配置します（例: `service_account_key.json`）。
     - ※`.gitignore`により、`*.json` はGitHub等にアップロードされません。

3. **環境変数ファイル（.env）の設定**:
   `.env.example` をコピーして `.env` を作成し、自身のプロジェクト情報を設定してください。

```bash
cp .env.example .env
nano .env
```

```bash
GOOGLE_CLOUD_PROJECT=your-project-id  # プロジェクトID
GOOGLE_CLOUD_REGION=asia-northeast1   # リージョン（必要に応じて変更）
GOOGLE_APPLICATION_CREDENTIALS=./service_account_key.json # 配置したキーファイルのパス
GEMINI_MODEL_NAME=gemini-3.5-flash
TASK_YAML_PATH=./tasks.yaml           # タスク定義ファイルのパス（任意）
JIRA_SERVER=https://your-domain.atlassian.net # JiraのURL（任意）
JIRA_USER_EMAIL=your-email@example.com        # Jiraログイン用メールアドレス（任意）
JIRA_API_TOKEN=your-api-token                 # Atlassian APIトークン（任意）
```

### 4. ローカルモデル (Ollama / Gemma 4) の利用（オプション）
クラウドAPIの代わりにローカルでLLMを実行可能です。最もセットアップが容易で依存関係の少ない **Ollama** をサポートしています。

1. [Ollama 公式サイト](https://ollama.com/) からアプリをインストールします。
2. ターミナルで `ollama run gemma4` を実行し、モデルをダウンロード＆起動します。
3. `.env` ファイルでプロバイダーを切り替えます。
   ```bash
   LLM_PROVIDER=ollama
   OLLAMA_MODEL=gemma4
   ```
（※画像の認識などを行う場合、ローカルPCのGPUリソースを消費しますのでご注意ください）

## カスタムアクションについて
エージェントが使用できる特別なツール（Jira連携やユーザー対話ツールなど）の一覧とその使い方は、[CUSTOM_ACTIONS.md](./CUSTOM_ACTIONS.md) を参照してください。

## アシスタントの実行方法

ショートカットコマンド `./run` を使用して、簡単にアシスタントの管理や起動が行えます。

### 1. Web UI モード（常駐エージェント） 【推奨】
PCの起動時に自動でバックグラウンド実行されるように設定し、すべての操作をブラウザのダッシュボードで行うモードです。

- **常駐サーバーの起動 (有効化)**:
  ```bash
  ./run start
  ```
  このコマンドを実行すると、macOSの `launchd` にWebサーバーが登録され、PC起動時に自動でバックグラウンド起動するようになります。

- **ダッシュボードへのアクセス**:
  ブラウザで **[http://localhost:8000](http://localhost:8000)** にアクセスします。
  - **タスク一覧**: 登録されているタスクがカード形式で表示され、「実行」ボタンから起動できます。
  - **リアルタイムログ**: 実行中のエージェントのログがコンソール風にスクロール表示されます。
  - **MFAコードなどの入力待ち**: エージェントがユーザーに入力を求めた際、画面全体を覆う巨大な「入力要求オーバーレイ」が自動で表示され、そこに入力するだけで処理を続行させることができます。

- **ステータス確認**:
  サーバーが正しく稼働しているか確認します。
  ```bash
  ./run status
  ```

- **常駐サーバーの停止 (無効化)**:
  ```bash
  ./run stop
  ```

- **デバッグ用起動 (フォアグラウンド起動)**:
  バックグラウンドではなく、ターミナル上に直接ログを表示させながらWebサーバーを起動したい場合は以下を実行します。
  ```bash
  ./run dev
  ```

---

### 2. CLI モード（従来のターミナル実行）
ターミナル上で対話的に実行する従来の方法です。

- **CLI対話モードの起動**:
  ```bash
  ./run cli
  # または
  python3 main.py
  ```
- **タスク番号の直接指定**:
  ```bash
  ./run <タスク番号>
  # 例: ./run 1
  ```

**MFA（多要素認証）への対応 (CLI時):**
ログイン時にMFAコードの入力を求められた場合、エージェントは自動的に一時停止し、ターミナル上で以下のように入力を求めます。
```text
[Agentからの質問]: 認証コードが必要です。SMSに送信された6桁のコードを入力してください。
回答を入力してください (入力後Enter): 123456
```

---

## PCロック解除時の自動実行（トリガー設定）
macOSの画面ロック解除（`Ctrl + Cmd + Q` による画面ロックからの復帰や、ディスプレイ睡眠からの復帰）をトリガーにして、自動的にエージェントを実行する機能（常駐サービス）も設定可能です。

- **トリガーの有効化**:
  ```bash
  python3 manage_trigger.py enable
  ```
- **トリガーの無効化**:
  ```bash
  python3 manage_trigger.py disable
  ```

## 謝辞
このプロジェクトの開発は、Google Antigravityの支援を受けて行われました。
