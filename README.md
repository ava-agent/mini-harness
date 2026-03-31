# land — Landing Knowledge Assistant

> 从 902 行到 2100+ 行，13 个模块覆盖 Agent Harness 核心子系统。边做边学。

```bash
cd /path/to/new-repo && land
```

---

## Quick Start

```bash
git clone https://github.com/ava-agent/mini-harness.git
cd mini-harness
pip install -e .

export GLM_API_KEY=your-api-key

cd /path/to/your/repo
land                              # 交互模式
land -p "分析这个项目的架构"        # One-shot 模式
land --session 2026-03-31-143022  # 恢复会话
```

| 命令 | 说明 |
|------|------|
| `/memory` | 查看已记忆的事实 |
| `/output` | 查看输出目录 |
| `/session` | 当前会话信息 |
| `/sessions` | 列出所有会话 |
| `/help` | 帮助 |
| `/quit` | 保存并退出 |

---

## Part 1: 什么是 Agent Harness

### 一个类比

```
LLM = CPU        (提供原始智能，但单独不能做任何事)
Harness = OS     (提供文件系统、进程管理、安全层、I/O)
Agent = App      (在 OS 上运行的应用程序)
```

**没有 Harness 的 LLM** 就像没有操作系统的 CPU——能计算，但不能持续工作、不能记忆、不能安全地与外部交互。

### Harness 的组成

![Architecture — 六模块围绕 Agent Loop](docs/images/01-architecture.png)

一个完整的 Agent Harness 包含 6 个子系统：

| 子系统 | land 里的文件 | 解决什么问题 |
|--------|-------------|-------------|
| **Agent Loop** | `agent.py` | Agent 怎么持续地思考和行动 |
| **Tool Integration** | `tools.py` | Agent 怎么使用外部工具 |
| **Context Engineering** | `prompt.py` | Agent 怎么理解自己的角色和边界 |
| **Memory** | `memory.py` | Agent 怎么记住之前的发现 |
| **Safety** | `safety.py` | Agent 怎么避免做危险的事 |
| **LLM Client** | `llm.py` | Agent 怎么和大模型通信 |

**land 用 902 行代码实现了所有 6 个。** 每个文件就是一个子系统，阅读顺序 = 学习顺序。

---

## Part 2: 从零理解 — 你输入 `land` 后发生了什么

### Step 1: 启动

```bash
$ land /path/to/repo
land v0.1 — Landing Knowledge Assistant
Project: /path/to/repo
Session: 2026-03-31-150000
>
```

启动时做了什么：
1. 初始化 `LLMClient`（连接 GLM API）
2. 加载 `ToolRegistry`（注册 6 个内置工具）
3. 创建 `MemoryStore`（新 session 或恢复旧 session）
4. 创建 `SafetyGuard`（加载黑名单规则）
5. 组装 `Agent`（把上面 4 个组件连起来）

### Step 2: 你输入一个问题

```
> 帮我了解这个项目的整体结构
```

### Step 3: Prompt 组装 (prompt.py)

![Context Engineering — 从 Prompt Engineering 到 Context Engineering](docs/images/10-context-vs-prompt.png)

**这是 Harness 最关键的理念转变：**

```
旧思路 (Prompt Engineering):
  写一段固定的提示词 → 发给 LLM → 希望它表现好

新思路 (Context Engineering):
  每次调用动态组装上下文 → 注入当前记忆 → 注入当前项目 → 发给 LLM
```

![Context Engineering — 6 层动态组装](docs/images/03-context-engineering.png)

`prompt.py` 像搭积木一样组装 System Prompt：

```python
def build_system_prompt(memory_recall="", project_path=""):
    sections = [
        ROLE_SECTION,              # 1. "你是 Landing 知识助手"
        CLI_TOOLS_SECTION,         # 2. "你可以用 git, gh, glab..."
        OUTPUT_STRUCTURE_SECTION,  # 3. "INDEX.md 的模板是..."
        memory_recall,             # 4. "你已经知道: ..." (动态!)
        project_context,           # 5. "当前项目: /path/..." (动态!)
        CONSTRAINTS_SECTION,       # 6. "不要修改源码，不要..."
    ]
```

**为什么每次都重新组装？** 因为第 4 段（记忆）在变——Agent 每发现一个事实，下一轮的 System Prompt 就多一条记忆。

**对比 Claude Code**：Claude Code 的 System Prompt 更复杂，有 System Reminder（对抗 LLM 的"指令遗忘"）和 Prompt Cache（利用前缀缓存降低延迟）。但核心思想一样：**分段组装，按需注入**。

### Step 4: Agent Loop (agent.py)

![Agent Loop — Think → Act → Observe](docs/images/02-agent-loop.png)

System Prompt 组装好后，进入核心循环：

