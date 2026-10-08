# Claude Code adapter

~/.claude/CLAUDE.md의 관리 블록에서 공통 지침을 읽도록 안내한다. agents/에 YAML front matter가 있는 두 reviewer Markdown을 생성한다. model: inherit, tools: Read, Grep, Glob로 제한한다. RUN/ENV에 필요한 실제 실행은 주 세션에 요청하고 직접/전달 근거를 구분한다. source 정본은 설치 current의 agents/와 rules/다.

참고: https://code.claude.com/docs/en/memory 및 https://code.claude.com/docs/en/sub-agents
