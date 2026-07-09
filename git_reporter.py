#!/usr/bin/env python3

import json
import os
import sys
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor  # 💡 병렬 처리를 위한 내장 모듈

# ==========================================
# [기본 설정 영역]
# ==========================================
DEFAULT_DAYS = 7  # 명령어 뒤에 아무것도 안 붙였을 때의 기본 조회 기간

# 현재 실행 중인 파일(또는 빌드된 파일)의 실제 폴더 경로를 구합니다.
if getattr(sys, 'frozen', False):
    # PyInstaller로 빌드된 실행 파일 형태일 때
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 일반 .py 파이썬 스크립트 형태일 때
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 무조건 실행 파일과 '같은 폴더'에 config.json이 위치하도록 절대 경로로 지정
CONFIG_FILE = os.path.join(BASE_DIR, 'git_repo_config.json')

def load_or_create_config():
    """config.json 파일이 있으면 불러오고, 없으면 사용자 입력을 받아 생성합니다."""
    # 1. 기존 설정 파일이 존재하는지 확인
    if os.path.exists(CONFIG_FILE):
        print("기존 설정 파일을 불러오는 중...")
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            try:
                config = json.load(f)
                return config
            except json.JSONDecodeError:
                print("설정 파일이 손상되었거나 형식이 올바르지 않습니다. 새로 설정합니다.")

    # 2. 파일이 없거나 오류가 있다면 사용자에게 직접 입력 받기
    print("=== 초기 설정이 필요합니다 ===")
    config = {}
    
    print("사용자의 git Author를 입력해주세요.")
    config['AUTHOR'] = input("=> ")
    print("=========================")
    
    print("프로젝트가 있는 상위 폴더 경로를 입력하세요.")
    print("입력 예시: /Users/daeun/http")
    config['BASE_WORKSPACE'] = input("=> ")
    
    print("=========================")
    
    
    
    # 사용자에게 쉼표 기준으로 입력받기
    print(" ❌ 제외할 디렉터리 경로를 쉼표(,)로 구분해서 입력해주세요. ")
    print("입력 예시: daeun, /Users/daeun/http/daeun")
    user_input = input("=> ")
    print("=========================")
    
    # 양쪽 공백을 제거하고 리스트로 분리
    dir_list = [d.strip() for d in user_input.split(',') if d.strip()]
    
    config['EXCLUDE_DIRS'] = set(dir_list)
    # JSON 파일로 저장할 때는 set을 list로 변환해야 에러가 나지 않습니다.
    # 1. 파일에 저장하기 위해 config의 복사본을 만듭니다.
    json_data = config.copy()
    
    # 2. set 형태인 EXCLUDE_DIRS를 JSON이 저장할 수 있는 list 형태로 변환합니다.
    if 'EXCLUDE_DIRS' in json_data and isinstance(json_data['EXCLUDE_DIRS'], set):
        json_data['EXCLUDE_DIRS'] = list(json_data['EXCLUDE_DIRS'])

    # 3. config 대신 list로 변환된 json_data를 저장합니다.
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=4, ensure_ascii=False)
    
    print(f"설정이 완료되었습니다! '{CONFIG_FILE}' 파일에 저장되었습니다.\n")
    return config
# ==========================================

