# 인간이 병목이다
## Human Bottleneck — Workflow Harness

**AI가 계획하고 만들고 검토한다. 사람은 방향을 정하고, 계획을 다듬고, 진행을 승인한다.**

Human Bottleneck은 사람의 검토와 승인을 중심에 둔 개인용 에이전트 작업 하네스입니다. Codex와 Claude Code에 공통 작업 규칙, 독립 검토자, 프로젝트별 계획·메모리 구조를 연결합니다.

새 세션에서도 같은 규칙과 기록으로 작업을 이어가고 싶은 사람, 코드 작성 전에 계획을 보고 수정하는 사람을 위한 프로젝트입니다.

> v0.2.0은 macOS와 Windows 네이티브 설치를 지원합니다. Windows/macOS CI 통과 후 버전 태그로 GitHub Release를 배포합니다. 실제 앱 새 세션의 지침·역할 로딩은 사용자 환경에서 확인합니다. 프로젝트 표시명은 Human Bottleneck이며 저장소와 명령 이름은 현재 `workflow_harness` / `workflow-harness`를 사용합니다.

## 어떻게 작업하나요?

관련 코드를 조사한 뒤 요구·구현 방향·영향 범위·검사 방법·복구가 명확한 작업은 접근 설명 → 구현 → 검사 → 결과 보고의 간소 경로를 사용합니다. 별도 계획과 계획 리뷰를 만들지 않으며, 중요한 위험의 불확실성이 남으면 결과 리뷰를 받습니다. 설계 선택이나 영향 확대가 발견되면 아래 정식 경로로 전환합니다.


```text
요구사항
  → 계획 작성
  → 독립 계획 검토
  → 사용자 검토·보완·진행 승인
  → 구현과 검사·테스트
  → 독립 결과 검토·수정
  → 진행·결정·다음 작업을 메모리에 기록
```

- **영향에 맞는 계획:** 작은 수정은 T(Task), 흐름·구조 변경은 P(Plan)와 T, 새로운 개념과 방향이 필요하면 S(Spec)부터 작성합니다.
- **계획 간 정합성:** 상위 문서·버전·선행 작업을 명시합니다. 상위 방향이 바뀌면 하위 계획을 무효화하고 다시 검토합니다.
- **분리된 검토:** 계획 검토자와 구현 결과 검토자가 원본 자료를 확인합니다. 결과 검토는 코드(CODE), 실행(RUN), 대상 환경(ENV)으로 범위를 나눕니다.
- **세션을 잇는 메모리:** 현재 요약, 계획별 진행, 원본 이력을 연결합니다. coding·infra처럼 서로 다른 순차 세션도 같은 프로젝트 맥락을 읽습니다.
- **개인 작업 공간:** 계획·메모리는 코드 레포의 `.harness/`에 두고 로컬 Git 제외 설정으로 관리합니다. 팀의 공유 `.gitignore`는 수정하지 않습니다.

검토 호출 시점은 에이전트 지침으로 안내합니다. 설치 자체가 자동 호출을 강제하는 것은 아니며, 독립 리뷰가 실제 테스트나 사용자 승인을 대신하지 않습니다.

## 설치 전 준비

- macOS 또는 Windows 네이티브(PowerShell 5.1 이상)
- Python 3.9 이상 (`python3 --version`으로 확인)
- macOS HTTPS 다운로드용 `curl`, 프로젝트 초기화용 `git`
- Windows에는 Codex 또는 Claude Code의 CLI나 데스크톱 앱이 설치되어 있어야 합니다.
- 사용할 Codex 또는 Claude Code

Python이 없으면 먼저 설치해야 합니다. 별도 pip 패키지나 하네스 설치를 위한 관리자 권한은 필요하지 않습니다. Linux·WSL은 지원 범위 밖입니다.

## 설치하기

### Windows 네이티브 — 현재 소스에서 설치

현재 체크아웃의 `install.ps1`이 있는 폴더에서 PowerShell로 실행합니다. 아래 실행 정책 옵션은 이 프로세스에만 적용됩니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 --dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 --yes
& "$env:LOCALAPPDATA\workflow-harness\bin\workflow-harness.cmd" status
```

CLI가 없어도 Codex·Claude 데스크톱 앱을 탐지합니다. 설치 전에 발견한 대상과 설정 경로를 표시하며, `--tool codex|claude|both`로 범위를 지정할 수 있습니다. 자동 탐지되지 않는 일반 EXE 설치는 `--codex-app "C:\path\Codex.exe"` 또는 `--claude-app "C:\path\Claude.exe"`로 지정합니다. 앱의 네이티브 Codex 또는 Claude **Code 탭의 로컬 세션**이 대상입니다.

기본 설치 위치는 `%LOCALAPPDATA%\workflow-harness`, 실행기는 그 안의 `bin\workflow-harness.cmd`입니다. 새 PowerShell 프로세스에서 실행기를 호출하면 콘솔 코드 페이지를 UTF-8로 전환합니다. 새 앱 세션에서 규칙과 검토자 두 개가 로드되는지 확인하세요. 자세한 [Windows 설치·업데이트 안내](docs/installation.md#windows-네이티브)를 참고하세요.

### Windows — GitHub 릴리스에서 설치

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/socpa1234/workflow_harness/releases/download/v0.2.0/install.ps1' -OutFile "$env:TEMP\workflow-harness-install.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\workflow-harness-install.ps1" --version v0.2.0 --dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\workflow-harness-install.ps1" --version v0.2.0 --yes
```

기존 v0.1.2 설치 파일은 macOS용입니다. Windows에는 v0.2.0 이상을 사용하세요.

### GitHub에서 다운로드

