# land — Landing Knowledge Assistant

最小但完整的 Agent Harness (902 行 Python)，帮助新人快速理解接手的系统。

```bash
cd /path/to/new-repo && land
```

---

## Quick Start

```bash
git clone https://github.com/ava-agent/mini-harness.git
cd mini-harness
pip install -e .

export GLM_API_KEY=your-api-key    # Required
# export GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4  # Default
# export GLM_MODEL=glm-4-flash    # Default

# 交互模式
cd /path/to/your/repo
land

# One-shot 模式
land -p "分析这个项目的架构，生成知识地图"

# 恢复会话
land --session 2026-03-31-143022
```

### Commands

| 命令 | 说明 |
|------|------|
| `/memory` | 查看已记忆的事实 |
| `/output` | 查看输出目录 |
| `/session` | 当前会话信息 |
| `/sessions` | 列出所有会话 |
| `/help` | 帮助 |
| `/quit` | 保存并退出 |

---

## Design: 为什么这么设计

### 设计哲学

**land 遵循三个核心原则**：

1. **Harness Engineering** (Ryan Lopopolo, OpenAI)
   - "给 AI 一张地图，而不是一本说明书"
   - 产出的知识地图用 ~100 行 INDEX.md 作为入口，指向更深的文档
   - Agent 本身的 System Prompt 也是分段组装的地图，不是一段大文本

2. **Context Engineering** (Anthropic, LangChain)
   - 不是"提示词工程"——不是优化一句话的措辞
   - 而是"上下文工程"——设计 Agent 的整个信息架构
   - System Prompt 每次 LLM 调用时动态组装：角色 + 工具 + 记忆 + 约束

3. **最小但完整**
   - 6 个模块，每个对应 Harness 的一个核心子系统
   - 唯一外部依赖：`openai` SDK
   - 没有框架（不用 LangChain/CrewAI），每一行代码都有意义

### 和 Claude Code / DeerFlow 的对比

```
                        land        Claude Code     DeerFlow 2.0
                        ────        ───────────     ────────────
代码量                   902 行      ~50K+ 行        ~30K+ 行
Agent Loop              ✅ 15 轮     ✅ 复杂嵌套      ✅ LangGraph 状态机
工具系统                 6 个         ~20 个          ~15 个 (5 来源)
上下文工程               ✅ 分段组装  ✅ System Reminder ✅ 14 阶段中间件
记忆                    ✅ JSON 文件  ✅ MEMORY.md     ✅ 置信度事实系统
安全                    ✅ 黑名单+循环 ✅ 5 层纵深     ✅ Guardrail 中间件
沙箱                    ❌           ✅ 进程隔离      ✅ Docker
Sub-Agent               ❌           ✅              ✅ 双线程池
MCP                     ❌           ✅ 原生          ✅ OAuth
Skill/Plugin            ❌           ✅              ✅ 渐进加载

land 是学习 Harness 的起点：
  看到了骨架 → 才知道 Claude Code 的肌肉长在哪里
```

---

## Architecture: 六个模块

```
┌──────────────────────────────────────────────────────┐
│                    cli.py / main.py                   │
│                   终端交互 + REPL                     │
└──────────────────────┬───────────────────────────────┘
                       │ 用户输入
                       ▼
┌──────────────────────────────────────────────────────┐
│                     agent.py                          │
│              Agent Loop (核心循环)                     │
│                                                      │
│   ┌─────────┐    ┌──────────┐    ┌───────────┐      │
│   │ 1. Think │───→│ 2. Act   │───→│ 3. Observe│──┐   │
│   │ 调用 LLM │    │ 执行工具  │    │ 收集结果   │  │   │
│   └─────────┘    └──────────┘    └───────────┘  │   │
│        ▲                                        │   │
│        └────────────────────────────────────────┘   │
│                    (循环直到完成)                      │
└──┬──────────┬──────────┬──────────┬─────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌─────────┐
│llm.py│ │tools.py│ │memory  │ │safety.py│
│      │ │        │ │  .py   │ │         │
│ GLM  │ │ 6 工具  │ │ JSON   │ │ 黑名单   │
│ API  │ │ @tool  │ │ 持久化  │ │ 循环检测  │
└──────┘ └────────┘ └────────┘ └─────────┘
              │
              ▼
         ┌─────────┐
         │prompt.py│
         │         │
         │ 动态组装  │
         │ System   │
         │ Prompt   │
         └─────────┘
```