def find_git_repositories(base_path):
    config = load_or_create_config()
    
    """무거운 폴더 및 사용자가 지정한 폴더를 스킵하고, .git 발견 시 하위 탐색을 중단합니다."""
    repo_paths = []
    if not os.path.isdir(base_path):
        print(f"❌ 경고: 기준 디렉토리를 찾을 수 없습니다: {base_path}")
        return repo_paths
        
    # 기본 의존성 폴더 목록 + 사용자 제외 폴더 목록 병합
    SKIP_DIRS = { 'node_modules', 'vendor', '.venv', 'venv', 'target', 'build' }
    
    # 이제 기존 코드처럼 집합(set)으로 바로 사용 가능합니다.
    EXCLUDE_DIRS = config.get('EXCLUDE_DIRS', set())
    
    for root, dirs, files in os.walk(base_path):
        # 💡 1. 사용자 설정(EXCLUDE_DIRS)에 따른 필터링 로직 추가
        filtered_dirs = []
        for d in dirs:
            full_path = os.path.join(root, d)
            # 폴더명이 SKIP_DIRS/EXCLUDE_DIRS에 있거나, 전체 경로가 EXCLUDE_DIRS에 있으면 제외
            if d in SKIP_DIRS or d in EXCLUDE_DIRS or full_path in EXCLUDE_DIRS:
                continue
            filtered_dirs.append(d)
        
        # os.walk의 탐색 대상을 필터링된 결과로 교체
        dirs[:] = filtered_dirs
        
        if '.git' in dirs:
            repo_paths.append(root)
            dirs.clear() 
            
    return repo_paths

def get_git_log_detailed(repo_path, author, since_date):
    """지정된 리포지토리에서 커밋 로그를 수집합니다."""
    cmd = [
        "git", "-C", repo_path, "log",
        f"--since={since_date}",
        "--date=short",
        "--format=%ad\t%s"
    ]
    if author:
        cmd.append(f"--author={author}")
        
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    except:
        return []

def parse_arguments():
    """터미널 인자 또는 사용자 입력을 받아 조회 시작 날짜를 반환합니다."""
    
    # 1. 터미널에서 인자가 넘어왔는지 확인 (예: ./git_reporter 260601)
    if len(sys.argv) >= 2:
        arg = sys.argv[1]
        print(f"➡️ 터미널 입력 인자 감지: {arg}")
    else:
        # 2. 인자가 없다면 (더블 클릭 실행 등), 매번 입력받도록 처리
        print("=== 조회 기간 설정 ===")
        print("- 6자리 날짜 입력 (예: 260601 -> 2026-06-01 이후 조회)")
        print("- 단순 숫자 입력 (예: 3 -> 최근 3일간 조회)")
        print("- [엔터] 그냥 누르면 기본값 (최근 7일간 조회)")
        
        arg = input("=> ").strip()
        
        # 사용자가 아무것도 입력하지 않고 엔터만 친 경우
        if not arg:
            since_datetime = datetime.now() - timedelta(days=DEFAULT_DAYS)
            print(f"ℹ️ 기본 설정 적용: 최근 {DEFAULT_DAYS}일치 데이터를 수집합니다.")
            return since_datetime.strftime("%Y-%m-%d 00:00:00")

    # 3. 입력된 값(arg) 검증 로직 (다은님의 기존 핵심 로직 활용)
    
    # 케이스 1: 6자리 숫자 입력 (날짜 형식 YYMMDD 검증)
    if len(arg) == 6 and arg.isdigit():
        try:
            # 260601 -> 2026-06-01로 변환
            parsed_date = datetime.strptime(arg, "%y%m%d")
            date_str = parsed_date.strftime("%Y-%m-%d")
            print(f"ℹ️ 날짜 지정 완료: {date_str} 00:00:00 이후 데이터를 수집합니다.")
            return f"{date_str} 00:00:00"
        except ValueError:
            pass # 6자리 숫자이지만 올바른 날짜가 아닌 경우 아래 단순 숫자 일수 케이스로 이동
            
    # 케이스 2: 일반 숫자 입력 (예: 3 -> 최근 3일간)
    if arg.isdigit():
        days = int(arg)
        since_datetime = datetime.now() - timedelta(days=days)
        print(f"ℹ️ 숫자 지정 완료: 최근 {days}일치 데이터를 수집합니다.")
        return since_datetime.strftime("%Y-%m-%d 00:00:00")
        
    # 예외 처리 (잘못된 형식 입력 시)
    print(f"❌ 입력 오류: '{arg}'는 올바른 형식이 아닙니다. (6자리 날짜 YYMMDD 또는 일수 숫자 입력)")
    print(f"ℹ️ 기본값인 최근 {DEFAULT_DAYS}일치 데이터로 대체 수집합니다.")
    since_datetime = datetime.now() - timedelta(days=DEFAULT_DAYS)
    return since_datetime.strftime("%Y-%m-%d 00:00:00")

