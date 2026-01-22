# PC Local Assistant

Mac上で動作する、AI主導のブラウザ操作アシスタントです。
Chromeブラウザを自動操作し、認証が必要な社内ページなどからの情報収集を行います。

## 特徴
- **Gemini Flash**: 高速なGemini 1.5 Flashモデルを使用。
- **browser-use**: 高度なブラウザ操作エージェントライブラリを使用。
- **永続化プロファイル**: `chrome_profile` ディレクトリを使用し、ログイン状態やCookieを保持します。

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
GEMINI_MODEL_NAME=gemini-3-flash-preview
```

## 実行方法

```bash
python3 main.py
```

実行すると、タスクの入力を求められます。
初回は認証が必要な場合がありますが、一度ログインすればCookieが `chrome_profile` に保存されるため、次回以降は自動ログイン（またはログイン済み状態）が維持される可能性があります。

**MFA（多要素認証）への対応:**
ログイン時にMFAコード（ワンタイムパスワードなど）の入力を求められた場合、エージェントは自動的に一時停止し、ターミナル上で以下のようにコードの入力を求めます。
ユーザーがコードを入力してEnterキーを押すと、エージェントはブラウザにそのコードを入力して処理を続行します。

```text
[Agentからの質問]: 認証コードが必要です。SMSに送信された6桁のコードを入力してください。
回答を入力してください (入力後Enter): 123456
```

### タスクの実行
スクリプトを実行すると、`tasks.yaml` に定義されたタスクの一覧が表示されます。
実行したいタスクの番号を入力してください。

```bash
--- 実行可能タスク一覧 ---
1. 日次売上チェック (daily_sales)
   説明: 売上管理システムにログインし、昨日の売上速報を取得して表示します。
2. 勤怠打刻漏れチェック (attendance_log)
   説明: 勤怠システムで今月の打刻漏れがないか確認します。
-------------------------
実行したいタスクの番号を入力してください (qで終了): 1
```

### タスクの設定 (`tasks.yaml`)
実行するタスクは `tasks.yaml` で管理します。
新しいタスクを追加したい場合は、このファイルを編集してください。

```yaml
tasks:
  - id: "unique_id"
    name: "タスク名"
    description: "タスクの簡単な説明"
    prompt: |
      https://example.com/login にアクセスしてください。
      ログイン画面が表示されたら、ask_user ツールを使ってユーザーにログインを依頼してください。
      ログイン完了後、xxxx の操作を行ってください。
```

### 認証（ログイン）について
セキュリティのため、社内システムへのID・パスワード入力は**ユーザー自身による手動操作**を推奨しています。
タスクの指示（`prompt`）の中で、「ログイン画面ではユーザーに入力を依頼する」ように記述してください。

エージェントが `ask_user` ツールを使用すると実行が一時停止しますので、その間にブラウザ上でログインを行い、完了したらターミナルでEnterを押してエージェントに通知してください。
