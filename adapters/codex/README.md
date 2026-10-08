# Codex adapter

CLI는 CODEX_HOME(미지정 시 ~/.codex)의 AGENTS.md에 관리 블록을 추가하고 agents/에 plan-reviewer.toml, implementation-reviewer.toml을 생성한다. 각 등록은 설치 current의 역할 정본을 참조하고 모델 설정을 상속한다. 두 검토자는 read-only 기본이며 RUN/ENV 실행은 권한에 맞게 주 세션에 요청할 수 있다. 라이브 런타임 권한은 설치 기본값보다 우선할 수 있으므로 역할 지침의 수정 금지도 함께 따른다.

AGENTS.override.md가 있으면 개인 AGENTS.md가 가려질 수 있으므로 설치 전 충돌을 보고한다. 실제 호출 여부는 새 세션에서 확인한다.

참고: https://learn.chatgpt.com/docs/agent-configuration/agents-md 및 https://learn.chatgpt.com/docs/agent-configuration/subagents
