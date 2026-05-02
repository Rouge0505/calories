# 卡路里教练

AI Agent Skill - 你的 AI 营养与健身教练。

通过自然语言对话，记录每日饮食、运动和身体状态，追踪热量收支趋势，纠正不健康的饮食认知。

## 依赖

- Python 3（标准库，无需 pip install）
- SQLite（Python 内置）

## 文件说明

| 文件 | 用途 |
|------|------|
| `calories.py` | CLI 脚本，所有数据库操作的入口 |
| `SKILL.md` | Skill 定义文件，供 Agent 读取 |
| `data.db` | SQLite 数据库，运行时自动创建，已在 .gitignore 中排除 |

## 使用方式

本项目设计为 Qoder Skill，由 Agent 自动调用，用户无需直接操作命令行。

如需手动测试：

```bash
python3 calories.py log --date 2026-05-02 --category food --data '{"items":"燕麦粥","kcal":350}'
python3 calories.py summary --date 2026-05-02
python3 calories.py trend --days 7
```
