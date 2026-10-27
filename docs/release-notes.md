Human Bottleneck — Workflow Harness v0.2.0 릴리스입니다.

- Windows 네이티브 PowerShell 설치·업데이트·제거를 추가했습니다. Codex와 Claude Code는 CLI뿐 아니라 데스크톱 앱만 설치된 경우도 탐지하며, 사용자 지침과 두 검토자를 연결합니다. 대상은 네이티브 Codex와 Claude Code 로컬 Code 탭입니다.
- Windows는 관리자 권한이나 심볼릭 링크 생성 없이 설치합니다. 한글·공백 경로, 사용자 지정 설정 홈, 설치 미리보기, 기존 설정 보존, 백업·실패 복구를 지원합니다.
- Plan별 브랜치에 검증한 변경 단위별 중간 커밋을 쌓도록 규칙을 보완했습니다. 같은 Plan의 Task는 브랜치를 공유하며 작은 Task는 묶고 큰 Task는 나눌 수 있습니다. 커밋 전에 필요한 검사·검토와 지적 처리를 마치고, 개인 계획 ID는 공유 커밋 메시지에 넣지 않습니다.
- macOS v0.1.2에서 업데이트할 수 있도록 압축 패키지의 기존 파일 목록을 유지했습니다. install.ps1은 별도 릴리스 자산으로 제공합니다. HTTPS 다운로드는 각 리다이렉트도 HTTPS로 제한합니다.
- Windows PowerShell 5.1/Python 3.9, PowerShell 7/Python 3.12, macOS의 설치·실행기·패키징 검사를 릴리스 필수 CI로 연결했습니다.

Python 3.9 이상이 필요합니다. 설치 방법은 README와 docs/installation.md를 참고하세요. 자산은 install.sh, install.ps1, 버전 고정 tar.gz 패키지, SHA256SUMS입니다. 업데이트는 도구 선택과 기존 사용자 설정을 보존하며 Codex·Claude 앱 자체의 버전은 바꾸지 않습니다.

설치·업데이트 후 새 Codex/Claude Code 세션에서 공통 규칙과 두 reviewer를 확인하세요. 실제 앱 로그인·새 세션 로딩과 규칙 준수 효과는 자동 설치 검사와 별도로 확인해야 합니다. Linux·WSL은 지원 범위 밖입니다.
