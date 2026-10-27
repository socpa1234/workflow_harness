# Claude Code adapter

CLAUDE_CONFIG_DIR(미지정 시 ~/.claude)의 CLAUDE.md 관리 블록에서 공통 지침을 읽도록 안내한다. agents/에 YAML front matter가 있는 두 reviewer Markdown을 생성한다. model: inherit, tools: Read, Grep, Glob로 제한한다. RUN/ENV에 필요한 실제 실행은 주 세션에 요청하고 직접/전달 근거를 구분한다. source 정본은 설치된 버전의 agents/와 rules/다.

Windows는 CLI 또는 Claude 데스크톱 앱만 설치된 경우도 탐지하며, 로컬 Code 탭에서 공유하는 사용자 설정을 대상으로 한다. 기본 설정 홈은 %USERPROFILE%\.claude다. 일반 Chat/Cowork·WSL·원격 세션은 대상으로 하지 않는다. 탐지·파일 생성과 실제 새 세션의 reviewer 로드는 구분한다. macOS는 current 연결, Windows는 releases/<version> 직접 참조를 사용한다.

참고: https://code.claude.com/docs/en/memory, https://code.claude.com/docs/en/sub-agents, https://code.claude.com/docs/en/settings, https://code.claude.com/docs/en/desktop, https://support.claude.com/en/articles/12622703-deploy-claude-desktop-for-windows