```python
for iteration in range(15):           # 最多 15 轮
    response = llm.chat(messages)      # Think: LLM 思考

    if no tool_calls:
        return response.content        # Done: 返回文本

    for tc in tool_calls:              # Act: 执行工具
        safety_check(tc)               #   安全检查
        result = tools.execute(tc)     #   执行
        messages.append(result)        #   Observe: 结果回传

    continue                           # 回到 Think
```

**这就是 Harness 的心脏。** 三个阶段不断循环：

| 阶段 | 做什么 | 对应代码 |
|------|--------|---------|
| **Think** | 把所有信息发给 LLM，让它决定下一步 | `llm.chat(messages)` |
| **Act** | LLM 返回 tool_calls，执行对应工具 | `tools.execute(name, args)` |
| **Observe** | 工具结果作为新消息回传给 LLM | `messages.append(tool_result)` |

**一个真实例子**：

```
Think #1: LLM 收到 "帮我了解项目结构"
  → LLM 决定: 先调用 list_dir

Act #1: 执行 list_dir(".", depth=2)
  → 返回: "src/\n  order/\n  inventory/\n  config/\nREADME.md\n..."

Observe #1: 结果回传给 LLM

Think #2: LLM 看到目录结构，决定读 README
  → LLM 决定: 调用 read_file("README.md")

Act #2: 执行 read_file("README.md")
  → 返回: "# Order System\nA fulfillment platform..."

Observe #2: 结果回传给 LLM

Think #3: LLM 现在有了足够信息
  → LLM 返回文本: "这是一个订单履约系统，核心模块包括..."

Done! 返回给用户。
```

**3 轮循环，Agent 就完成了"看目录 → 读关键文件 → 总结回答"的过程。** 就像一个有经验的工程师第一次看一个新项目的操作：先看骨架，再看入口，然后形成理解。

### Step 5: 工具执行 (tools.py)

![Tool Registry — @tool 装饰器到 LLM 调用的完整流程](docs/images/06-tool-registry.png)

**Agent 怎么知道有哪些工具？** 通过 JSON Schema：

```python
# 你写的 Python 函数:
@tool(description="读取文件内容，返回带行号的文本")
def read_file(path: str, limit: int = 200) -> str:
    """path: 文件的绝对或相对路径
    limit: 最多读取的行数"""

# @tool 自动生成的 JSON Schema (发给 LLM):
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "读取文件内容，返回带行号的文本",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "文件的绝对或相对路径"},
        "limit": {"type": "integer", "description": "最多读取的行数"}
      },
      "required": ["path"]
    }
  }
}
```

**LLM 看到 Schema，就知道可以调用 `read_file(path="src/main.py")`。** 这就是 OpenAI function-calling 协议的核心。

#### 6 个内置工具

| 工具 | 行数 | 用途 | Landing 场景 |
|------|------|------|-------------|
| `read_file` | 14 | 读文件（带行号、限制行数） | 读代码、读配置 |
| `list_dir` | 23 | 列目录（树状、深度控制） | 了解项目骨架 |
| `search_code` | 18 | 搜索模式（优先用 rg） | 找关键类、找调用链 |
| `run_command` | 13 | 执行 shell 命令 | git log、gh pr list |
| `write_file` | 7 | 写文件（自动创建目录） | 产出知识地图 |
| `memorize` | 5 | 记住发现 | 跨会话保持认知 |

**`run_command` 是最强大的工具**——通过它可以调用任何系统 CLI：

```bash
# Agent 可以这样调用:
run_command("git log --oneline -20")           # 看最近提交
run_command("git shortlog -sn")                # 看贡献者
run_command("gh issue list --state open")      # 看 GitHub Issue
run_command("glab mr list")                    # 看 GitLab MR
run_command("wc -l src/**/*.java")             # 统计代码量
```

**添加新工具只需 5 行**：

```python
@tool(description="获取 Git 仓库的贡献者统计")
def git_contributors(path: str = ".") -> str:
    """path: Git 仓库路径"""
    result = subprocess.run(
        ["git", "-C", path, "shortlog", "-sn", "--all"],
        capture_output=True, text=True, timeout=15)
    return result.stdout.strip() or "(no contributors)"
```

不需要改任何其他文件——`@tool` 自动注册，Agent 自动发现。

### Step 6: 安全检查 (safety.py)

![Safety Layer — 命令黑名单 + 循环检测](docs/images/07-safety-layer.png)

每次工具调用前都要过两道检查：

#### 检查 1: 命令黑名单

```python
# Agent 想执行 "rm -rf /"
safety.check_command("rm -rf /")
# → (False, "Blocked: matches dangerous pattern 'rm\s+-rf'")
# → 拒绝执行，原因回传给 LLM，LLM 会换一种方式

# 黑名单里有 13 个模式:
BLOCKED = ["rm -rf", "sudo", "mkfs", "shutdown", "reboot",
           "git push --force", "git reset --hard", "chmod 777", ...]
```

