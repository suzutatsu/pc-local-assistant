import os
import datetime
import asyncio
import logging
from dotenv import load_dotenv
from browser_use import Agent, Controller, Browser
from browser_use.llm.google import ChatGoogle
from google.auth import load_credentials_from_file


# 環境変数の読み込み
load_dotenv()

def _get_jira_client():
    jira_server = os.getenv("JIRA_SERVER")
    jira_email = os.getenv("JIRA_USER_EMAIL")
    jira_token = os.getenv("JIRA_API_TOKEN")
    if not (jira_server and jira_email and jira_token):
        return None, "エラー: Jiraの認証情報が .env に設定されていません。"
    try:
        from jira import JIRA
        jira = JIRA(server=jira_server, basic_auth=(jira_email, jira_token))
        return jira, None
    except Exception as e:
        return None, f"Jira初期化エラー: {e}"

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

    # パスが指定されている場合、認証情報を読み込む
    credentials = None
    if credentials_path and os.path.exists(credentials_path):
        credentials, _ = load_credentials_from_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
    
    # ChatGoogleを使用 (browser-useのネイティブコンポーネント)
    llm = ChatGoogle(
        model=model_name,
        vertexai=True,
        project=project_id,
        location=location,
        credentials=credentials,
        temperature=0
    )

    # タスク設定の読み込み
    import yaml
    import sys

    task_yaml_path = os.getenv("TASK_YAML_PATH")
    if task_yaml_path:
        tasks_file = task_yaml_path
    else:
        current_dir = os.getcwd()
        tasks_file = os.path.join(current_dir, "tasks.yaml")
        
    if not os.path.exists(tasks_file):
        print(f"エラー: 設定ファイル {tasks_file} が見つかりません。tasks.yaml.example をコピーして tasks.yaml を作成してください。")
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

    selected_task = None
    
    # CLI引数を確認
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        try:
            # 1始まりのインデックスを試行
            idx = int(arg) - 1
            if 0 <= idx < len(tasks):
                selected_task = tasks[idx]
        except ValueError:
            pass
            
    if selected_task:
        print(f"CLI引数でタスクが選択されました: {sys.argv[1]}")
    else:
        print("\n--- 実行可能タスク一覧 ---")
        for i, t in enumerate(tasks):
            print(f"{i + 1}. {t.get('name')} ({t.get('id')})")
            print(f"   説明: {t.get('description')}")
        print("-------------------------")

        # 対話モード
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

    # CLI引数からコンテキストを追加 (2つ目以降の引数がある場合)
    if len(sys.argv) > 2:
        extra_args = sys.argv[2:]
        context_info = " ".join(extra_args)
        print(f"追加コンテキスト: {context_info}")
        task_description += f"\n\n[ユーザー提供コンテキスト]: {context_info}\n(ここに情報が含まれている場合は、ask_userを使わずにそれを直接使用してください。)"

    if not task_description:
        print("タスクの説明（prompt）が空です。終了します。")
        return

    # ブラウザの仕様設定
    # use_browser が明示的に false の場合のみヘッドレスモードを有効化（画面を出さない）
    # デフォルトは True (画面を出す)
    use_browser = selected_task.get('use_browser', True)
    headless_mode = not use_browser

    # 永続的なブラウザプロファイルの設定
    # プロジェクトディレクトリ内に 'browser_profile' ディレクトリを作成して使用します
    profile_path = os.path.join(current_dir, "browser_profile")
    os.makedirs(profile_path, exist_ok=True)
    
    # ブラウザの初期化
    browser = Browser(
        headless=headless_mode, 
        user_data_dir=profile_path,
        enable_default_extensions=False, # 組織ポリシー等で拡張機能インストールが制限される場合に備え無効化
        # 操作の安定性を高めるための待機設定
        wait_between_actions=1.0,         # 各アクション（クリック・入力など）の間に1秒待機
        minimum_wait_page_load_time=2.0,  # ページロード時に最低2秒待機してDOMレンダリングを確実にする
        # chrome_instance_path=None, # デフォルトのChromeを使用
        # other args...
    )




    # Controller パターンを使用してカスタムアクション（ツール）を定義
    controller = Controller()
    
    @controller.action("ask_user")
    def ask_user_action(question: str):
        """
        ユーザーに質問をし、その回答を返します。
        MFAコード、認証コード、OTP、またはその他の情報を入力する必要がある場合にこのツールを使用してください。
        また、ログインなどの手動操作をユーザーに依頼する場合にも使用してください。
        """
        print(f"\n\n[Agentからの質問]: {question}")
        return input("回答を入力してください (入力後Enter): ")

    @controller.action("search_jira_issues")
    def search_jira_issues(jql: str):
        """
        Jiraのチケットを検索します。
        例: 'project = PROJ AND status = "In Progress"'
        """
        jira, error = _get_jira_client()
        if error: return error
        
        try:
            issues = jira.search_issues(jql, maxResults=10)
            if not issues:
                return "JQLに一致するチケットは見つかりませんでした。"
            return [{"key": issue.key, "summary": issue.fields.summary, "status": str(issue.fields.status)} for issue in issues]
        except Exception as e:
            return f"Jira検索エラー: {e}"

    @controller.action("add_jira_comment")
    def add_jira_comment(issue_key: str, comment: str):
        """
        指定したJiraチケット(例: PROJ-123)にコメントを追加します。
        """
        jira, error = _get_jira_client()
        if error: return error
        
        try:
            jira.add_comment(issue_key, comment)
            return f"チケット {issue_key} にコメントを追加しました。"
        except Exception as e:
            return f"Jiraコメント追加エラー: {e}"

    @controller.action("update_jira_issue_description")
    def update_jira_issue_description(issue_key: str, description: str):
        """
        指定したJiraチケット(例: PROJ-123)の説明(Description)を更新します。
        """
        jira, error = _get_jira_client()
        if error: return error
        
        try:
            issue = jira.issue(issue_key)
            issue.update(description=description)
            return f"チケット {issue_key} の説明を更新しました。"
        except Exception as e:
            return f"Jira説明更新エラー: {e}"

    # エージェントの作成
    agent = Agent(
        task=task_description,
        llm=llm,
        browser=browser,
        controller=controller,
        # 認識精度向上のための設定
        use_vision=True,               # 画像認識を明示的に有効化
        vision_detail_level="high",    # より高精細な画像をLLMに渡し、UI要素の認識精度を向上させる
        use_thinking=True,             # LLMによるプランニングと推論を有効化
        enable_planning=True
    )

    # エージェントの実行
    print("エージェントを実行中...")
    history = await agent.run()
    
    # 結果の表示
    print("\n--- 実行結果 ---")
    result = history.final_result()
    print(result)

    # 振り返りの自動生成と保存
    print("\n--- 振り返りを生成中 ---")
    
    reflection_prompt = f"""
    以下の観点で、今回のタスク『{selected_task.get('name')}』の実行プロセスを振り返り、簡潔にまとめてください：
    1. **目的**: ループや知識不足による不要なステップを減らし、より少ないステップ数で効率的に要件を満たすこと。
    2. **分析**: どの手順でつまずいたか、無駄な操作がなかったか。
    3. **改善案**: 次回同様のタスクを行う際、プロンプトをどのように変更すれば、よりスムーズかつ短手順で完了できるか。（**現状で十分に効率的であれば、あえて改善案を挙げる必要はありません**）

    実行履歴:
    {result}
    """
    
    try:
        from langchain_core.messages import HumanMessage
        reflection_content = await llm.ainvoke([HumanMessage(content=reflection_prompt)])
        
        if hasattr(reflection_content, 'content'):
            reflection_text = reflection_content.content
        elif hasattr(reflection_content, 'completion'):
            reflection_text = reflection_content.completion
        else:
            reflection_text = str(reflection_content)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # historyはAgentHistoryListオブジェクト。steps等の属性があるか不明だが、長さを取得できると仮定
        # もし len() が使えない場合は 'N/A' とする
        try:
             step_count = len(history.history)
        except:
             step_count = "Unknown"
        
        reflection_entry = f"""
## {timestamp} - {selected_task.get('name')}
- **Model**: {model_name}
- **Steps**: {step_count}
- **Reflection**:
{reflection_text}
"""
        
        reflection_file = os.path.join(current_dir, "REFLECTION.md")
        with open(reflection_file, "a", encoding="utf-8") as f:
            f.write(reflection_entry + "\n")
            
        print(f"振り返りを REFLECTION.md に保存しました。")
        print(reflection_entry)

    except Exception as e:
        print(f"振り返りの生成または保存に失敗しました: {e}")

    # ブラウザを閉じる
    # await browser.close() # browser-use automatically handles cleanup

if __name__ == "__main__":
    asyncio.run(main())
