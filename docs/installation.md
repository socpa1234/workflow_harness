# 설치와 제거

Python 3.9 이상이 필요하며 macOS 다운로드에는 curl, 프로젝트 init에는 Git이 필요하다. 하네스는 관리자 권한과 pip 패키지를 요구하지 않는다. v0.2.0은 macOS와 Windows 네이티브를 대상으로 한다. 이전 v0.1.2는 macOS용이다. Linux·WSL은 지원 범위 밖이다.

## Windows 네이티브

PowerShell 5.1 이상에서 현재 소스 폴더의 설치기를 실행한다. 독립 설치기는 v0.2.0 릴리스의 install.ps1을 다운로드해 --version v0.2.0으로 실행한다(README의 HTTPS 설치 예시 참조). Python은 PATH의 python, py -3, python3 순으로 확인하며 Microsoft Store의 미설치 실행 별칭은 건너뛴다. Python이나 앱 자체를 자동 설치·업데이트하지 않는다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 --dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 --yes
$harness = "$env:LOCALAPPDATA\workflow-harness\bin\workflow-harness.cmd"
& $harness status
& $harness init "C:\work\my repo" --yes
```

실행 정책 옵션은 해당 프로세스에만 적용하며 조직 정책을 우회하지 않는다. 기본 root는 `%LOCALAPPDATA%\workflow-harness`, bin은 root 아래 `bin`이다. `--root`와 `--bin-dir`로 바꾸면 이후 명령에도 같은 root를 전달한다. PATH를 자동 변경하지 않으며 실행기는 설치 시 사용한 Python 절대 경로를 사용하므로 Python을 옮기면 복구/재설치가 필요하다.

신규 설치에서 `--tool`을 생략하면 발견한 Codex·Claude를 모두 선택한다. 한 도구만 있으면 그 도구만 설치한다. `--tool codex|claude|both`로 지정할 수도 있으며, 미발견 대상은 변경 없이 중단한다. 설정 폴더만 남아 있는 경우를 설치된 앱으로 판단하지 않는다.

탐지 범위는 PATH의 CLI, 사용자 native/npm 경로, `CODEX_INSTALL_DIR`, Codex standalone 기본 경로, 현재 사용자 MSIX의 `OpenAI.Codex` 및 `Claude`, 일반 EXE 기본 폴더다. MSIX는 각 이름을 별도로 조회하며 관리자 조회나 전체 디스크 검색은 하지 않는다. 패키지 조회 실패는 별도로 알린다. 사용자 지정/자동 탐지되지 않는 EXE는 다음처럼 지정한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 --codex-app "D:\Apps\Codex.exe" --claude-app "D:\Apps\Claude.exe" --dry-run
```

Codex에는 `CODEX_HOME` 또는 `%USERPROFILE%\.codex`, Claude에는 `CLAUDE_CONFIG_DIR` 또는 `%USERPROFILE%\.claude`의 사용자 지침과 검토자를 설치한다. 환경 변수를 따로 지정했다면 앱도 같은 설정 홈을 사용하도록 시작해야 한다. 앱 실행 파일은 탐지 근거이며, 앱 디렉토리·인증 정보·앱 업데이트 설정은 변경하지 않는다. 대상은 네이티브 Codex와 Claude Code의 로컬 Code 탭이다. 일반 Chat/Cowork, WSL·원격 세션은 대상이 아니다.

Windows에는 심볼릭 링크/junction을 만들지 않고 버전별 release 절대 경로를 참조한다. 한글·공백 경로를 지원하고 UTF-8을 사용한다. `.cmd` 실행기는 콘솔 코드 페이지를 UTF-8로 전환한다. 실행기/Python/root/bin 경로의 `%`, 따옴표, 줄바꿈은 설치 전 거부한다. 기존 reparse/junction으로 관리 경로가 우회되면 중단한다. 사용자 설정 보존·백업·실패 복구·소유 항목 충돌 검사는 macOS와 같은 코어를 사용한다.

업데이트는 게시된 버전을 지정해 다음처럼 실행한다. 업데이트는 기존 도구 선택·설정 경로를 유지하며, 앱이 잠시 미발견되어도 기존 관리 설정을 업데이트할 수 있다. 다른 도구를 자동 추가하지 않는다.

```powershell
$version = 'v0.2.0'
& $harness update --version $version --dry-run
& $harness update --version $version --yes
& $harness uninstall --dry-run
& $harness uninstall --yes
```

macOS v0.1.2 설치는 v0.2.0으로 업데이트할 수 있다. 같은 버전의 다른 내용으로 덮어쓰는 것은 거부하며 개발 시험은 별도 root/bin을 사용한다. `install.ps1`은 독립 릴리스 자산이다. 독립 설치기는 `--version`으로 버전을 고정해 HTTPS 패키지·SHA256SUMS를 검증하고, 각 리다이렉트도 HTTPS로 제한한다. tar 파일 목록은 구 v0.1.2 macOS updater와 호환되도록 유지한다.

Windows/macOS CI를 구성했으며 Windows PowerShell5.1/Python3.9, pwsh/Python3.12에서 native 실행기·실제 junction·현재 사용자 MSIX 조회를 검사한다. 릴리스는 이 CI가 모두 성공해야 게시한다. 실제 실행 결과는 해당 태그의 Actions run에서 확인한다. Mac의 pwsh 실행과 OS mock 결과만으로 Windows 실행 통과를 판단하지 않는다. 새 Codex/Claude Code 앱 세션에서 공통 규칙과 두 reviewer가 보이는지는 사용자 환경에서 별도 확인해야 한다.