#### 检查 2: 循环检测 (Doom Loop Detection)

```python
# Agent 连续 3 次调用同样的 read_file("config.yaml")
safety.check_loop("read_file", {"path": "config.yaml"})
# 第 1 次: (True, "")  — 正常
# 第 2 次: (True, "")  — 可能是 retry
# 第 3 次: (False, "Loop detected") — 停！换一种方式

# 每次用户发新消息时重置计数器
safety.reset_loop()
```

**为什么需要循环检测？** 因为 LLM 有概率会陷入 Doom Loop——一直重复同样的操作。这是 Agent 特有的问题，传统软件没有。

**对比 Claude Code 的 5 层安全**：

```
Claude Code 安全纵深:
├── Layer 1: AST 静态分析 (代码注入检测)     ← land 没有
├── Layer 2: Allow/Deny 列表                ← land 的黑名单
├── Layer 3: Runtime Approval (用户确认)     ← land 没有
├── Layer 4: Docker 沙箱 (进程隔离)          ← land 没有
└── Layer 5: Audit Log (操作审计)            ← land 没有

land 的 2 层 (黑名单 + 循环) 是最小但最关键的子集。
扩展方向: 先加 "用户确认"，再加沙箱。
```

### Step 7: 记忆持久化 (memory.py)

当 Agent 调用 `memorize("order-service 是核心模块", "list_dir 结果")` 时：

```python
# agent.py 拦截 memorize 调用:
if name == "memorize":
    self.memory.add(fact=args["fact"], source=args["source"])

# memory.py 存入 JSON:
{
  "session_id": "2026-03-31-150000",
  "facts": [
    {
      "fact": "order-service 是核心模块",
      "source": "list_dir 结果",
      "timestamp": "2026-03-31T15:01:23"
    }
  ]
}

# 下一轮 LLM 调用时，prompt.py 会注入:
# "## 已知事实
#  - order-service 是核心模块 (source: list_dir 结果)"
```

**关键设计: Token 预算**

```python
def recall(self, token_budget=2000):
    char_budget = token_budget * 4  # ~4 chars/token 估算
    for entry in reversed(self._facts):  # 最近的优先
        if used + len(line) > char_budget:
            break  # 超预算就停!
```

**为什么不全部返回？** 因为 LLM 的上下文窗口是有限资源。100 条记忆可能占用 2000 token，挤掉了当前对话的空间。这就是**上下文经济学**——Ryan Lopopolo 说的"上下文是稀缺资源"。

**对比其他 Harness 的记忆系统**：

```
land:          JSON 列表 + token 预算 → 最简单
Claude Code:   MEMORY.md 文件 + frontmatter 类型标签 → 结构化
DeerFlow:      LLM 自动提取事实 + 置信度评分 → 最智能
Dapr Agents:   Dapr State Store (28+ 可插拔后端) → 最可扩展
```

### Step 8: 产出知识地图

![Output Structure — 渐进式披露的知识架构](docs/images/08-output-structure.png)

当你说"帮我生成知识地图"，Agent 会按模板创建：

```
output/order-system/
├── INDEX.md                ← 入口地图 (~100 行)
├── architecture.md         ← 分层架构 + 模块关系
├── modules/
│   ├── order-service.md   ← 职责、入口文件、依赖
│   ├── inventory.md
│   └── dispatch.md
├── people.md               ← @张三 — order owner
├── risks.md                ← 分布式锁竞争问题
├── glossary.md             ← "履约" = fulfillment
└── onboarding-checklist.md ← [ ] 跑通本地环境
```

**INDEX.md 的核心原则** (来自 Ryan Lopopolo, OpenAI):

> "给人地图，不是说明书。~100 行入口 + 指针 + 渐进发现。"

```markdown
# Order System — 知识地图
> 生成时间: 2026-03-31 | 来源: git repo

## 一句话
订单履约系统，从下单到配送完成。日均 500 万单。

## 核心模块 (详见 modules/)
- [order-service](modules/order-service.md) — 订单生命周期 ★最复杂
- [inventory](modules/inventory.md) — 库存扣减与回补

## 关键人 (详见 people.md)
- @张三 — order-service owner

## 需要注意 (详见 risks.md)
- ⚠️ 分布式锁竞争问题
```

**每条都是指针，不内联详情。** 这和 AGENTS.md / CLAUDE.md 的设计原则完全一致——map, not manual.

---

## Part 2.5: 进阶模块 — 从 Claude Code 学到的 4 个子系统

v0.1 有 6 个模块 (902 行)。参考 Claude Code，v0.2 新增了 4 个模块 (+567 行)，覆盖了 Harness 的"第二层能力"。

### Module 7: compact.py — 上下文压缩 (119 行)

![Context Compact — 渐进式压缩策略](docs/images/11-context-compact.png)

**问题**：对话越长，token 消耗越多。LLM 上下文窗口是有限资源。如果不压缩，Agent 在长任务中会"撑爆"窗口，丢失关键上下文。

