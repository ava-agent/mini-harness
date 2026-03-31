"""Skill System — predefined workflows triggered by /commands.

Claude Code has skills like /commit, /review-pr that trigger
multi-step predefined workflows. The Skill is NOT a single function —
it's a prompt template that gets injected into the Agent's next turn,
guiding it through a structured workflow.

For Landing Assistant, built-in skills:
  /analyze  — Full project analysis workflow
  /map      — Generate knowledge map to output/
  /explore  — Deep-dive into a specific module
  /people   — Identify key contributors and owners
  /risks    — Identify tech debt and known issues
"""

from __future__ import annotations

from typing import Optional


class Skill:
    """A predefined workflow with a name, description, and prompt template."""

    def __init__(self, name: str, description: str, prompt_template: str) -> None:
        self.name = name
        self.description = description
        self.prompt_template = prompt_template

    def render(self, args: str = "", project_path: str = "") -> str:
        """Render the skill prompt with arguments."""
        return self.prompt_template.format(
            args=args,
            project=project_path or ".",
        )


class SkillRegistry:
    """Registry of available skills."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def render(self, name: str, args: str = "", project_path: str = "") -> Optional[str]:
        """Look up a skill and render its prompt. Returns None if not found."""
        skill = self.get(name)
        if skill:
            return skill.render(args, project_path)
        return None


# ---------------------------------------------------------------------------
# Global registry + built-in skills
# ---------------------------------------------------------------------------

skill_registry = SkillRegistry()

skill_registry.register(Skill(
    name="analyze",
    description="全面分析项目：结构、技术栈、核心模块、近期活动",
    prompt_template="""\
请对项目 {project} 进行全面分析，按以下步骤执行：

1. **目录结构**: 使用 list_dir 查看项目骨架 (depth=2)
2. **技术栈识别**: 读取 package.json / pom.xml / go.mod / requirements.txt / build.gradle 等
3. **入口文件**: 读取 README.md 和主入口文件
4. **Git 活跃度**: 执行 `git log --oneline -20` 和 `git shortlog -sn --all`
5. **核心模块**: 识别主要模块并用 memorize 记住每个模块的职责

分析完成后，输出一份结构化的项目概览，包含：
- 一句话描述
- 技术栈
- 核心模块列表 (名称 + 一句话职责)
- 关键贡献者
- 近期活跃方向

{args}""",
))

skill_registry.register(Skill(
    name="map",
    description="生成结构化知识地图到 output/ 目录",
    prompt_template="""\
请为项目 {project} 生成完整的知识地图，按以下结构写入文件：

1. 先用 /analyze 的方式全面了解项目
2. 然后依次创建以下文件：

   - `output/INDEX.md` — 入口地图 (~100 行，只放指针，不内联详情)
   - `output/architecture.md` — 分层架构图 + 模块关系
   - `output/modules/` — 每个核心模块一个文件 (职责、入口、依赖)
   - `output/people.md` — 关键人物 + 负责领域
   - `output/risks.md` — 技术债和已知问题
   - `output/glossary.md` — 业务术语表
   - `output/onboarding-checklist.md` — Landing 待办清单

INDEX.md 遵循 Harness Engineering 原则：~100 行地图，每条都是指针。

{args}""",
))

skill_registry.register(Skill(
    name="explore",
    description="深度探索一个特定模块或目录",
    prompt_template="""\
请深度探索项目 {project} 中的以下部分: {args}

分析步骤：
1. 列出目标目录的完整结构
2. 读取入口文件和核心文件
3. 搜索关键类/函数定义
4. 分析依赖关系 (import/require/include)
5. 查看 git blame 了解谁最近修改了这些文件
6. 用 memorize 记住关键发现

输出一份模块深度分析报告。""",
))

skill_registry.register(Skill(
    name="people",
    description="识别关键贡献者和模块 owner",
    prompt_template="""\
请分析项目 {project} 的贡献者信息：

1. 执行 `git shortlog -sn --all` 查看总贡献排名
2. 对核心目录执行 `git log --format='%an' <dir> | sort | uniq -c | sort -rn | head -5`
3. 查看 CODEOWNERS / MAINTAINERS 文件 (如果存在)
4. 分析最近 30 天的活跃贡献者: `git log --since='30 days ago' --format='%an' | sort | uniq -c | sort -rn`

输出一份关键人物列表，包含：
- 姓名/ID
- 主要负责领域
- 活跃程度

{args}""",
))

skill_registry.register(Skill(
    name="risks",
    description="识别技术债、安全风险和需要注意的问题",
    prompt_template="""\
请分析项目 {project} 的潜在风险：

1. 搜索 TODO/FIXME/HACK/XXX 注释: `search_code("TODO|FIXME|HACK|XXX")`
2. 检查依赖是否过时 (package.json / pom.xml 等)
3. 查看最近的 bug fix 提交: `git log --oneline --grep="fix" -20`
4. 检查是否有硬编码的配置或凭证模式
5. 查看 .gitignore 是否合理

输出一份风险清单，按严重程度排序。

{args}""",
))