### 数据流（一次完整的交互）

```
1. 用户输入: "帮我分析这个项目的架构"

2. prompt.py 组装 System Prompt:
   ┌─ 角色: "你是 Landing 知识助手..."
   ├─ 工具说明: "你可以调用 git, gh, glab..."
   ├─ 输出模板: "INDEX.md 是地图不是说明书..."
   ├─ 记忆回忆: "- order-service 是核心模块 (source: git log)"
   └─ 约束: "以读为主，不修改源码..."

3. agent.py 发送给 LLM:
   messages = [system_prompt, ...history, user_message]

4. LLM 返回 tool_calls:
   [{"name": "list_dir", "arguments": {"path": ".", "depth": 2}}]

5. safety.py 检查:
   ✅ list_dir 不在黑名单
   ✅ 不是重复调用

6. tools.py 执行:
   list_dir(".", depth=2) → "src/\n  order/\n  inventory/\n..."

7. 结果回传 LLM，LLM 继续思考...
   (可能再调用 read_file, search_code, run_command 等)

8. LLM 最终返回文本响应:
   "这个项目是一个订单履约系统，核心模块包括..."

9. memory.py 如果 Agent 调了 memorize:
   保存: {"fact": "order-service 是核心", "source": "list_dir"}
```

---

## Module Deep Dive: 逐模块解析

### 1. llm.py — LLM 客户端 (41 行)

**它是 Harness 最薄的一层。** 只做一件事：把 messages + tools 发给模型，拿回响应。

```python
class LLMClient:
    def chat(self, messages, tools=None):
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, tools=tools, tool_choice="auto"
        )
        return response.choices[0].message
```

**设计决策**：
- 用 `openai` SDK + 自定义 `base_url`，所有 OpenAI 兼容模型（GLM、DeepSeek、通义千问）零改动切换
- 不做 streaming（最小版本不需要）
- 不做重试（交给上层 Agent Loop 处理）

**学习要点**：Harness 的价值不在 LLM 调用，而在**围绕 LLM 的基础设施**。这个文件最小，是对的。

---

### 2. tools.py — 工具注册表 (217 行)

**两个核心机制**：

#### `@tool` 装饰器 + 自动 Schema 生成

```python
@tool(description="读取文件内容，返回带行号的文本")
def read_file(path: str, limit: int = 200) -> str:
    """path: 文件的绝对或相对路径
    limit: 最多读取的行数，默认 200"""
```

一个装饰器做了三件事：
1. 从 Python 类型注解自动生成 OpenAI function-calling JSON Schema
2. 从 docstring 提取每个参数的描述
3. 注册到全局 `registry`

这意味着**添加新工具只需写一个函数**，零配置。

#### ToolRegistry

```python
class ToolRegistry:
    def get_schemas(self) -> list[dict]   # 给 LLM 看的 JSON Schema
    def execute(name, args) -> str         # 执行并返回字符串结果
```

**设计决策**：
- 工具返回值统一为 `str`——LLM 只能读文本，不需要结构化返回
- `run_command` 是最关键的工具：通过它调用 git/gh/glab/feishu-cli，避免为每个 CLI 写专用工具
- `memorize` 是一个"虚拟工具"：tools.py 里的实现是 placeholder，真正的持久化在 agent.py 里拦截处理

**学习要点**：对比 Claude Code 的 ~20 个工具（Read, Edit, Glob, Grep, Bash...），land 用 6 个覆盖了核心场景。`run_command` 承担了 Claude Code 里 Bash 工具的角色。

---

### 3. safety.py — 安全层 (62 行)

**两个防线**：

#### 命令黑名单

```python
BLOCKED_PATTERNS = [
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bgit\s+push\s+--force\b"),
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    # ...13 个模式
]
```