**Claude Code 的做法**：当 token 用量接近上限时，自动触发 Compact——先截断旧工具输出，再摘要旧对话，最后卸载到记忆文件。

**land 的实现**：

```python
class ContextCompactor:
    def compact_if_needed(self, messages):
        usage = self.estimate_tokens(messages) / self.budget

        if usage < 0.70:  return messages          # 正常
        if usage >= 0.70: self._truncate_outputs()  # 截断工具输出
        if usage >= 0.85: self._summarize_old()     # 摘要旧对话
```

**三阶段压缩**：

| 阶段 | 触发条件 | 做什么 | 效果 |
|------|---------|--------|------|
| Stage 1 | > 70% 窗口 | 截断超过 50 行的工具输出 | 减少 ~30% |
| Stage 2 | > 85% 窗口 | 旧对话替换为 1-2 行摘要，保留最近 10 条 | 减少 ~60% |
| Stage 3 | (future) | 卸载事实到 memory.json | 减少 ~80% |

**学习要点**：Claude Code 还有 Prompt Cache——静态部分（System Prompt、Tool Schema）被 LLM 缓存为前缀，只有动态部分（对话历史）需要每次重传。这使得压缩的紧迫性降低 ~40%。

---

### Module 8: hooks.py — 生命周期钩子 (129 行)

![Hooks System — Agent 生命周期的 5 个拦截点](docs/images/12-hooks-system.png)

**问题**：Agent 有真实工具（读文件、写文件、执行命令）——一个错误可能删除文件或推送坏代码。仅靠 System Prompt 约束不够——LLM 在长对话中可能"遗忘"规则。需要在**代码层面**拦截。

**Claude Code 的做法**：在 Agent 执行的关键节点注册 Hook，任何操作都要过 Hook 链。这是第 5 层安全防线。

**land 的实现**：

```python
hooks = HookRegistry()

# 用装饰器注册 Hook
@hooks.pre_tool_use
def block_env_writes(tool_name, args):
    """阻止写入 .env 文件"""
    if tool_name == "write_file" and ".env" in args.get("path", ""):
        return {"allowed": False, "reason": "Cannot write to .env files"}
    return {"allowed": True}

@hooks.post_tool_use
def audit_log(tool_name, args, result):
    """记录每一次工具调用"""
    logger.info(f"{tool_name}({args}) → {result[:80]}")
```

**5 个 Hook 事件**：

| Hook | 时机 | 能做什么 |
|------|------|---------|
| `pre_tool_use` | 工具执行**前** | 拦截、修改参数、审计 |
| `post_tool_use` | 工具执行**后** | 检查结果、记录日志 |
| `session_start` | 会话开始 | 初始化、加载配置 |
| `session_end` | 会话结束 | 保存状态、清理 |
| `on_error` | 发生错误 | 错误处理、告警 |

**学习要点**：Hooks 和传统软件的 Middleware/Interceptor 是同一个模式——你在 Dapr 中见过的 Middleware Pipeline，在 Harness 里以 Hook 形态出现。DeerFlow 的 14 阶段中间件本质上就是一系列 Hook。

---

### Module 9: permissions.py — 权限系统 (140 行)

![Permission System — Allow / Ask / Deny 三级授权](docs/images/13-permission-system.png)

**问题**：不能全拦（Agent 没法工作），不能全放（Agent 可能搞坏东西）。需要**分级授权**。

**Claude Code 的做法**：三级权限 + 模式匹配。同一个工具在不同上下文可以有不同权限。

**land 的实现**：

```python
checker = PermissionChecker(mode="semi-auto")

# 读操作 → 自动放行
checker.check("read_file", {"path": "a.py"})      # → ALLOW

# 危险操作 → 永远拒绝
checker.check("run_command", {"command": "rm -rf /"})  # → DENY

# 写操作 → 询问用户
checker.check("write_file", {"path": "out.md"})    # → ASK
#   ⚠ Approve?  write_file(path=out.md)
#   [y/N]: _
```

**三种权限 + 三种模式**：

```
权限:
  ALLOW — 自动放行 (read_file, list_dir, search_code, git log...)
  ASK   — 需要用户确认 (write_file, git push, git commit...)
  DENY  — 永远拒绝 (rm -rf, sudo, force push...)

模式:
  auto      — 全部放行 (速度最快，最不安全)
  semi-auto — 用规则判断 (默认模式，平衡)
  manual    — 全部询问 (最安全，最慢)
```

**判断顺序**：DENY > ALLOW > ASK > 默认。这意味着 DENY 规则始终优先——即使有 ALLOW 规则匹配，DENY 也能覆盖它。

**学习要点**：Claude Code 的权限是**模式匹配**的，不是简单的工具名级别。`Bash(npm test)` 可以 ALLOW，但 `Bash(rm -rf)` 要 DENY——同是 Bash 工具，不同参数不同权限。land 的实现用 `tool_name:glob_pattern` 达到同样效果。