# 💡 병렬 처리를 위해 단일 리포지토리를 작업하는 래퍼 함수 추가
def fetch_repo_logs(repo, author, since_date_str):
    repo_name = os.path.basename(os.path.normpath(repo))
    logs = get_git_log_detailed(repo, author, since_date_str)
    return repo_name, logs

def main():
    config = load_or_create_config()
    
    BASE_WORKSPACE = config.get('BASE_WORKSPACE')
    AUTHOR = config.get('AUTHOR')
    
    print("=" * 70)
    print("  Git Terminal-to-Sheet Reporter")
    print("=" * 70)
    
    since_date_str = parse_arguments()
    
    repositories = find_git_repositories(BASE_WORKSPACE)
    print(f"✅ 총 {len(repositories)}개의 Git 리포지토리를 감지했습니다.")
    
    raw_total_logs = []
    commit_groups = defaultdict(list)
    
    # ThreadPoolExecutor를 사용한 대폭적인 병렬 처리
    # max_workers를 지정하지 않으면 파이썬이 CPU 코어 수에 맞춰 적절히 조절합니다.
    with ThreadPoolExecutor() as executor:
        # 모든 리포지토리에 대해 fetch_repo_logs 함수를 비동기 실행하도록 예약
        futures = [
            executor.submit(fetch_repo_logs, repo, AUTHOR, since_date_str) 
            for repo in repositories
        ]
        
        # 완료된 작업 순서대로 결과를 받아와서 기존 딕셔너리 및 리스트에 취합
        for future in futures:
            repo_name, logs = future.result()
            for log in logs:
                parts = log.split('\t')
                if len(parts) == 2:
                    date, msg = parts
                    raw_total_logs.append((date, repo_name, msg))
                    commit_groups[msg].append(repo_name)

    # [포맷 1] 전체 내역 조립
    raw_total_logs.sort(key=lambda x: x[0], reverse=True)
    format_1_lines = []
    for date, repo_name, msg in raw_total_logs:
        # repo_name을 25칸짜리 고정 너비로 채워 정렬합니다.
        padded_repo = f"{repo_name:<25}"
        format_1_lines.append(f"{date}\t{padded_repo}\t{msg}")

    # [포맷 2] 폴더별 그룹화 요약 조립
    output_groups = defaultdict(list)
    for msg, repo_list in commit_groups.items():
        distinct_repos = sorted(list(set(repo_list)))
        project_key = ", ".join(distinct_repos)  # 무조건 폴더명 나열
        output_groups[project_key].append(msg)

    format_2_lines = []
    for project_key, messages in output_groups.items():
        format_2_lines.append(project_key)
        for msg in set(messages):
            format_2_lines.append(f" - {msg}")
        format_2_lines.append("")

    # 최종 화면 출력
    print(f"\n📅 조회 시작 시점: {since_date_str}")
    
    print("\n▶ [1] 전체 로그 내역 ")
    print( "─" * 68 )
    if format_1_lines:
        print("\n".join(format_1_lines))
    else:
        print("해당 기간 동안 커밋 내역이 없습니다.")
    print( "─" * 68 )
    
    print("\n▶ [2] 폴더별 그룹화 요약 (업무 보고서 텍스트용)")
    print( "─" * 68 )
    if format_2_lines:
        print("\n".join(format_2_lines).strip())
    else:
        print("해당 기간 동안 커밋 내역이 없습니다.")
    print( "─" * 68 )
    
    input("\n👉 복사 완료 후 터미널에서 [Enter] 키를 누르면 프로그램이 종료됩니다...")

if __name__ == "__main__":
    main()