#!/usr/bin/env python3
"""
PickerImportタスクのログを確認するスクリプト

使用例:
  python scripts/check_logs.py --session-id 123
  python scripts/check_logs.py --event picker.session.start --last 10
  python scripts/check_logs.py --last 50 --level INFO
"""

import argparse
import json
import sys
from datetime import datetime, timezone

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, '/home/kyon/myproject')

from core.db import db
from core.models.log import Log
from webapp import create_app


def parse_message_json(message):
    """JSONメッセージをパースして、読みやすい形式で返す"""
    try:
        data = json.loads(message)
        return data
    except json.JSONDecodeError:
        return message


def format_log_entry(log):
    """ログエントリを読みやすい形式でフォーマット"""
    timestamp = log.created_at.strftime("%Y-%m-%d %H:%M:%S")
    
    # JSONメッセージをパース
    parsed_message = parse_message_json(log.message)
    
    if isinstance(parsed_message, dict):
        # 構造化ログの場合
        session_id = parsed_message.get('session_id', 'N/A')
        ts = parsed_message.get('ts', timestamp)
        
        print(f"[{timestamp}] {log.level} - {log.event}")
        print(f"  Session ID: {session_id}")
        
        if 'file_path' in parsed_message:
            print(f"  File: {parsed_message['file_path']}")
            print(f"  Size: {parsed_message.get('file_size', 0):,} bytes")
            print(f"  SHA256: {parsed_message.get('sha256', 'N/A')[:16]}...")
        
        if 'progress' in parsed_message:
            print(f"  Progress: {parsed_message['progress']}")
            print(f"  Imported: {parsed_message.get('imported', 0)}, "
                  f"Duplicates: {parsed_message.get('duplicates', 0)}, "
                  f"Failed: {parsed_message.get('failed', 0)}")
        
        if 'duration_seconds' in parsed_message:
            duration = parsed_message['duration_seconds']
            print(f"  Duration: {duration:.2f}s")
            print(f"  Results: Imported={parsed_message.get('imported', 0)}, "
                  f"Duplicates={parsed_message.get('duplicates', 0)}, "
                  f"Failed={parsed_message.get('failed', 0)}")
        
        if 'error' in parsed_message:
            print(f"  Error: {parsed_message['error']}")
            
        print()
    else:
        # 通常のテキストログ
        print(f"[{timestamp}] {log.level} - {log.event}")
        print(f"  {parsed_message}")
        print()


def main():
    parser = argparse.ArgumentParser(description='PickerImportタスクのログを確認')
    parser.add_argument('--session-id', type=int, help='特定のセッションIDのログのみ表示')
    parser.add_argument('--event', help='特定のイベントタイプのログのみ表示 (例: picker.session.start)')
    parser.add_argument('--level', help='特定のレベルのログのみ表示 (例: INFO, ERROR)')
    parser.add_argument('--last', type=int, default=20, help='最新のN件のログを表示 (デフォルト: 20)')
    parser.add_argument('--json', action='store_true', help='JSON形式で出力')
    
    args = parser.parse_args()
    
    # Flaskアプリを初期化
    app = create_app()
    
    with app.app_context():
        # クエリを構築
        query = Log.query
        
        # フィルタを適用
        if args.session_id:
            query = query.filter(Log.message.contains(f'"session_id": {args.session_id}'))
        
        if args.event:
            query = query.filter(Log.event == args.event)
        
        if args.level:
            query = query.filter(Log.level == args.level.upper())
        
        # Picker関連のイベントのみを対象
        picker_events = [
            'picker.session.start',
            'picker.session.progress', 
            'picker.session.complete',
            'picker.session.error',
            'picker.session.skip',
            'picker.item.claim',
            'picker.item.end',
            'picker.file.saved'
        ]
        query = query.filter(Log.event.in_(picker_events))
        
        # 最新順でソート
        query = query.order_by(Log.created_at.desc())
        
        # 件数制限
        logs = query.limit(args.last).all()
        
        if not logs:
            print("該当するログが見つかりませんでした。")
            return
        
        print(f"最新 {len(logs)} 件のログを表示:\n")
        
        # 古い順に表示するため逆順に
        for log in reversed(logs):
            if args.json:
                log_data = {
                    'id': log.id,
                    'level': log.level,
                    'event': log.event,
                    'message': parse_message_json(log.message),
                    'created_at': log.created_at.isoformat(),
                }
                print(json.dumps(log_data, indent=2, ensure_ascii=False))
            else:
                format_log_entry(log)


if __name__ == '__main__':
    main()
