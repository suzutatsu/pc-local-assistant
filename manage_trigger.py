#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

# 絶対パスの動的解決
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PLIST_LABEL = "org.local.pc-assistant-trigger"
PLIST_FILE_NAME = f"{PLIST_LABEL}.plist"
LAUNCH_AGENTS_DIR = os.path.expanduser("~/Library/LaunchAgents")
PLIST_DEST_PATH = os.path.join(LAUNCH_AGENTS_DIR, PLIST_FILE_NAME)

TRIGGER_SCRIPT_PATH = os.path.join(PROJECT_DIR, "pc_local_assistant_trigger.py")
LOCAL_PLIST_PATH = os.path.join(PROJECT_DIR, PLIST_FILE_NAME)
CUSTOM_PYTHON_SYMLINK = os.path.join(PROJECT_DIR, "venv/bin/pc-local-assistant-trigger")

TRIGGER_SCRIPT_CONTENT = """import os
import subprocess
from Foundation import NSObject, NSDistributedNotificationCenter
from AppKit import NSApplication

PROJECT_DIR = "{project_dir}"
CUSTOM_PYTHON = os.path.join(PROJECT_DIR, "venv/bin/pc-local-assistant-trigger")
MAIN_SCRIPT = os.path.join(PROJECT_DIR, "main.py")
EXECUTION_LOG = os.path.join(PROJECT_DIR, "main_execution.log")

class NotificationObserver(NSObject):
    def unlockCallback_(self, notification):
        notification_name = notification.name()
        print(f"Received notification: {{notification_name}}", flush=True)
        print("Screen unlocked! Triggering pc-local-assistant...", flush=True)
        
        try:
            log_file = open(EXECUTION_LOG, "a", encoding="utf-8")
            log_file.write(f"\\n--- Triggered Screen Unlock ({{notification_name}}) ---\\n")
            log_file.flush()
            
            subprocess.Popen(
                [CUSTOM_PYTHON, MAIN_SCRIPT, "1"],
                cwd=PROJECT_DIR,
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL
            )
            print("Successfully spawned main.py with custom trigger process", flush=True)
        except Exception as e:
            print(f"Error spawning script: {{e}}", flush=True)

def main():
    app = NSApplication.sharedApplication()
    observer = NotificationObserver.alloc().init()
    
    center = NSDistributedNotificationCenter.defaultCenter()
    center.addObserver_selector_name_object_(
        observer,
        "unlockCallback:",
        "com.apple.screensaver.didUnlock",
        None
    )
    center.addObserver_selector_name_object_(
        observer,
        "unlockCallback:",
        "com.apple.screenIsUnlocked",
        None
    )
    
    print("Listening for macOS screen unlock events (com.apple.screensaver.didUnlock & com.apple.screenIsUnlocked)...", flush=True)
    app.run()

if __name__ == "__main__":
    main()
"""

PLIST_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{project_dir}/venv/bin/pc-local-assistant-trigger</string>
        <string>{project_dir}/pc_local_assistant_trigger.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>{project_dir}</string>
    <key>StandardOutPath</key>
    <string>{project_dir}/trigger_out.log</string>
    <key>StandardErrorPath</key>
    <string>{project_dir}/trigger_err.log</string>
