#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

# 絶対パスの動的解決
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LAUNCH_AGENTS_DIR = os.path.expanduser("~/Library/LaunchAgents")

# ロック解除トリガー用の設定
PLIST_LABEL = "org.local.pc-assistant-trigger"
PLIST_FILE_NAME = f"{PLIST_LABEL}.plist"
PLIST_DEST_PATH = os.path.join(LAUNCH_AGENTS_DIR, PLIST_FILE_NAME)
TRIGGER_SCRIPT_PATH = os.path.join(PROJECT_DIR, "pc_local_assistant_trigger.py")
LOCAL_PLIST_PATH = os.path.join(PROJECT_DIR, PLIST_FILE_NAME)
CUSTOM_PYTHON_SYMLINK = os.path.join(PROJECT_DIR, "venv/bin/pc-local-assistant-trigger")

# サーバー常駐用の設定
SERVER_LABEL = "org.local.pc-assistant-server"
SERVER_FILE_NAME = f"{SERVER_LABEL}.plist"
SERVER_DEST_PATH = os.path.join(LAUNCH_AGENTS_DIR, SERVER_FILE_NAME)
SERVER_LOCAL_PLIST_PATH = os.path.join(PROJECT_DIR, SERVER_FILE_NAME)

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
        
        log_file = None
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
        finally:
            if log_file is not None:
                log_file.close()

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

SERVER_PLIST_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{project_dir}/venv/bin/uvicorn</string>
        <string>server:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8000</string>
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
    <string>{project_dir}/server_out.log</string>
    <key>StandardErrorPath</key>
    <string>{project_dir}/server_err.log</string>
