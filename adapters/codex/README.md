# Codex adapter

CLI는 CODEX_HOME(미지정 시 ~/.codex)의 AGENTS.md에 관리 블록을 추가하고 agents/에 plan-reviewer.toml, implementation-reviewer.toml을 생성한다. 각 등록은 설치된 버전의 역할 정본을 참조하고 모델 설정을 상속한다. 두 검토자는 read-only 기본이며 RUN/ENV 실행은 권한에 맞게 주 세션에 요청할 수 있다. 라이브 런타임 권한은 설치 기본값보다 우선할 수 있으므로 역할 지침의 수정 금지도 함께 따른다.

AGENTS.override.md가 있으면 개인 AGENTS.md가 가려질 수 있으므로 설치 전 충돌을 보고한다. 실제 호출 여부는 새 세션에서 확인한다.

Windows는 CLI 또는 데스크톱 앱만 설치된 경우도 탐지한다. 네이티브 Codex의 기본 설정 홈은 %USERPROFILE%\.codex이며 WSL 세션은 대상이 아니다. macOS는 current 연결, Windows는 releases/<version> 직접 참조를 사용한다. CODEX_INSTALL_DIR와 Windows standalone 기본 경로도 탐지한다. 현재 사용자 OpenAI.Codex MSIX 또는 일반 EXE 경로가 설치 근거이며, 설정 폴더만으로 탐지하지 않는다. 실제 새 앱 세션에서 지침·역할 발견을 별도 확인한다.

참고: https://learn.chatgpt.com/docs/agent-configuration/agents-md, https://learn.chatgpt.com/docs/agent-configuration/subagents, https://learn.chatgpt.com/docs/app/windows, https://learn.chatgpt.com/docs/enterprise/windows-deployment, https://learn.chatgpt.com/docs/config-file/environment-variables