macOS에서는 [v0.2.0 릴리스](https://github.com/socpa1234/workflow_harness/releases/tag/v0.2.0)의 설치 파일을 사용합니다.

```sh
curl --proto '=https' --proto-redir '=https' -fL \
  https://github.com/socpa1234/workflow_harness/releases/download/v0.2.0/install.sh \
  -o /tmp/workflow-harness-install.sh

# 먼저 변경될 파일을 확인합니다.
sh /tmp/workflow-harness-install.sh --version v0.2.0 --tool both --dry-run

# 확인한 설정을 적용합니다.
sh /tmp/workflow-harness-install.sh --version v0.2.0 --tool both --yes
```

`--tool`은 `codex`, `claude`, `both` 중 선택합니다. 버전별 패키지와 체크섬을 확인한 뒤 규칙·역할·CLI를 함께 설치합니다.

### 현재 로컬 체크아웃에서 설치

macOS 로컬 소스는 아래 명령으로 설치합니다. 현재 소스의 VERSION은 `v0.2.0`입니다. 수정한 개발 소스를 같은 버전으로 덮어쓰면 거부되므로 개발 시험에는 별도 `--root`와 `--bin-dir`를 사용하세요.

이 README와 `install.sh`가 있는 디렉토리에서 실행합니다.

```sh
sh install.sh --tool both --dry-run
sh install.sh --tool both --yes
```

기존 개인 지침에는 관리 블록을 추가하고 검토자 등록을 연결합니다. 다른 사람이 만든 등록 파일이나 수정된 관리 항목과 충돌하면 덮어쓰지 않고 중단합니다. 변경 전 자료는 백업합니다. 자세한 충돌·복구 정책은 [설치 안내](docs/installation.md)를 참고하세요.

## 설치 후 시작하기

macOS에서는 다음처럼 설치 상태를 확인하고 작업할 레포를 초기화합니다. Windows에서는 위 실행기 경로에 같은 `init` 명령을 전달합니다.

```sh
~/.local/bin/workflow-harness status
~/.local/bin/workflow-harness init /path/to/your/repo --dry-run
~/.local/bin/workflow-harness init /path/to/your/repo --yes
```

`/path/to/your/repo`는 실제 작업 레포 경로로 바꿉니다. 초기화하면 다음 개인 작업 공간을 만들고 로컬 `.git/info/exclude`에 등록합니다. worktree에서는 Git이 알려주는 실제 제외 파일을 사용합니다.

```text
.harness/
  plans/                  # 작업별 폴더 ([done]- 접두사로 완료 표시)
    <작업명>/             # S/P/T; S가 있을 때만 index.md
      history/            # 이전 계획 revision
  memory/
    current.md            # 새 세션이 먼저 읽는 맥락과 재개 지점
    progress/             # 계획 ID별 실제 진행
    history/              # 결정·문제 해결·작업의 원본 이력
```

이 기록은 Git 커밋에 포함되지 않으며 다른 clone이나 컴퓨터에 자동으로 동기화되지 않습니다. 기존 기록은 초기화 시 보존합니다.

Codex 또는 Claude Code를 **새 세션으로 시작**하고, 공통 지침과 두 검토자 역할을 읽을 수 있는지 확인하세요. 첫 요청은 다음처럼 시작할 수 있습니다.

> 이 레포의 지침과 .harness 메모리를 확인하고, 요구사항에 맞는 계획부터 작성해줘. 사용자 검토에 올리기 전에 계획 검토자를 호출해줘.

## 업데이트와 제거

자동 업데이트는 하지 않습니다. 게시된 버전을 지정해서 업데이트합니다.

아래 업데이트 예시는 macOS용입니다. Windows에서는 실행기에 `update --version v0.2.0 --yes`를 전달합니다. 도구 선택은 유지하며, Claude Code·Codex 앱 자체의 버전은 바꾸지 않습니다.

```sh
# 게시된 버전으로 업데이트합니다.
~/.local/bin/workflow-harness update --version v0.2.0 --yes

~/.local/bin/workflow-harness uninstall --dry-run
~/.local/bin/workflow-harness uninstall --yes
```

업데이트는 기존 도구 선택을 유지합니다. 도구 선택을 바꾸려면 제거 후 다시 설치합니다. 제거 시 관리 설정과 연결을 복원하며 프로젝트의 `.harness/`, 설치 버전과 백업 자료는 보존합니다.

기본 설치 위치는 `~/.local/share/workflow-harness`, 명령 위치는 `~/.local/bin/workflow-harness`입니다. `--root`와 `--bin-dir`로 변경할 수 있습니다. 사용자 PATH는 자동 수정하지 않습니다. 커스텀 root를 사용했다면 이후 명령에도 같은 `--root`를 전달하세요.

## 규칙을 살펴보고 싶다면

| 문서 | 내용 |
| --- | --- |
| [공통 규칙](rules/AGENTS.md) | 작업 흐름, 지침 탐색, 메모리 복원과 검토 호출 |
| [계획 거버넌스](rules/governance/planning.md) | S/P/T, 리비전, 의존성, 무효화와 로컬 Git 관리 |
| [메모리 작성 거버넌스](rules/governance/memory-writing.md) | 기록·갱신·요약 압축·원본 보존 |
| [계획 검토자](agents/plan-reviewer.md) | 계획 정합성과 리비전 필수 검사 |
| [결과 검토자](agents/implementation-reviewer.md) | CODE/RUN/ENV 검토와 실행 근거 |
| [설치 안내](docs/installation.md) | 설치·충돌·백업·제거·릴리스 준비 |
| [로드맵](docs/roadmap.md) | 합의한 방향과 앞으로 다룰 과제 |

이 프로젝트는 실제 작업 경험으로 규칙을 다듬어 갑니다. 공통 규칙은 시스템·조직의 상위 지침을 대체하지 않으며 프로젝트별 지침과 함께 적용합니다.
