# land — Landing Knowledge Assistant

最小但完整的 Agent Harness，帮助新人快速理解接手的系统。分析代码仓库和文档，产出结构化的知识地图。

## Install

```bash
git clone https://github.com/land-agent/mini-harness.git
cd mini-harness
pip install -e .
```

## Setup

```bash
export GLM_API_KEY=your-api-key
# Optional (defaults shown):
# export GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# export GLM_MODEL=glm-4-flash
```

## Usage

```bash
# 在项目目录中启动 (默认分析当前目录)
cd /path/to/your/repo
land

# 指定项目路径
land /path/to/repo

# One-shot 模式: 执行单条指令后退出
land -p "分析这个项目的整体架构"
land /path/to/repo -p "帮我生成知识地图到 output/"

# 恢复之前的会话
land --session 2026-03-30-143022
```

## Architecture

```
User Input
  → prompt.py 组装上下文 (角色 + 工具 + 记忆 + 约束)
  → llm.py 调用 GLM
  → agent.py 解析响应
  → tool_calls? → safety.py 检查 → tools.py 执行 → memory.py 记录
  → 文本响应? → 输出给用户
  → 循环直到完成
```

```
harness/
├── agent.py   ← Agent Loop: think → act → observe
├── llm.py     ← LLM 客户端 (GLM, OpenAI 兼容)
├── tools.py   ← 工具注册表 + 6 个内置工具
├── memory.py  ← 记忆系统 (JSON 持久化)
├── prompt.py  ← System Prompt 动态组装
└── safety.py  ← 安全层 (黑名单 + 循环检测)
```

## Tools

| 工具 | 说明 |
|------|------|
| `read_file` | 读取文件内容（带行号） |
| `list_dir` | 列出目录结构 |
| `search_code` | 搜索代码模式 |
| `run_command` | 执行 shell 命令 (git/gh/glab/feishu-cli...) |
| `write_file` | 写入文件 |
| `memorize` | 记住重要发现 |

## Commands

| 命令 | 说明 |
|------|------|
| `/memory` | 查看已记忆的事实 |
| `/output` | 查看输出目录 |
| `/session` | 当前会话信息 |
| `/sessions` | 列出所有会话 |
| `/help` | 帮助 |
| `/quit` | 保存并退出 |

## Output Structure

生成的知识地图遵循 [Harness Engineering](https://openai.com/index/harness-engineering/) 渐进式披露原则：

```
output/{project-name}/
├── INDEX.md            ← 入口地图 (~100 行)
├── architecture.md     ← 架构图
├── modules/            ← 每模块一个文件
├── people.md           ← 关键人物
├── risks.md            ← 风险和技术债
├── glossary.md         ← 术语表
└── onboarding-checklist.md
```