---

### Module 10: config.py — 项目配置 (108 行)

![Config System — LAND.md + settings.json 双层配置](docs/images/14-config-system.png)

**问题**：不同项目有不同规则。"不要修改 config/ 目录"、"测试覆盖率必须 > 80%"、"@张三负责 order-service"——这些项目特定的信息应该持久化，不是每次口头告诉 Agent。

**Claude Code 的做法**：`CLAUDE.md`（人类写、Markdown、自由格式）+ `settings.json`（机器读、JSON、结构化）。

**land 的实现**：

```bash
# 在项目根目录创建 LAND.md
land --init

# LAND.md 内容会自动注入到 System Prompt
cat LAND.md
```

```markdown
# Project Rules for land

## Coding Standards
- 语言: Java 17 + Spring Boot 3.2
- 测试: JUnit 5, 覆盖率 > 80%

## Architecture
- 微服务架构，order/inventory/dispatch 三个核心服务
- 消息中间件: Kafka

## Rules
- 不要修改 config/ 目录下的文件
- 不要直接查看 .env 文件

## Team Context
- @张三 负责 order-service
- @李四 负责基础设施和部署
```

**双层设计**：

| 层 | 文件 | 给谁看 | 内容 |
|----|------|--------|------|
| **Human** | `LAND.md` | 人 + Agent | 项目规则、架构、团队（Markdown） |
| **Machine** | `.land/settings.json` | Harness | max_iterations、permission_mode（JSON） |

**学习要点**：LAND.md = 你在 Claude Code 里见到的 CLAUDE.md。核心思想是"仓库即真相"（Ryan Lopopolo）——如果规则不在仓库里，对 Agent 就不存在。Slack 里的讨论、脑子里的知识，Agent 都看不到。

---

### Agent Loop v0.2: 5 层安全防线

新的 `agent.py` 现在集成了全部安全层：

```python
for tc in tool_calls:
    # Layer 2: 命令黑名单 (safety.py)
    if is_blocked(tc): continue

    # Layer 3: 权限检查 (permissions.py) — Allow/Ask/Deny
    if is_denied(tc): continue
    if needs_ask(tc) and user_says_no(): continue

    # Layer 4: 循环检测 (safety.py)
    if is_loop(tc): continue

    # Layer 5: 生命周期钩子 (hooks.py) — PreToolUse
    if hook_blocks(tc): continue

    # ✅ 全部通过 → 执行
    result = tools.execute(tc)

    # PostToolUse hook — 审计
    hooks.fire_post_tool_use(tc, result)
```

对比 Claude Code 的 5 层：

```
           Claude Code              land v0.2
Layer 1:   System Prompt 约束       ✅ prompt.py
Layer 2:   命令黑名单               ✅ safety.py
Layer 3:   Allow/Ask/Deny 权限      ✅ permissions.py (NEW)
Layer 4:   循环检测                  ✅ safety.py
Layer 5:   Hooks 拦截               ✅ hooks.py (NEW)
Bonus:     Docker/Worktree 沙箱     ❌ (P2 扩展)
```

---

## Part 2.7: 高阶能力 — SubAgent、Skill、Trace

v0.1 是骨架 (6 模块)，v0.2 是护栏 (4 模块)，v0.3 是**高阶能力**——这是 Claude Code 真正强大的地方。

### Module 11: subagent.py — 子 Agent (154 行)

![SubAgent — 主 Agent 委派子任务给 SubAgent](docs/images/15-subagent.png)

**问题**：大任务不应该在一个长对话里完成——上下文会爆、风险会累积。"分析这个项目"应该拆成几个独立子任务。

**Claude Code 的做法**：`Agent` 工具可以启动一个新的 Agent，拥有独立上下文窗口，完成后把结果返回给父 Agent。SubAgent 可以再启动 SubAgent（递归嵌套）。

**land 的实现**：

```python
manager = SubAgentManager(llm, tools, safety)

# 委派子任务
results = manager.spawn_many([
    {"name": "structure", "task": "分析目录结构和技术栈"},
    {"name": "git",       "task": "分析 git 历史和贡献者"},
    {"name": "docs",      "task": "读取所有文档文件并摘要"},
], context=f"项目路径: {project_path}")

# 每个 SubAgent 有自己的:
# - 独立上下文 (不污染父 Agent)
# - 聚焦的 System Prompt (只做一件事)
# - 独立的迭代次数上限 (默认 8 轮)
```

**SubAgent 的 3 个关键设计**:

| 特性 | 为什么 |
|------|--------|
| **独立上下文** | SubAgent 读的文件、工具输出不进入父 Agent 的历史，避免污染 |
| **聚焦 Prompt** | "你只需完成一个任务" — 比父 Agent 的通用 Prompt 更高效 |
| **结果摘要** | SubAgent 返回文本结果（不是原始工具输出），父 Agent 只看摘要 |