Agent 调用 `run_command` 时，先过黑名单。匹配到就拒绝，原因回传给 LLM。

#### 循环检测 (Doom Loop Detection)

```python
def check_loop(self, tool_name, args):
    key = f"{tool_name}|{json.dumps(args, sort_keys=True)}"
    self._call_counter[key] += 1
    if count >= 3:  # 同样的调用超过 3 次
        return False, "Loop detected, try a different approach"
```

**设计决策**：
- 用工具名 + 参数的精确匹配检测循环（DeerFlow 用的是更复杂的 sliding window 算法）
- 每次用户新输入时 `reset_loop()`——新问题重新计数
- 阈值 3 是经验值：1 次正常，2 次可能是 retry，3 次就是 loop

**学习要点**：Claude Code 有 5 层安全纵深（AST 分析、Allow/Deny、Runtime Approval、Docker、Audit）。land 的 2 层（黑名单 + 循环检测）是最小但最关键的子集。

**对比 DeerFlow 的 14 阶段中间件**：
```
DeerFlow 有而 land 没有的:
├── Summarization        ← 上下文超窗时自动压缩
├── DanglingToolCall     ← LLM 生成了格式错误的 tool_call
├── MaxSteps             ← 更精细的步数限制
├── ContextOverflow      ← Token 预算动态管理
└── Guardrail            ← 基于 LLM 的内容审查

这些是你后续扩展的方向。
```

---

### 4. memory.py — 记忆系统 (95 行)

**核心方法**：

```python
class MemoryStore:
    def add(fact, source)        # Agent 发现了什么 → 存入
    def recall(token_budget=2000) # 取出记忆，控制在 token 预算内
    def save() / load()          # JSON 文件持久化
```

**`recall()` 的 token 预算机制**：

```python
def recall(self, token_budget=2000):
    char_budget = token_budget * 4  # ~4 chars/token
    for entry in reversed(self._facts):  # 最近的优先
        line = f"- {entry['fact']}"
        if used + len(line) > char_budget:
            break  # 超预算就停
        lines.append(line)
```

**为什么不是全部返回？** 因为 System Prompt 有 token 上限。记忆越多，留给当前对话的空间越少。这就是"上下文经济学"——每个 token 都是稀缺资源。

**设计决策**：
- 最近优先（`reversed`）：人的直觉也是最近发现的最相关
- 估算 ~4 chars/token：粗略但够用
- 每次 `add()` 自动 `save()`：不怕崩溃丢数据

**对比其他 Harness 的记忆系统**：
```
land:          JSON 列表 + token 预算
Claude Code:   MEMORY.md (文件系统) + frontmatter 类型
DeerFlow:      LLM 提取事实 + 置信度评分 + Token 预算注入
Dapr Agents:   Dapr State Store (28+ 可插拔后端)

land 的记忆够用但原始。下一步可以加:
├── LLM 自动提取事实（不靠 Agent 主动调 memorize）
├── 置信度评分（不确定的事实权重低）
└── 向量检索（不只是全量召回）
```

---

### 5. prompt.py — System Prompt 动态组装 (135 行)

**这是 Harness 区别于"给 LLM 发消息"的关键。**

```python
def build_system_prompt(memory_recall="", project_path=""):
    sections = [
        ROLE_SECTION,              # 1. 你是谁
        CLI_TOOLS_SECTION,         # 2. 你能用什么
        OUTPUT_STRUCTURE_SECTION,  # 3. 产出规范
        memory_recall,             # 4. 你记得什么 (动态)
        project_context,           # 5. 当前项目 (动态)
        CONSTRAINTS_SECTION,       # 6. 你不能做什么
    ]
    return "\n\n".join(sections)
```

**每次 LLM 调用都重新组装**。因为记忆在变、项目上下文在变。

**6 个段的设计逻辑**：

