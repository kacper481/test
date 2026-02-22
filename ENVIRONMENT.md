# Mobile Environment Documentation

This document describes the full containerized development environment for the `kacper481/test` repository.

---

## 1. Overview

| Property | Value |
|---|---|
| **Container ID** | `container_01BSg1smH6Vco5YQR6WpKksd--claude_code_remote--5c8796` |
| **Machine ID** | `1fedf2a76df94f808de522c6d6b831a2` |
| **Hostname** | `runsc` |
| **Runtime** | gVisor (sandbox container runtime) |
| **OS** | Ubuntu 24.04.3 LTS (Noble Numbat) |
| **Kernel** | Linux 4.4.0 x86_64 |
| **Disk** | 30 GB total, ~9.2 MB used |
| **Sandbox** | Yes (`IS_SANDBOX=yes`) |

---

## 2. Repository

| Property | Value |
|---|---|
| **Remote URL** | `http://local_proxy@127.0.0.1:43199/git/kacper481/test` |
| **Current Branch** | `claude/document-mobile-environment-EpZFo` |
| **Working Directory** | `/home/user/test` |

### Branches

- `master` (local)
- `claude/document-mobile-environment-EpZFo` (local + remote)
- `origin/main` (remote)
- `origin/claude/create-new-branch-NEQ5U` (remote)

### Repository Contents

- `.gitkeep` — empty marker file
- `container-info.txt` — container ID and machine ID
- `ENVIRONMENT.md` — this file

---

## 3. Installed Languages & Runtimes

| Language | Version | Path |
|---|---|---|
| **Node.js** | v22.22.0 | `/opt/node22/bin/node` |
| **Python** | 3.11.14 | `/usr/local/bin/python3` |
| **Ruby** | 3.3.6 | `/usr/local/bin/ruby` |
| **Java (OpenJDK)** | 21.0.10 | `/usr/bin/java` |
| **Go** | 1.24.7 | `/usr/local/go/bin/go` |
| **Rust** | 1.93.1 | `/root/.cargo/bin/rustc` |
| **Cargo** | 1.93.1 | `/root/.cargo/bin/cargo` |
| **Bun** | 1.3.9 | `/root/.bun/bin/bun` |

### Additional Node.js Versions

Available under `/opt/`:

- `node20`
- `node21` (symlinked to node22)
- `node22` (active)

Managed by **NVM** at `/opt/nvm`.

### Additional Ruby Versions

Available via **rbenv** at `/opt/rbenv`:

- `ruby-3.1.6`
- `ruby-3.2.6`
- `ruby-3.3.6` (active)

---

## 4. Build Tools & Package Managers

| Tool | Version | Path |
|---|---|---|
| **npm** | 10.9.4 | (bundled with Node.js) |
| **Maven** | 3.9.11 | `/opt/maven/bin/mvn` |
| **Gradle** | 8.14.3 | `/opt/gradle/bin/gradle` |
| **NVM** | — | `/opt/nvm` |
| **rbenv** | — | `/opt/rbenv` |
| **Cargo** | 1.93.1 | `/root/.cargo/bin/cargo` |

### System Build Packages

- `build-essential` 12.10ubuntu1
- `cmake` 3.28.3
- `autoconf` 2.71
- `bison` 3.8.2
- `clang-tools-18` 1:18.1.3
- `git`
- `docker-buildx-plugin` 0.31.1

---

## 5. Environment Variables

| Variable | Value |
|---|---|
| `JAVA_HOME` | `/usr/lib/jvm/java-21-openjdk-amd64` |
| `GRADLE_HOME` | `/opt/gradle` |
| `MAVEN_HOME` | `/opt/maven` |
| `RUSTUP_HOME` | `/root/.rustup` |
| `HOME` | `/root` |
| `SHELL` | `/bin/bash` |
| `IS_SANDBOX` | `yes` |

### PATH (key entries)

```
/root/.local/bin
/root/.cargo/bin      # Rust
/usr/local/go/bin     # Go
/opt/node22/bin       # Node.js
/opt/maven/bin        # Maven
/opt/gradle/bin       # Gradle
/opt/rbenv/bin        # Ruby version manager
/root/.bun/bin        # Bun
```

---

## 6. Network & Proxy

All outbound traffic is routed through an HTTP proxy with JWT-based authentication.

| Property | Value |
|---|---|
| **Proxy Host** | `21.0.0.173:15004` |
| **Config Variables** | `GLOBAL_AGENT_HTTP_PROXY`, `JAVA_TOOL_OPTIONS` |

### Allowed Package Registries

- npm registry
- PyPI
- Maven Central
- Gradle Plugins Portal
- Docker Hub
- (and other major repositories)

---

## 7. Claude Code Configuration

| Property | Value |
|---|---|
| **Config Directory** | `/root/.claude/` |
| **Settings File** | `/root/.claude/settings.json` |
| **Git User** | Claude (`noreply@anthropic.com`) |
| **Git Signing** | SSH key at `/home/claude/.ssh/commit_signing_key.pub` |
| **GPG Format** | `ssh` |
| **Code Sign Tool** | `/tmp/code-sign` |

### Settings Summary (`/root/.claude/settings.json`)

```json
{
  "hooks": {
    "Stop": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "~/.claude/stop-hook-git-check.sh"}]
    }]
  },
  "permissions": {"allow": ["Skill"]}
}
```

### Claude Code Directory Structure

```
/root/.claude/
├── backups/
├── debug/
├── plans/
├── plugins/
│   └── blocklist.json
├── projects/
│   └── -home-user-test/
├── session-env/
├── skills/
├── shell-snapshots/
├── todos/
├── settings.json
└── stop-hook-git-check.sh
```

---

## 8. Mobile Development Capabilities

### Native Mobile SDKs

**None installed.** The environment does NOT include:

- Android SDK or ADB (Android Debug Bridge)
- Android Emulator
- Xcode or Swift compiler
- iOS development tools

### Cross-Platform / Web-Based Mobile Development

The following runtimes support cross-platform mobile frameworks:

| Framework | Runtime Required | Available |
|---|---|---|
| React Native | Node.js | Yes (v22.22.0) |
| NativeScript | Node.js | Yes (v22.22.0) |
| Ionic | Node.js | Yes (v22.22.0) |
| Capacitor | Node.js | Yes (v22.22.0) |
| Flutter (backend) | Go / Rust | Yes |
| Mobile backend APIs | Python / Go / Rust | Yes |

---

## 9. Key Absolute Paths Reference

| Resource | Path |
|---|---|
| Working directory | `/home/user/test` |
| Container info | `/home/user/test/container-info.txt` |
| Git config | `/home/user/test/.git/config` |
| User home | `/root` |
| Git user config | `/root/.gitconfig` |
| Claude config | `/root/.claude/settings.json` |
| Node.js binary | `/opt/node22/bin/node` |
| Python binary | `/usr/local/bin/python3` |
| Ruby binary | `/usr/local/bin/ruby` |
| Go binary | `/usr/local/go/bin/go` |
| Rust compiler | `/root/.cargo/bin/rustc` |
| Maven | `/opt/maven/bin/mvn` |
| Gradle | `/opt/gradle/bin/gradle` |
| Bun | `/root/.bun/bin/bun` |