</dict>
</plist>
"""

def check_dependencies():
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
                sys.exit(1)
        else:
            print("[-] venv/bin/pip が見つかりません。")
            sys.exit(1)

def get_current_user_uid():
    try:
        uid = subprocess.check_output(["id", "-u"]).decode().strip()
        return uid
    except Exception:
        return "501"

def is_service_running(label):
    uid = get_current_user_uid()
    try:
        output = subprocess.check_output(["launchctl", "print", f"gui/{uid}/{label}"], stderr=subprocess.DEVNULL).decode()
        return "state = running" in output
    except subprocess.CalledProcessError:
        return False

# ==================== ロック解除トリガー管理 ====================

def enable_trigger():
    print("[*] PCロック解除時の自動起動トリガーを有効化しています...")
    check_dependencies()
    
    if not os.path.exists(CUSTOM_PYTHON_SYMLINK):
        try:
            os.symlink("python3", CUSTOM_PYTHON_SYMLINK)
        except Exception as e:
            print(f"[-] シンボリックリンクの作成に失敗しました: {e}")
            sys.exit(1)

    try:
        with open(TRIGGER_SCRIPT_PATH, "w", encoding="utf-8") as f:
            f.write(TRIGGER_SCRIPT_CONTENT.format(project_dir=PROJECT_DIR))
    except Exception as e:
        print(f"[-] トリガースクリプトの生成に失敗しました: {e}")
        sys.exit(1)

    try:
        with open(LOCAL_PLIST_PATH, "w", encoding="utf-8") as f:
            f.write(PLIST_CONTENT.format(label=PLIST_LABEL, project_dir=PROJECT_DIR))
    except Exception as e:
        print(f"[-] launchd plist の生成に失敗しました: {e}")
        sys.exit(1)

    os.makedirs(LAUNCH_AGENTS_DIR, exist_ok=True)
    try:
        shutil.copy(LOCAL_PLIST_PATH, PLIST_DEST_PATH)
    except Exception as e:
        print(f"[-] LaunchAgents へのコピーに失敗しました: {e}")
        sys.exit(1)

    uid = get_current_user_uid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", PLIST_DEST_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        result = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", PLIST_DEST_PATH], capture_output=True, text=True)
        if result.returncode == 0:
            print("[+] ロック解除トリガーを起動しました。")
        else:
            print(f"[-] 起動に失敗しました: {result.stderr.strip()}")
            sys.exit(1)
    except Exception as e:
        print(f"[-] launchd への登録中にエラーが発生しました: {e}")
        sys.exit(1)

def disable_trigger():
    print("[*] PCロック解除時の自動起動トリガーを無効化しています...")
    uid = get_current_user_uid()
    
    if os.path.exists(PLIST_DEST_PATH) or is_service_running(PLIST_LABEL):
        try:
            subprocess.run(["launchctl", "bootout", f"gui/{uid}", PLIST_DEST_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[+] サービスを停止・登録解除しました。")
        except Exception as e:
            print(f"[-] サービスの停止中にエラーが発生しました: {e}")

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
                os.remove(path)
            except Exception:
                pass

    print("[+] トリガーを無効化しました。")

# ==================== Webサーバー常駐管理 ====================

def enable_server():
    print("[*] Webサーバーの常駐起動を有効化しています...")
    
    # plist作成
    try:
        with open(SERVER_LOCAL_PLIST_PATH, "w", encoding="utf-8") as f:
            f.write(SERVER_PLIST_CONTENT.format(label=SERVER_LABEL, project_dir=PROJECT_DIR))
        print(f"[+] launchd server plist 設定を生成しました: {SERVER_LOCAL_PLIST_PATH}")
    except Exception as e:
        print(f"[-] launchd server plist の生成に失敗しました: {e}")
        sys.exit(1)

    os.makedirs(LAUNCH_AGENTS_DIR, exist_ok=True)
    try:
        shutil.copy(SERVER_LOCAL_PLIST_PATH, SERVER_DEST_PATH)
        print(f"[+] 設定を LaunchAgents へコピーしました: {SERVER_DEST_PATH}")
    except Exception as e:
        print(f"[-] LaunchAgents へのコピーに失敗しました: {e}")
        sys.exit(1)

    uid = get_current_user_uid()
    # 既存のものをブートアウト
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", SERVER_DEST_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 起動
    try:
        result = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", SERVER_DEST_PATH], capture_output=True, text=True)
        if result.returncode == 0:
            print("[+] Webサーバーの常駐起動に成功しました！")
            print("[+] http://localhost:8000 でWebダッシュボードにアクセスできます。")
        else:
            print(f"[-] 常駐起動に失敗しました: {result.stderr.strip()}")
            sys.exit(1)
    except Exception as e:
        print(f"[-] launchd への登録中にエラーが発生しました: {e}")
        sys.exit(1)

def disable_server():
    print("[*] Webサーバーの常駐起動を無効化しています...")
    uid = get_current_user_uid()
    
    if os.path.exists(SERVER_DEST_PATH) or is_service_running(SERVER_LABEL):
        try:
            subprocess.run(["launchctl", "bootout", f"gui/{uid}", SERVER_DEST_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[+] 常駐Webサーバーを停止・登録解除しました。")
        except Exception as e:
            print(f"[-] 停止中にエラーが発生しました: {e}")

    files_to_remove = [
        SERVER_DEST_PATH,
        SERVER_LOCAL_PLIST_PATH,
        os.path.join(PROJECT_DIR, "server_out.log"),
        os.path.join(PROJECT_DIR, "server_err.log")
    ]
    
    for path in files_to_remove:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    print("[+] 常駐Webサーバーを無効化しました。")

def show_status():
    print("[*] アシスタントサービスの稼働ステータスを確認しています...")
    
    trigger_active = is_service_running(PLIST_LABEL)
    server_active = is_service_running(SERVER_LABEL)
    
    print("\n--- サービス稼働ステータス ---")
    print(f"  1. Webサーバー (FastAPI)     : {'【 ON 】 (常駐稼働中)' if server_active else '【 OFF 】 (停止中)'}")
    if server_active:
        print("     URL: http://localhost:8000")
    print(f"  2. 画面ロック解除トリガー    : {'【 ON 】 (監視中)' if trigger_active else '【 OFF 】 (停止中)'}")
    print("-------------------------------\n")

def show_usage():
    print("利用方法:")
    print("  python3 manage_trigger.py enable         : ロック解除トリガーを有効化")
    print("  python3 manage_trigger.py disable        : ロック解除トリガーを無効化")
    print("  python3 manage_trigger.py enable-server  : Webサーバーを常駐起動 (ON)")
    print("  python3 manage_trigger.py disable-server : Webサーバーの常駐起動を解除 (OFF)")
    print("  python3 manage_trigger.py status         : 全体ステータスを確認")
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
    elif command == "enable-server":
        enable_server()
    elif command == "disable-server":
        disable_server()
    elif command == "status":
        show_status()
    else:
        print(f"[-] 未知のコマンドです: {sys.argv[1]}")
        show_usage()
        sys.exit(1)
