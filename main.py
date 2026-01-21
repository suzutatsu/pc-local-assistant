import asyncio
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Controller
from browser_use.browser.browser import Browser, BrowserConfig, BrowserContextConfig

# 環境変数の読み込み
load_dotenv()

async def main():
    # Gemini Flashモデルの設定
    # ユーザー指定のモデル、もしくは最新のFlashモデル（gemini-3-flash-preview）を使用
    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    print(f"Using Gemini Model: {model_name}")
    
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0
    )

    # 永続的なChromeプロファイルの設定
    # プロジェクトディレクトリ内に 'chrome_profile' ディレクトリを作成して使用します
    current_dir = os.getcwd()
    profile_path = os.path.join(current_dir, "chrome_profile")
    
    # ブラウザの初期化
    # new_context_config で user_data_dir を指定し、プロファイルを永続化します
    browser = Browser(
        config=BrowserConfig(
            headless=False, # 動作確認のためヘッドレスモードをオフにする
            chrome_instance_path=None, # デフォルトのChromeを使用
        )
    )

    # コンテキスト設定（永続化のため）
    context_config = BrowserContextConfig(
        user_data_dir=profile_path,
        # 必要に応じてウィンドウサイズなどを指定
        # viewport={'width': 1280, 'height': 720}
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
        browser_context_config=context_config,
        controller=controller
    )

    # エージェントの実行
    print("エージェントを実行中...")
    history = await agent.run()
    
    # 結果の表示
    print("\n--- 実行結果 ---")
    print(history.final_result())

    # ブラウザを閉じる
    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