**对比 Claude Code**：Claude Code 的 SubAgent 还支持并行执行（多线程）、Git Worktree 隔离（每个 SubAgent 在独立代码副本上工作）。land 当前是顺序执行，但架构上预留了并行扩展。

---

### Module 12: skills.py — Skill 系统 /命令 (148 行)

![Skill System — /命令触发预定义工作流](docs/images/16-skill-system.png)

**问题**：每次都手动描述"帮我分析项目结构、看 git 历史、读 README..."太繁琐。常用工作流应该一键触发。

**Claude Code 的做法**：`/commit`、`/review-pr` 等 Skill——不是简单的快捷命令，而是注入到 Agent 上下文的**结构化 Prompt 模板**，引导 Agent 按步骤完成。

**land 的 5 个内置 Skill**：

```bash
> /analyze              # 全面分析: 结构→技术栈→入口→git→核心模块
> /map                  # 生成知识地图到 output/ (INDEX.md + 模块文档)
> /explore src/order    # 深度探索 order 模块
> /people               # 识别贡献者和 owner
> /risks                # 识别技术债和风险
```

**Skill 的核心设计——它是 Prompt，不是代码**：

```python
Skill(
    name="analyze",
    prompt_template="""
    请对项目 {project} 进行全面分析，按以下步骤：
    1. list_dir 查看骨架
    2. 读取 package.json/pom.xml 识别技术栈
    3. 读取 README.md
    4. git log --oneline -20
    5. git shortlog -sn --all
    6. 识别核心模块并 memorize
    ...
    """,
)
```

**为什么是 Prompt 而不是硬编码步骤？** 因为 LLM 可以根据实际情况灵活调整——如果项目没有 package.json，它会跳过；如果发现了意外的结构，它会探索。Skill 给的是**导航路线**，不是死板脚本。

**学习要点**：Claude Code 的 Skill 系统更复杂——支持 Skill 文件（Markdown 文件作为 Skill）、参数化（`/review-pr 123`）、渐进加载（不预加载所有 Skill）。land 的实现是最简形态，但核心思想一致。

---

### Module 13: trace.py — 执行追踪 (168 行)

![Trace — Agent 执行的完整可观测性](docs/images/17-trace.png)

**问题**：Agent 做了什么？为什么做了这个决定？花了多少 token？哪个工具调用最慢？——没有可观测性，你无法调试和优化 Agent。

**Claude Code 的做法**：记录所有操作到事件日志。DeerFlow 用 OpenTelemetry 做分布式追踪。

**land 的 `/trace` 命令**：

```bash
> /trace

Session: 20260331-150000
Events: 23
LLM calls: 5
Tool calls: 14
Blocked: 2
Est. tokens: 15,200
Tool time: 1,847ms

  15:00:01 💬 User: 帮我分析这个项目
  15:00:02 🧠 LLM (glm-4-flash) msgs=3 tokens≈2400
  15:00:03 ⚙️ list_dir → 1200 chars (23ms)
  15:00:04 ⚙️ read_file → 3400 chars (12ms)
  15:00:05 🧠 LLM (glm-4-flash) msgs=7 tokens≈4800
  15:00:06 ⚙️ run_command → 800 chars (156ms)
  15:00:07 🚫 BLOCKED run_command: sudo apt install...
  15:00:08 🧠 LLM (glm-4-flash) msgs=10 tokens≈6200
  15:00:10 💡 Agent: 这个项目是一个订单履约系统...
```

**追踪记录的 7 种事件**：

| 事件 | 图标 | 记录什么 |
|------|------|---------|
| `user_input` | 💬 | 用户输入（截断到 200 字符） |
| `llm_call` | 🧠 | 模型名、消息数、估算 token |
| `tool_call` | ⚙️ | 工具名、参数、结果长度、耗时 |
| `tool_blocked` | 🚫 | 被拦截的工具和原因 |
| `agent_response` | 💡 | Agent 最终响应 |
| `compact` | 📦 | 压缩前后的消息数 |
| `error` | ❌ | 错误信息 |

**Trace 自动保存到 `.land/traces/{session}.json`**，可以事后分析。

**学习要点**：可观测性是 Harness 的"第七感"——没有它你在盲飞。Claude Code 的日志让你能回答"为什么 Agent 选择了这个工具而不是那个"。DeerFlow 用 OpenTelemetry 做跨 SubAgent 的分布式追踪。land 的 JSON 事件日志是最简实现。

---

### v0.3 全景: 13 个模块