| 段 | 内容 | 为什么需要 |
|----|------|-----------|
| Role | "你是 Landing 知识助手" | 限定角色边界 |
| CLI Tools | git/gh/glab/feishu-cli 用法 | Agent 不知道有什么 CLI 可用 |
| Output Structure | INDEX.md 模板 + 目录规范 | 不给模板 Agent 会随意输出 |
| Memory | 动态注入已知事实 | 跨轮次保持连贯 |
| Project | 工作目录路径 | Agent 需要知道在哪 |
| Constraints | "以读为主，不修改源码" | 防止 Agent 越界 |

**学习要点**：Claude Code 的 system prompt 更复杂——包含 System Reminder（对抗指令衰减）、Prompt Cache（利用前缀缓存降低延迟）、动态工具 Schema 注入。但核心思想一样：**分段组装，按需注入**。

---

### 6. agent.py — Agent Loop (171 行)

**这是 Harness 的心脏。** 整个文件实现一个循环：

```
for iteration in range(15):        # 最多 15 轮
    response = llm.chat(messages)  # Think: 让 LLM 思考

    if no tool_calls:
        return response.content    # Done: 纯文本回复

    for tc in tool_calls:          # Act: 执行工具
        safety_check(tc)           # 安全检查
        result = tools.execute(tc) # 执行
        messages.append(result)    # Observe: 结果回传

    continue                       # 循环
```

**关键细节**：

1. **`memorize` 拦截**：Agent 调用 memorize 时，agent.py 拦截并写入 MemoryStore，而不是执行 tools.py 里的 placeholder

2. **消息格式**：tool_call 结果必须以 `{"role": "tool", "tool_call_id": tc.id}` 格式回传——这是 OpenAI function-calling 协议要求的

3. **MAX_ITERATIONS = 15**：防止无限循环的硬性上限。Claude Code 的 Agent Loop 更复杂，有 SubAgent 嵌套和动态调整

4. **System Prompt 每轮重建**：`[self._system_message()] + self.history`——因为记忆可能在本轮更新了

**对比 Claude Code 的 Agent Loop**：
```
Claude Code 有而 land 没有的:
├── SubAgent (子任务分派)
├── Streaming (流式输出)
├── Parallel Tool Calls (并行执行多个工具)
├── Context Window Management (超窗时自动压缩)
├── Retry with Backoff (LLM 调用失败重试)
└── Hooks (PreToolUse / PostToolUse 钩子)

这些都是在 land 的骨架上可以逐步添加的。
```

---

## Output Structure: 知识地图

land 产出的不是散乱笔记，而是**结构化的知识架构**，遵循 Harness Engineering 渐进式披露原则：

```
output/{project-name}/
├── INDEX.md                ← 入口地图 (~100 行，只放指针)
├── architecture.md         ← 分层架构 + 模块关系图
├── modules/                ← 每个核心模块一个文件
│   └── {module-name}.md   ← 职责、入口文件、依赖、关键逻辑
├── people.md               ← 关键人物/团队 + 负责领域
├── risks.md                ← 技术债、已知问题
├── glossary.md             ← 业务术语表
├── onboarding-checklist.md ← 自动生成的 Landing 待办
└── explorer.html           ← 交互式知识浏览器 (可选)
```

### INDEX.md 设计原则 (来自 Ryan Lopopolo, OpenAI)

> "给 AI 一张地图，不是一本说明书。~100 行入口 + 指针 + 渐进发现。"

- 不超过 100 行
- 每条信息都是**指针**（链接到更深的文档），不内联详情
- 先总览 → 再模块 → 再细节（渐进式）

---

## Extension Guide: 下一步扩展

### 优先级排序

```
P0 (马上有用):
├── 上下文压缩 — history 太长时自动 summarize
├── Streaming 输出 — 不用等 LLM 全部生成完
└── .env 文件支持 — 不用每次 export

P1 (提升体验):
├── 交互式确认 — 高危操作前问用户 "确认执行?"
├── 更好的循环检测 — sliding window 而非精确匹配
├── 输出目录自动管理 — 按项目名和日期组织
└── 彩色 Markdown 渲染 — 终端里渲染 Agent 的 MD 输出

P2 (接近 Claude Code):
├── SubAgent — 大任务分解成子任务
├── MCP 支持 — 接入 MCP Server 获取更多工具
├── Plugin/Skill 系统 — 可扩展的能力
├── Prompt Cache — 利用 LLM 前缀缓存降低延迟
└── 向量记忆 — 语义检索而非全量召回
```

