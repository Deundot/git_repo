#!/usr/bin/env python3
import os
import sys
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict

# ==========================================
# [기본 사용자 설정 영역]
# ==========================================
BASE_WORKSPACE = "/Users/daeun/http"
AUTHOR = "최다은"
DEFAULT_DAYS = 7  # 명령어 뒤에 아무것도 안 붙였을 때의 기본 조회 기간
# ==========================================

def find_git_repositories(base_path):
    """하위 모든 깊이에서 .git 폴더가 있는 경로를 재귀적으로 탐색합니다."""
    repo_paths = []
    if not os.path.isdir(base_path):
        print(f"❌ 경고: 기준 디렉토리를 찾을 수 없습니다: {base_path}")
        return repo_paths
        
    for root, dirs, files in os.walk(base_path):
        if '.git' in dirs:
            repo_paths.append(root)
            dirs.remove('.git')
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
    """터미널에서 넘어온 인자를 해석하여 조회 시작 날짜를 반환합니다."""
    if len(sys.argv) < 2:
        since_datetime = datetime.now() - timedelta(days=DEFAULT_DAYS)
        print(f"ℹ️ 기간 미지정: 기본 설정에 따라 최근 {DEFAULT_DAYS}일치 데이터를 수집합니다.")
        return since_datetime.strftime("%Y-%m-%d 00:00:00")
        
    arg = sys.argv[1]
    
    # 케이스 1: 6자리 숫자 입력 (날짜 형식 YYMMDD 검증)
    if len(arg) == 6 and arg.isdigit():
        try:
            # 260601 -> 2026-06-01로 변환
            parsed_date = datetime.strptime(arg, "%y%m%d")
            date_str = parsed_date.strftime("%Y-%m-%d")
            print(f"ℹ️ 날짜 지정: {date_str} 00:00:00 이후 데이터를 수집합니다.")
            return f"{date_str} 00:00:00"
        except ValueError:
            pass # 6자리 숫자이지만 올바른 날짜가 아닌 경우 아래 단순 숫자 일수 케이스로 이동
            
    # 케이스 2: 일반 숫자 입력 (예: 3 -> 최근 3일간)
    if arg.isdigit():
        days = int(arg)
        since_datetime = datetime.now() - timedelta(days=days)
        print(f"ℹ️ 숫자 지정: 최근 {days}일치 데이터를 수집합니다.")
        return since_datetime.strftime("%Y-%m-%d 00:00:00")
        
    # 예외 처리
    print(f"❌ 입력 오류: '{arg}'는 올바른 옵션이 아닙니다. (6자리 날짜 YYMMDD 또는 일수 숫자 입력)")
    print(f"ℹ️ 기본값인 최근 {DEFAULT_DAYS}일치 데이터로 대체 수집합니다.")
    since_datetime = datetime.now() - timedelta(days=DEFAULT_DAYS)
    return since_datetime.strftime("%Y-%m-%d 00:00:00")

def main():
    print("=" * 70)
    print("  Git Terminal-to-Sheet Reporter")
    print("=" * 70)
    
    since_date_str = parse_arguments()
    
    repositories = find_git_repositories(BASE_WORKSPACE)
    print(f"✅ 총 {len(repositories)}개의 Git 리포지토리를 감지했습니다.")
    
    raw_total_logs = []
    commit_groups = defaultdict(list)
    
    for repo in repositories:
        repo_name = os.path.basename(os.path.normpath(repo))
        logs = get_git_log_detailed(repo, AUTHOR, since_date_str)
        
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
        # repo_name을 20칸짜리 고정 너비로 채워 정렬합니다.
        padded_repo = f"{repo_name:<20}"
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