## 로컬 검증

다음은 macOS 명령이다.

```sh
sh install.sh --tool both --dry-run
sh install.sh --tool both --yes
~/.local/bin/workflow-harness status
~/.local/bin/workflow-harness init /path/to/repo --yes
```

기본 설치 위치는 ~/.local/share/workflow-harness, 명령 위치는 ~/.local/bin/workflow-harness다. --root와 --bin-dir로 변경할 수 있다. 커스텀 root를 사용했다면 이후 status/update/uninstall에도 같은 --root를 전달한다. 사용자 PATH는 자동 수정하지 않는다.

## HTTPS 설치

아래 명령은 GitHub Release v0.2.0의 고정 URL을 사용한다.

```sh
curl --proto '=https' --proto-redir '=https' -fL \
  https://github.com/socpa1234/workflow_harness/releases/download/v0.2.0/install.sh \
  -o /tmp/workflow-harness-install.sh
sh /tmp/workflow-harness-install.sh --version v0.2.0 --tool both --dry-run
sh /tmp/workflow-harness-install.sh --version v0.2.0 --tool both --yes
```

버전별 패키지와 SHA256SUMS를 받아 검증 후 설치한다. 체크섬은 파일 일치 확인이며 동일 GitHub 출처 자체의 진위를 별도로 보증하지 않는다. 기본 CLI는 HTTPS URL만 사용한다. 별도 로컬 아카이브는 --archive와 --checksums를 함께 지정한다.

## 기존 설정과 데이터

기존 개인 AGENTS.md / CLAUDE.md는 하네스 관리 블록만 추가한다. 지침 파일 symlink, 기존 비소유 reviewer 등록, 수정된 관리 블록·설치 파일은 덮어쓰지 않고 중단한다. 기존 plan-reviewer 링크가 개발 체크아웃의 .codex/agents/plan-reviewer.toml을 가리키고 내용이 배포된 개발 등록 원본과 일치하면 백업 전환한다. 다른 링크·파일은 충돌로 보존한다.

변경 목록은 항상 표시한다. 비대화형 실행은 --yes가 필요하며 --dry-run은 설치 설정을 변경하지 않는다. root/backups/에 변경 전 내용과 복구 자료가 남는다. 실행 중 강제 종료 후 .lock이 남았다면 재실행하지 말고 backups의 changes.json과 실제 파일을 확인해 복구해야 한다.

update는 기존 도구 선택을 유지한다. 도구 선택 변경은 uninstall 후 install한다. 등록 파일은 읽기 전용으로 시작하므로 RUN/ENV 검토가 필요한 명령은 주 세션에서 수행하고 원본 로그를 전달할 수 있다. 설치가 자동 검토 호출을 강제하지는 않는다.

```sh
workflow-harness update --version v0.2.0 --yes
workflow-harness uninstall --dry-run
workflow-harness uninstall --yes
```

제거는 관리 항목을 복원하고 CLI 실행기와 macOS의 current 연결을 제거한다. 릴리스·백업 디렉토리와 프로젝트 .harness는 보존한다. 과거 버전 디렉토리는 자동 삭제하지 않는다. 동일 내용의 버전은 재설치에 재사용하며, 같은 버전에 다른 내용이 있으면 중단한다.

## 프로젝트 작업 공간

init은 Git 루트에 .harness/plans와 memory/current.md, progress, history를 생성한다. git rev-parse --git-path info/exclude에 /.harness/를 추가하고 제외 동작을 확인한다. 공유 .gitignore를 수정하거나 파일을 스테이징하지 않는다. 기존 계획과 메모리는 보존한다. 다른 clone/환경으로의 자동 동기화는 지원하지 않는다.

## 새 세션 확인

Codex/Claude Code를 새로 시작해 공통 규칙 위치와 두 검토자 역할을 확인한다. Codex의 AGENTS.override.md가 개인 지침을 가리거나 조직 정책이 적용되면 해당 설정부터 확인한다. 설치 검증과 실제 도구의 역할 발견은 별도이며 최종 HTTPS 다운로드·설치는 사용자가 수행한다.

## 릴리스 준비

```sh
python3 -m unittest discover -s tests -v
python3 scripts/package.py
```

정식 패키징은 깨끗하게 커밋된 소스를 요구한다. 로컬 시험만 --allow-dirty로 만들 수 있으며 RELEASE.json에 development_build=true가 표시된다. dist의 네 파일을 동일 소스 커밋의 GitHub Release에 첨부한다. .harness 및 인증 정보는 allowlist에 포함하지 않는다. 태그·릴리스 게시 전 소스 커밋과 게시 권한을 확인한다.

`VERSION`을 변경하고 소스를 커밋한 뒤 해당 버전 태그를 푸시하면 `.github/workflows/release.yml`이 공통 Windows/macOS 검사를 통과한 뒤 깨끗한 소스를 패키징하여 tar.gz, install.sh, install.ps1, SHA256SUMS 네 자산을 게시한다. `main` 푸시만으로 게시하지 않는다. 태그와 VERSION이 다르거나 테스트가 실패하면 게시를 중단한다. 기존 릴리스는 덮어쓰지 않는다. 다음 릴리스 전 `docs/release-notes.md`도 갱신한다.