### 扩展示例：添加一个新工具

只需在 `tools.py` 底部加一个函数：

```python
@tool(description="获取 Git 仓库的贡献者统计")
def git_contributors(path: str = ".") -> str:
    """path: Git 仓库路径"""
    result = subprocess.run(
        ["git", "-C", path, "shortlog", "-sn", "--all"],
        capture_output=True, text=True, timeout=15
    )
    return result.stdout.strip() or "(no contributors found)"
```

不需要改任何其他文件——`@tool` 自动注册，Agent 自动发现。

---

## Learning Resources: 学习资料

### 理解 Harness 的概念

| 资源 | 核心价值 |
|------|---------|
| [Harness Engineering (Ryan Lopopolo, OpenAI)](https://openai.com/index/harness-engineering/) | "给 AI 地图，不是说明书" — land 的产出结构直接来自这个思想 |
| [Building Effective Agents (Anthropic)](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/building-effective-agents) | Agent Loop 的设计模式：Augmented LLM → Workflow → Autonomous |
| [Context Engineering (Torantulino)](https://www.latent.space/p/context-engineering) | 从 Prompt Engineering 到 Context Engineering 的范式转移 |
| [Harness Engineering (Martin Fowler)](https://martinfowler.com/articles/building-agents-with-harness.html) | 工程视角的 Harness 设计原则 |

### 研究 Claude Code 的 Harness

| 资源 | 核心价值 |
|------|---------|
| [Claude Code 官方文档](https://docs.anthropic.com/en/docs/claude-code) | 5 层安全、SubAgent、Skill/Hook、Memory 系统 |
| [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices) | System Prompt 设计、CLAUDE.md 约定 |
| [Claude Code 源码分析](https://github.com/anthropics/claude-code) | 从用户视角理解完整 Harness 行为 |

### 研究 DeerFlow 的 Harness

| 资源 | 核心价值 |
|------|---------|
| [DeerFlow GitHub](https://github.com/bytedance/deer-flow) | 14 阶段中间件、后端轮询、Harness/App 边界 |
| 重点阅读: `deerflow/agents/lead_agent/middleware/` | 每个中间件对应一个 Agent 特有问题 |
| 重点阅读: `tests/test_harness_boundary.py` | 用 AST 检测 import 确保边界——和 Capa 的 API/SPI 同构 |

### OpenAI Function Calling 协议

| 资源 | 核心价值 |
|------|---------|
| [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling) | tools.py 的 JSON Schema 格式来源 |
| [OpenAI API Reference](https://platform.openai.com/docs/api-reference/chat/create) | messages/tool_calls/tool 三种 role 的协议细节 |

### Agent 协议标准

| 资源 | 核心价值 |
|------|---------|
| [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) | Agent ↔ 工具/数据的标准协议 |
| [A2A (Agent-to-Agent)](https://github.com/google/A2A) | Agent ↔ Agent 协作协议 |

---

## Source Map: 代码行数与知识图谱映射

```
文件           行数    Harness 子系统         对应概念
────────────  ────    ─────────────         ─────────
tools.py      217     Tool Integration      工具注册、Schema 生成、执行
agent.py      171     Agent Loop            Think → Act → Observe 循环
cli.py        180     Terminal Interface    交互层、REPL、特殊命令
prompt.py     135     Context Engineering   System Prompt 分段动态组装
memory.py      95     Memory & State        JSON 持久化、Token 预算回忆
safety.py      62     Safety & Guardrails   命令黑名单、循环检测
llm.py         41     LLM Abstraction       OpenAI 兼容客户端
────────────  ────
合计           901

代码量分布揭示 Harness 的本质:
  工具层最多 (217) — Agent 的价值在于使用工具
  LLM 层最少 (41)  — 调用 LLM 本身不产生价值
  其余都是"围绕 LLM 的基础设施"
```

---

## License

MIT
