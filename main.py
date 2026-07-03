import os
import sys
import datetime
import asyncio
import logging
import yaml
from dotenv import load_dotenv
from browser_use import Agent, Controller, Browser
from browser_use.llm.google import ChatGoogle
from google.auth import load_credentials_from_file

# 環境変数の読み込み
load_dotenv()

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pc_local_assistant")

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

def load_tasks(tasks_file=None):
    current_dir = os.getcwd()
    if not tasks_file:
        task_yaml_path = os.getenv("TASK_YAML_PATH")
        if task_yaml_path:
            tasks_file = task_yaml_path
        else:
            tasks_file = os.path.join(current_dir, "tasks.yaml")
            
    if not os.path.exists(tasks_file):
        logger.error(f"設定ファイル {tasks_file} が見つかりません。")
        return []

    with open(tasks_file, 'r', encoding='utf-8') as f:
        try:
            config = yaml.safe_load(f)
            return config.get('tasks', [])
        except yaml.YAMLError as exc:
            logger.error(f"YAMLファイルの読み込みエラー: {exc}")
            return []

def initialize_llm():
    llm_provider = os.getenv("LLM_PROVIDER", "vertexai").lower()
    model_name = "gemini-3.5-flash"
    
    if llm_provider == "ollama":
        from langchain_ollama import ChatOllama
        model_name = os.getenv("OLLAMA_MODEL", "gemma4")
        print(f"Using Ollama Local Model: {model_name}")
        llm = ChatOllama(
            model=model_name,
            temperature=0
        )
    else:
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3.5-flash")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "asia-northeast1")
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        print(f"Using Vertex AI Model: {model_name}")
        credentials = None
        if credentials_path and os.path.exists(credentials_path):
            credentials, _ = load_credentials_from_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
        
        llm = ChatGoogle(
            model=model_name,
            vertexai=True,
            project=project_id,
            location=location,
            credentials=credentials,
            temperature=0
        )
        
    return llm, model_name

def create_controller(ask_user_fn):
    controller = Controller()
    
    @controller.action("ask_user")
    def ask_user_action(question: str):
        """
        ユーザーに質問をし、その回答を返します。
        MFAコード、認証コード、OTP、またはその他の情報を入力する必要がある場合にこのツールを使用してください。
        また、ログインなどの手動操作をユーザーに依頼する場合にも使用してください。
        """
        return ask_user_fn(question)

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
            
    return controller

async def generate_reflection(task_name, model_name, result, steps, current_dir, llm):
    print("\n--- 振り返りを生成中 ---")
    reflection_prompt = f"""
    以下の観点で、今回のタスク『{task_name}』の実行プロセスを振り返り、簡潔にまとめてください：
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
        reflection_entry = f"""
## {timestamp} - {task_name}
- **Model**: {model_name}
- **Steps**: {steps}
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

async def run_sequence(tasks_to_run, llm, browser_profile_path, ask_user_fn, context_info="", pass_context=False, model_name="gemini-3-flash-preview"):
    # ブラウザの仕様設定
    use_browser = any(t.get('use_browser', True) for t in tasks_to_run)
    headless_mode = not use_browser

    browser = Browser(
        headless=headless_mode, 
        user_data_dir=browser_profile_path,
        enable_default_extensions=False,
        wait_between_actions=1.0,
        minimum_wait_page_load_time=2.0,
        ignore_default_args=['--extensions-on-chrome-urls'],
    )

    controller = create_controller(ask_user_fn)
    previous_result = ""
    current_dir = os.getcwd()

    try:
        for idx, current_task in enumerate(tasks_to_run):
            task_name = current_task.get('name')
            task_description = current_task.get('prompt', '')
            
            if not task_description:
                print(f"タスク '{task_name}' の説明（prompt）が空のためスキップします。")
                continue
                
            if context_info:
                task_description += f"\n\n[ユーザー提供コンテキスト]: {context_info}\n(ここに情報が含まれている場合は、ask_userを使わずにそれを直接使用してください。)"
                
            if pass_context and idx > 0 and previous_result:
                task_description += f"\n\n【前段タスクからの引き継ぎデータ】:\n{previous_result}"
                
            agent = Agent(
                task=task_description,
                llm=llm,
                browser=browser,
                controller=controller,
                use_vision=True,
                vision_detail_level="high",
                use_thinking=True,
                enable_planning=True
            )

            print(f"\n[{idx+1}/{len(tasks_to_run)}] エージェントを実行中: {task_name}")
            history = await agent.run()
            
            print(f"\n--- {task_name} の実行結果 ---")
            result = history.final_result()
            print(result)
            previous_result = result

            try:
                step_count = len(history.history)
            except Exception:
                step_count = "Unknown"

            await generate_reflection(task_name, model_name, result, step_count, current_dir, llm)
            
        return previous_result
    finally:
        await browser.close()

# CLI対話モード
def run_cli():
    llm, model_name = initialize_llm()
    tasks = load_tasks()
    
    if not tasks:
        print("実行可能なタスクがありません。")
        return

    selected_task = None
    
    # CLI引数を確認
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        # 'cli' という引数はスキップする（run cli で起動された場合）
        if arg.lower() != 'cli':
            try:
                idx = int(arg) - 1
                if 0 <= idx < len(tasks):
                    selected_task = tasks[idx]
            except ValueError:
                pass
            
    if selected_task:
        print(f"CLI引数でタスクが選択されました: {selected_task.get('name')}")
    else:
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

    context_info = ""
    # 引数が 'cli' の場合は sys.argv[2:] が追加コンテキストになる
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'cli':
        if len(sys.argv) > 2:
            context_info = " ".join(sys.argv[2:])
    elif len(sys.argv) > 2:
        context_info = " ".join(sys.argv[2:])
        
    if context_info:
        print(f"追加コンテキスト: {context_info}")

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
                print(f"エラー: Sequence に定義されたタスク '{step_id}' が見つかりません。")
                return
    else:
        tasks_to_run = [selected_task]
        pass_context = False

    profile_path = os.path.join(os.getcwd(), "browser_profile")
    os.makedirs(profile_path, exist_ok=True)
    
    # CLI 用の ask_user コールバック
    def cli_ask_user(question):
        print(f"\n\n[Agentからの質問]: {question}")
        return input("回答を入力してください (入力後Enter): ")

    try:
        asyncio.run(run_sequence(
            tasks_to_run=tasks_to_run,
            llm=llm,
            browser_profile_path=profile_path,
            ask_user_fn=cli_ask_user,
            context_info=context_info,
            pass_context=pass_context,
            model_name=model_name
        ))
    except KeyboardInterrupt:
        print("\n中断されました。")
        sys.exit(0)

if __name__ == "__main__":
    run_cli()