```
v0.1 骨架层 (6 模块, 672 行):       v0.2 护栏层 (4 模块, 496 行):
├── llm.py        — LLM 客户端      ├── compact.py     — 上下文压缩
├── tools.py      — 6 个工具         ├── hooks.py       — 生命周期钩子
├── safety.py     — 命令黑名单       ├── permissions.py — Allow/Ask/Deny
├── memory.py     — 记忆系统         └── config.py      — LAND.md 配置
├── prompt.py     — 上下文组装
└── agent.py      — Agent Loop       v0.3 能力层 (3 模块, 470 行):
                                     ├── subagent.py    — 子 Agent
cli.py            — 终端交互          ├── skills.py      — /命令工作流
                                     └── trace.py       — 执行追踪
```

---

## Part 3: 和 Claude Code / DeerFlow 对比学习

![Learning Path — 从 land 到 DeerFlow 到 Claude Code](docs/images/09-learning-path.png)

### 全景对比

```
                        land v0.3       Claude Code         DeerFlow 2.0
                        ─────────       ───────────         ────────────
代码量                   2100+ 行        ~50K+ 行            ~30K+ 行
模块数                   13              ~30+                ~20+
─────────────────────────────────────────────────────────────────────────
Agent Loop              ✅ 可配置轮数    ✅ 复杂嵌套          ✅ LangGraph 状态机
工具系统                 6 个            ~20 个              ~15 个 (5 来源)
上下文工程               ✅ 7 段组装      ✅ System Reminder   ✅ 14 阶段中间件
记忆                    ✅ JSON 文件     ✅ MEMORY.md         ✅ 置信度事实系统
安全                    ✅ 5 层          ✅ 5 层纵深          ✅ Guardrail 中间件
上下文压缩              ✅ 2 阶段        ✅ Compact           ✅ Summarization
Hooks                   ✅ 5 事件        ✅ 生命周期          ✅ 中间件管道
权限系统                ✅ A/A/D         ✅ Allow/Ask/Deny    ✅ Guardrail
项目配置                ✅ LAND.md       ✅ CLAUDE.md         ✅ 配置文件
SubAgent                ✅ 顺序 ★v0.3   ✅ 并行 + Worktree   ✅ 双线程池
Skill 系统              ✅ 5 个 ★v0.3   ✅ /commit 等        ✅ 渐进加载
执行追踪                ✅ JSON ★v0.3   ✅ 事件日志          ✅ OpenTelemetry
─────────────────────────────────────────────────────────────────────────
沙箱                    ❌              ✅ 进程隔离           ✅ Docker
MCP                     ❌              ✅ 原生              ✅ OAuth
Streaming               ❌              ✅                   ✅

land 覆盖了 Claude Code 80% 的架构概念，
剩余 20% (沙箱/MCP/Streaming) 是部署级关注点。
```

### 每个模块的进化方向

#### Agent Loop 进化

```
land (你现在在这里):
  简单 for 循环，最多 15 轮
  ↓
DeerFlow:
  LangGraph 状态机，支持分支和并行
  + 14 阶段中间件管道 (每个中间件处理一个 Agent 特有问题)
  ↓
Claude Code:
  嵌套 Agent Loop (SubAgent 可再产生 SubAgent)
  + 上下文自动压缩 (Compact)
  + Hooks (PreToolUse / PostToolUse 生命周期事件)
```

#### 工具系统进化

```
land:
  @tool 装饰器 + 6 个内置工具
  ↓
DeerFlow:
  5 来源动态组装 (内置 + Skill + MCP + SubAgent + 用户自定义)
  + Skill 渐进加载 (不一次性加载所有工具，按需发现)
  ↓
Claude Code:
  ~20 个内置工具 + MCP 延迟加载 (ToolSearch 按需发现)
  + Agent 工具 (一个工具可以启动一个新 Agent)
  + 权限控制 (Ask/Allow/Deny per tool)
```

#### 记忆系统进化

```
land:
  JSON 文件 + token 预算
  ↓
DeerFlow:
  LLM 自动提取事实 + 置信度评分 + 语义检索
  ↓
Claude Code:
  MEMORY.md 文件系统 + 类型标签 (user/feedback/project/reference)
  + 自动检测过时记忆
  + 引用前验证 (记忆说文件存在 → grep 确认)
```

#### 安全系统进化

```
land:
  命令黑名单 + 循环检测 (62 行)
  ↓
DeerFlow:
  + Guardrail 中间件 (基于 LLM 的内容审查)
  + DanglingToolCall 处理 (LLM 输出格式错误)
  ↓
Claude Code:
  5 层纵深防御:
  ├── AST 静态分析 (检测代码注入)
  ├── Allow/Deny 列表 (工具级权限)
  ├── Runtime Approval (用户交互确认)
  ├── Docker/Worktree 沙箱 (进程隔离)
  └── Audit Log (操作审计)
```

---

## Part 4: 动手扩展

### 扩展优先级

