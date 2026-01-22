import os
import asyncio
import logging
from dotenv import load_dotenv
from browser_use import Agent, Controller, Browser
from browser_use.llm.google import ChatGoogle
from google.auth import load_credentials_from_file

# 環境変数の読み込み
load_dotenv()

# Monkey-patch to increase navigation timeout (default 4s is too short)
# This overrides the internal method of browser_use.browser.session.BrowserSession (aliased as Browser)
original_navigate_and_wait = Browser._navigate_and_wait

async def patched_navigate_and_wait(self, url, target_id, timeout=None):
    if timeout is None:
        # Increase the default 4s timeout to 20s for slower pages
        timeout = 20.0
    return await original_navigate_and_wait(self, url, target_id, timeout)

Browser._navigate_and_wait = patched_navigate_and_wait

async def main():
    # Gemini Flashモデルの設定
    # ユーザー指定のモデル、もしくは最新のFlashモデル（gemini-3-flash-preview）を使用
    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_REGION", "asia-northeast1")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    print(f"Using Vertex AI Model: {model_name}")
    print(f"Project: {project_id}, Region: {location}")
    print(f"Credentials Path: {credentials_path}")

    # Load credentials if path is provided
    credentials = None
    if credentials_path and os.path.exists(credentials_path):
        credentials, _ = load_credentials_from_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
    
    # Use ChatGoogle (native browser-use component)
    llm = ChatGoogle(
        model=model_name,
        vertexai=True,
        project=project_id,
        location=location,
        credentials=credentials,
        temperature=0
    )

    # 永続的なブラウザプロファイルの設定
    # プロジェクトディレクトリ内に 'browser_profile' ディレクトリを作成して使用します
    current_dir = os.getcwd()
    profile_path = os.path.join(current_dir, "browser_profile")
    os.makedirs(profile_path, exist_ok=True)
    
    # ブラウザの初期化 (0.11.3以降のAPI)
    # Browser (BrowserSession) に直接設定を渡します
    browser = Browser(
        headless=False, # 動作確認のためヘッドレスモードをオフにする
        user_data_dir=profile_path,
        enable_default_extensions=False, # 組織ポリシー等で拡張機能インストールが制限される場合に備え無効化
        # chrome_instance_path=None, # デフォルトのChromeを使用
        # other args...
    )

    # タスク設定の読み込み
    import yaml
    
    tasks_file = os.path.join(current_dir, "tasks.yaml")
    if not os.path.exists(tasks_file):
        print(f"エラー: 設定ファイル {tasks_file} が見つかりません。")
        return

    with open(tasks_file, 'r', encoding='utf-8') as f:
        try:
            config = yaml.safe_load(f)
            tasks = config.get('tasks', [])
        except yaml.YAMLError as exc:
            print(f"YAMLファイルの読み込みエラー: {exc}")
            return

    if not tasks:
        print("実行可能なタスクが定義されていません。")
        return

    print("\n--- 実行可能タスク一覧 ---")
    for i, t in enumerate(tasks):
        print(f"{i + 1}. {t.get('name')} ({t.get('id')})")
        print(f"   説明: {t.get('description')}")
    print("-------------------------")

    selected_task = None
    import sys
    
    # Check for CLI arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        try:
            # Try 1-based index
            idx = int(arg) - 1
            if 0 <= idx < len(tasks):
                selected_task = tasks[idx]
        except ValueError:
            # Optional: Support task ID string matching in future, currently just ignoring
            pass
            
    if selected_task:
        print(f"CLI引数でタスクが選択されました: {sys.argv[1]}")
    else:
        # Interactive Mode
        while True:
            choice = input("実行したいタスクの番号を入力してください (qで終了): ")
            if choice.lower() == 'q':
                print("終了します。")
                return
            
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(tasks):
                    selected_task = tasks[idx]
                    break
                else:
                    print("無効な番号です。もう一度入力してください。")
            except ValueError:
                print("番号を入力してください。")

    print(f"\n選択されたタスク: {selected_task.get('name')}")
    # ユーザーが「ログイン完了」等を伝えやすいように変数名をそのまま使用
    task_description = selected_task.get('prompt', '')

    if not task_description:
        print("タスクの説明（prompt）が空です。終了します。")
        return

    # Controller パターンを使用してカスタムアクション（ツール）を定義
    controller = Controller()
    
    @controller.action("ask_user")
    def ask_user_action(question: str):
        """
        Asks the user a question and returns their answer.
        Use this tool when you need to input an MFA code, verification code, OTP, or any other information.
        Also use this tool to ask the user to perform manual actions like logging in.
        """
        print(f"\n\n[Agentからの質問]: {question}")
        return input("回答を入力してください (入力後Enter): ")

    # エージェントの作成
    agent = Agent(
        task=task_description,
        llm=llm,
        browser=browser,
        controller=controller
    )

    # エージェントの実行
    print("エージェントを実行中...")
    history = await agent.run()
    
    # 結果の表示
    print("\n--- 実行結果 ---")
    print(history.final_result())

    # ブラウザを閉じる
    # await browser.close() # browser-use 0.11.3 handles cleanup automatically

if __name__ == "__main__":
    asyncio.run(main())