</dict>
</plist>
"""

def check_dependencies():
    # pyobjc が利用可能かチェック
    try:
        import Foundation
        import AppKit
    except ImportError:
        print("[-] macOSのAPIバインディング(pyobjc)がロードできません。")
        print("[*] 仮想環境にパッケージをインストールしています...")
        pip_path = os.path.join(PROJECT_DIR, "venv/bin/pip")
        if os.path.exists(pip_path):
            try:
                subprocess.check_call([pip_path, "install", "pyobjc-framework-Cocoa"])
                print("[+] pyobjc-framework-Cocoa のインストールに成功しました。")
            except Exception as e:
                print(f"[-] パッケージのインストールに失敗しました: {e}")
                print("[!] 手動で次のコマンドを実行してください: venv/bin/pip install pyobjc-framework-Cocoa")
                sys.exit(1)
        else:
            print("[-] venv/bin/pip が見つかりません。仮想環境がセットアップされているか確認してください。")
            sys.exit(1)

def get_current_user_uid():
    try:
        uid = subprocess.check_output(["id", "-u"]).decode().strip()
        return uid
    except Exception:
        return "501"  # デフォルト

def is_service_running():
    uid = get_current_user_uid()
    try:
        output = subprocess.check_output(["launchctl", "print", f"gui/{uid}/{PLIST_LABEL}"], stderr=subprocess.DEVNULL).decode()
        return "state = running" in output
    except subprocess.CalledProcessError:
        return False

def enable_trigger():
    print("[*] PCロック解除時の自動起動トリガーを有効化しています...")
    check_dependencies()
    
    # 1. 仮想環境にカスタムプロセスのシンボリックリンクを作成
    if not os.path.exists(CUSTOM_PYTHON_SYMLINK):
        try:
            os.symlink("python3", CUSTOM_PYTHON_SYMLINK)
            print("[+] カスタムプロセスのシンボリックリンクを作成しました。")
        except Exception as e:
            print(f"[-] シンボリックリンクの作成に失敗しました: {e}")
            sys.exit(1)

    # 2. ロック解除監視スクリプトを動的に生成
    try:
        with open(TRIGGER_SCRIPT_PATH, "w", encoding="utf-8") as f:
            f.write(TRIGGER_SCRIPT_CONTENT.format(project_dir=PROJECT_DIR))
        print(f"[+] トリガースクリプトを生成しました: {TRIGGER_SCRIPT_PATH}")
    except Exception as e:
        print(f"[-] トリガースクリプトの生成に失敗しました: {e}")
        sys.exit(1)

    # 3. launchd 用の plist ファイルを生成
    try:
        with open(LOCAL_PLIST_PATH, "w", encoding="utf-8") as f:
            f.write(PLIST_CONTENT.format(label=PLIST_LABEL, project_dir=PROJECT_DIR))
        print(f"[+] launchd plist 設定を生成しました: {LOCAL_PLIST_PATH}")
    except Exception as e:
        print(f"[-] launchd plist の生成に失敗しました: {e}")
        sys.exit(1)

    # 4. plistを ~/Library/LaunchAgents/ にコピー
    os.makedirs(LAUNCH_AGENTS_DIR, exist_ok=True)
    try:
        shutil.copy(LOCAL_PLIST_PATH, PLIST_DEST_PATH)
        print(f"[+] 設定を LaunchAgents へコピーしました: {PLIST_DEST_PATH}")
    except Exception as e:
        print(f"[-] LaunchAgents へのコピーに失敗しました: {e}")
        sys.exit(1)

    # 5. すでに動いている場合は一度ブートアウト (安全策)
    uid = get_current_user_uid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", PLIST_DEST_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 6. launchctl に登録して起動
    try:
        result = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", PLIST_DEST_PATH], capture_output=True, text=True)
        if result.returncode == 0:
            print("[+] launchd サービスのロード・起動に成功しました！")
            print("[+] トリガーは正常に 【ON】 になりました。")
        else:
            print(f"[-] サービスの起動に失敗しました: {result.stderr.strip()}")
            sys.exit(1)
    except Exception as e:
        print(f"[-] launchd への登録中にエラーが発生しました: {e}")
        sys.exit(1)

def disable_trigger():
    print("[*] PCロック解除時の自動起動トリガーを無効化しています...")
    uid = get_current_user_uid()
    
    # 1. launchctl から登録解除・サービス停止
    if os.path.exists(PLIST_DEST_PATH) or is_service_running():
        try:
            result = subprocess.run(["launchctl", "bootout", f"gui/{uid}", PLIST_DEST_PATH], capture_output=True, text=True)
            if result.returncode == 0 or "No such process" in result.stderr:
                print("[+] launchd サービスを正常に停止・登録解除しました。")
            else:
                print(f"[*] サービスの停止中に注意メッセージ: {result.stderr.strip()}")
        except Exception as e:
            print(f"[-] サービスの停止中にエラーが発生しました: {e}")
    else:
        print("[*] サービスはすでに登録されていません。")

    # 2. 生成された関連ファイルをすべてクリーンアップ
    files_to_remove = [
        PLIST_DEST_PATH,
        LOCAL_PLIST_PATH,
        TRIGGER_SCRIPT_PATH,
        CUSTOM_PYTHON_SYMLINK,
        os.path.join(PROJECT_DIR, "trigger_out.log"),
        os.path.join(PROJECT_DIR, "trigger_err.log"),
        os.path.join(PROJECT_DIR, "main_execution.log")
    ]
    
    for path in files_to_remove:
        if os.path.exists(path):
            try:
                if os.path.islink(path) or os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
                print(f"[+] ファイルを削除しました: {path}")
            except Exception as e:
                print(f"[-] ファイル {path} の削除に失敗しました: {e}")

    print("[+] トリガーは正常に 【OFF】（削除済み）になりました。")

def show_status():
    print("[*] トリガーの稼働ステータスを確認しています...")
    service_active = is_service_running()
    plist_installed = os.path.exists(PLIST_DEST_PATH)
    
    if service_active:
        print("\n  トリガーステータス: 【 ON 】 (常駐稼働中)")
        print(f"  プロセス名: {PLIST_LABEL}")
        print("  ※ PCを画面ロック・解除するたびにアシスタントが自動実行されます。")
    elif plist_installed:
        print("\n  トリガーステータス: 【 INACTIVE 】 (設定ファイルは存在しますが稼働していません)")
        print("  ※ 'python3 manage_trigger.py enable' を実行して起動してください。")
    else:
        print("\n  トリガーステータス: 【 OFF 】 (無効化・未セットアップ)")
        print("  ※ 自動起動は行われません。")
    print()

def show_usage():
    print("利用方法:")
    print("  python3 manage_trigger.py enable  : トリガーを有効化 (ON) にします")
    print("  python3 manage_trigger.py disable : トリガーを無効化 (OFF) にして全クリーンアップします")
    print("  python3 manage_trigger.py status  : 現在のトリガーの有効・無効状態を確認します")
    print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(0)
        
    command = sys.argv[1].lower()
    
    if command == "enable":
        enable_trigger()
    elif command == "disable":
        disable_trigger()
    elif command == "status":
        show_status()
    else:
        print(f"[-] 未知のコマンドです: {sys.argv[1]}")
        show_usage()
        sys.exit(1)
