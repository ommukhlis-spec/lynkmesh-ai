# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | ✅ Active |
| 0.2.x   | ❌ End of life |
| 0.1.x   | ❌ End of life |

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Instead, report them privately via GitHub Security Advisories:

https://github.com/ommukhlis-spec/lynkmesh-ai/security/advisories/new

You can also email the maintainers directly. Expect an acknowledgment within 48 hours and a status update within 5 business days.

## Scope

Security issues in the LynkMesh AI codebase itself (Python source in `lynkmesh_ai/`) are in scope. The following are **not** in scope:

- Vulnerabilities in example code (`examples/`) — these are intentionally simplified demos with hardcoded test credentials.
- Vulnerabilities in provider skeletons (`bridges/providers/`) — these raise `NotImplementedError` and contain no functional code.
- Vulnerabilities in generated artifacts (`.ai/` directory) — these are runtime output, not source code.
- Vulnerabilities in third-party AI services that LynkMesh AI orchestrates (Claude, ChatGPT, Gemini, etc.).

## Architecture Security Properties

- **Zero runtime dependencies.** LynkMesh AI imports only the Python standard library. There are no third-party packages in the dependency tree.
- **No network access by default.** All analysis runs locally. The `AgentProvider` skeletons document integration points for cloud APIs but do not import SDKs or make network calls.
- **No credential storage.** LynkMesh AI does not store API keys, tokens, or passwords. The `.env.example` file documents optional environment variables but no `.env` file is committed.
- **No code execution.** Generated task files (`.ai/inbox/task_*.md`) are plain Markdown. They cannot execute themselves — they must be explicitly consumed by an external agent.
- **Opt-in automation.** All autonomous features require explicit CLI flags (`--semantic`, `--reason`). The default `lynkmesh-ai run` command performs read-only analysis.

## Supply Chain

This project has zero PyPI dependencies. The entire dependency tree is:

```
lynkmesh-ai
  (none)
```

This eliminates supply-chain attacks via dependency confusion, typosquatting, and compromised packages. The only trust boundary is the Python standard library itself.

## Responsible Disclosure

We follow a 90-day disclosure timeline. After a fix is released, the vulnerability details will be published in the GitHub Security Advisory and credited to the reporter (unless anonymity is requested).
