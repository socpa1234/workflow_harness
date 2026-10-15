# 설치와 제거 (macOS 초기 버전)

Python 3.9 이상, curl이 필요하다. 프로젝트 init에는 Git이 필요하다. Python이 없는 Mac은 Python을 먼저 설치해야 한다. 관리자 권한과 pip 패키지는 필요하지 않다. Windows·Linux는 초기 지원 대상이 아니다.

## 로컬 검증

```sh
sh install.sh --tool both --dry-run
sh install.sh --tool both --yes
~/.local/bin/workflow-harness status
~/.local/bin/workflow-harness init /path/to/repo --yes
```

기본 설치 위치는 ~/.local/share/workflow-harness, 명령 위치는 ~/.local/bin/workflow-harness다. --root와 --bin-dir로 변경할 수 있다. 커스텀 root를 사용했다면 이후 status/update/uninstall에도 같은 --root를 전달한다. 사용자 PATH는 자동 수정하지 않는다.

## HTTPS 설치

아래 명령은 GitHub Release v0.1.2의 고정 URL을 사용한다.

```sh
curl --proto '=https' --proto-redir '=https' -fL \
  https://github.com/socpa1234/workflow_harness/releases/download/v0.1.2/install.sh \
  -o /tmp/workflow-harness-install.sh
sh /tmp/workflow-harness-install.sh --version v0.1.2 --tool both --dry-run
sh /tmp/workflow-harness-install.sh --version v0.1.2 --tool both --yes
```

버전별 패키지와 SHA256SUMS를 받아 검증 후 설치한다. 체크섬은 파일 일치 확인이며 동일 GitHub 출처 자체의 진위를 별도로 보증하지 않는다. 기본 CLI는 HTTPS URL만 사용한다. 별도 로컬 아카이브는 --archive와 --checksums를 함께 지정한다.

## 기존 설정과 데이터

기존 개인 AGENTS.md / CLAUDE.md는 하네스 관리 블록만 추가한다. 지침 파일 symlink, 기존 비소유 reviewer 등록, 수정된 관리 블록·설치 파일은 덮어쓰지 않고 중단한다. 기존 plan-reviewer 링크가 개발 체크아웃의 .codex/agents/plan-reviewer.toml을 가리키고 내용이 배포된 개발 등록 원본과 일치하면 백업 전환한다. 다른 링크·파일은 충돌로 보존한다.

변경 목록은 항상 표시한다. 비대화형 실행은 --yes가 필요하며 --dry-run은 설치 설정을 변경하지 않는다. root/backups/에 변경 전 내용과 복구 자료가 남는다. 실행 중 강제 종료 후 .lock이 남았다면 재실행하지 말고 backups의 changes.json과 실제 파일을 확인해 복구해야 한다.

update는 기존 도구 선택을 유지한다. 도구 선택 변경은 uninstall 후 install한다. 등록 파일은 읽기 전용으로 시작하므로 RUN/ENV 검토가 필요한 명령은 주 세션에서 수행하고 원본 로그를 전달할 수 있다. 설치가 자동 검토 호출을 강제하지는 않는다.

```sh
workflow-harness update --version v0.1.2 --yes
workflow-harness uninstall --dry-run
workflow-harness uninstall --yes
```

제거는 관리 항목을 복원하고 current/CLI 연결을 제거한다. 릴리스·백업 디렉토리와 프로젝트 .harness는 보존한다. 과거 버전 디렉토리는 자동 삭제하지 않는다. 동일 내용의 버전은 재설치에 재사용하며, 같은 버전에 다른 내용이 있으면 중단한다.

## 프로젝트 작업 공간

init은 Git 루트에 .harness/plans와 memory/current.md, progress, history를 생성한다. git rev-parse --git-path info/exclude에 /.harness/를 추가하고 제외 동작을 확인한다. 공유 .gitignore를 수정하거나 파일을 스테이징하지 않는다. 기존 계획과 메모리는 보존한다. 다른 clone/환경으로의 자동 동기화는 지원하지 않는다.

## 새 세션 확인

Codex/Claude Code를 새로 시작해 공통 규칙 위치와 두 검토자 역할을 확인한다. Codex의 AGENTS.override.md가 개인 지침을 가리거나 조직 정책이 적용되면 해당 설정부터 확인한다. 설치 검증과 실제 도구의 역할 발견은 별도이며 최종 HTTPS 다운로드·설치는 사용자가 수행한다.

## 릴리스 준비

```sh
python3 -m unittest discover -s tests -v
python3 scripts/package.py
```

정식 패키징은 깨끗하게 커밋된 소스를 요구한다. 로컬 시험만 --allow-dirty로 만들 수 있으며 RELEASE.json에 development_build=true가 표시된다. dist의 세 파일을 동일 소스 커밋의 GitHub Release에 첨부한다. .harness 및 인증 정보는 allowlist에 포함하지 않는다. 태그·릴리스 게시 전 소스 커밋과 게시 권한을 확인한다.

`VERSION`을 변경하고 소스를 커밋한 뒤 해당 버전 태그를 푸시하면 `.github/workflows/release.yml`이 macOS에서 테스트하고 깨끗한 소스를 패키징하여 세 자산을 게시한다. `main` 푸시만으로 게시하지 않는다. 태그와 VERSION이 다르거나 테스트가 실패하면 게시를 중단한다. 기존 릴리스는 덮어쓰지 않는다. 다음 릴리스 전 `docs/release-notes.md`도 갱신한다.