```
P0 (马上有用):
├── .env 文件支持 — 不用每次 export
├── Streaming 输出 — 不用等 LLM 全部生成完
└── 上下文压缩 — history 太长时自动 summarize

P1 (提升体验):
├── 交互式确认 — 高危操作前问用户 "确认执行?"
├── 更好的循环检测 — sliding window 而非精确匹配
└── 彩色 Markdown 渲染 — 终端里渲染 Agent 的 MD 输出

P2 (接近 Claude Code):
├── SubAgent — 大任务分解成子任务
├── MCP 支持 — 接入 MCP Server 获取更多工具
├── Plugin/Skill — 可扩展的能力
└── 向量记忆 — 语义检索而非全量召回
```

### 示例: 添加 .env 支持 (P0)

```python
# 在 cli.py 的 main() 开头加:
from pathlib import Path

env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())
```

### 示例: 添加用户确认 (P1)

```python
# 在 agent.py 的 safety check 后加:
CONFIRM_PATTERNS = [re.compile(r"\bgit\s+push\b"), re.compile(r"\bwrite_file\b")]

for pattern in CONFIRM_PATTERNS:
    if pattern.search(str(args)):
        answer = input(f"  ⚠️  Confirm {name}({args})? [y/N] ")
        if answer.lower() != "y":
            result = "[CANCELLED] User denied"
            break
```

---

## Part 5: 源码导读 — 推荐阅读顺序

```
第一轮: 基础 6 模块 (v0.1 骨架)
─────────────────────────────────────────────────────
阅读顺序     文件             行数    你会学到什么
─────────   ──────────────  ────    ──────────────────────────
1 (最简单)   llm.py           41    OpenAI 兼容协议、模型抽象
2 (核心模式) tools.py         217    @tool 装饰器、JSON Schema、6 个工具
3 (安全基础) safety.py         62    命令黑名单、循环检测
4 (持久化)   memory.py         95    JSON 存储、Token 预算
5 (上下文)   prompt.py        145    分段组装、动态注入
6 (心脏)     agent.py         215    Agent Loop、5 层安全集成
7 (入口)     cli.py           187    REPL、特殊命令

第二轮: 进阶 4 模块 (v0.2 护栏层)
─────────────────────────────────────────────────────
8 (压缩)     compact.py       119    上下文窗口管理、渐进压缩
9 (钩子)     hooks.py         129    生命周期事件、拦截器模式
10 (权限)    permissions.py   140    Allow/Ask/Deny、模式匹配
11 (配置)    config.py        108    LAND.md、双层配置

第三轮: 高阶 3 模块 (v0.3 能力层)
─────────────────────────────────────────────────────
12 (子Agent) subagent.py      154    SubAgent、独立上下文、任务分解
13 (技能)    skills.py        148    /命令、Prompt 模板、预定义工作流
14 (追踪)    trace.py         168    事件日志、可观测性、性能分析

合计: ~2100 行, 13 个模块

三层架构的代码分布:
  v0.1 骨架 (672行, 47%) — Agent 运转的最小集
  v0.2 护栏 (496行, 34%) — 安全+配置，大量代码是"约束"
  v0.3 能力 (470行, 19%) — SubAgent+Skill+Trace，高阶能力

启示: Harness 的代码有 1/3 是护栏 — 不是让 Agent 做更多，而是让 Agent 更安全
```

**阅读每个文件时，问自己三个问题**：
1. 这个模块解决了什么 Agent 特有的问题？
2. Claude Code / DeerFlow 在同一个问题上做了什么更复杂的设计？
3. 如果我要扩展这个模块，下一步加什么？

---

## Part 6: 学习资料

### 核心概念

| 资源 | 读完你会理解 |
|------|-------------|
| [Harness Engineering (Ryan Lopopolo, OpenAI)](https://openai.com/index/harness-engineering/) | 为什么 land 的产出是"地图不是说明书" |
| [Building Effective Agents (Anthropic)](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/building-effective-agents) | 为什么 agent.py 是 Think→Act→Observe 循环 |
| [Context Engineering (Torantulino)](https://www.latent.space/p/context-engineering) | 为什么 prompt.py 每次动态组装而非写死 |
| [Harness Engineering (Martin Fowler)](https://martinfowler.com/articles/building-agents-with-harness.html) | 工程视角的 Harness 六大子系统 |

### 参考实现

| 项目 | 读完你会理解 |
|------|-------------|
| [Claude Code 官方文档](https://docs.anthropic.com/en/docs/claude-code) | land 的每个模块在完整 Harness 里长什么样 |
| [DeerFlow GitHub](https://github.com/bytedance/deer-flow) | 14 阶段中间件怎么解决 Agent 特有问题 |
| [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling) | tools.py 的 JSON Schema 格式为什么这么写 |

### 协议标准

| 协议 | 和 land 的关系 |
|------|---------------|
| [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) | land 未来接入更多工具的标准方式 |
| [A2A (Agent-to-Agent)](https://github.com/google/A2A) | land 未来和其他 Agent 协作的标准方式 |

---

## License

MIT
