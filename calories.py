#!/usr/bin/env python3
"""
Calories Tracker CLI - 记录饮食、运动、身体状态、里程碑，查询热量收支和趋势。
纯 Python 标准库实现，无外部依赖。

用法：
    python3 calories.py log --date 2026-04-30 --category meal --moment 午餐 --data '{...}'
    python3 calories.py log --date 2026-04-30 --category exercise --data '{...}'
    python3 calories.py log --date 2026-04-30 --category milestone --data '{"text":"深蹲PR 120kg"}'
    python3 calories.py summary --date 2026-04-30
    python3 calories.py trend --from 2026-04-24 --to 2026-04-30
    python3 calories.py trend --days 7
    python3 calories.py delete --id 3
    python3 calories.py update --id 3 --data '{...}'
    python3 calories.py set-profile --key goal --value "减脂为主，兼顾增肌"
    python3 calories.py get-profile
    python3 calories.py delete-profile --key target_deficit
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta

def _get_data_dir():
    """跨平台用户数据目录：macOS ~/Library/Application Support, Linux ~/.local/share, Windows %APPDATA%"""
    if sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
    return os.path.join(base, "calories")


DB_DIR = _get_data_dir()
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "data.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    _init_tables(conn)
    return conn


def _init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            moment TEXT,
            data_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_entries_date_category ON entries(date, category);

        CREATE TABLE IF NOT EXISTS profile (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)


# ─── 通用 log 命令 ───


def cmd_add_entry(args):
    data = json.loads(args.data)
    conn = get_db()
    conn.execute(
        "INSERT INTO entries (date, category, moment, data_json) VALUES (?,?,?,?)",
        (args.date, args.category, args.moment, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    # ── 数据已入库，下面仅为输出确认信息 ──
    # 当 CLI 直接调用时给用户看，当 Skill 调用时给 agent 做回复素材。
    label = _category_label(args.category)
    moment_str = f" ({args.moment})" if args.moment else ""

    if args.category == "meal":
        items = data.get("items", [])
        total_cal = sum(it.get("cal", 0) for it in items)
        total_protein = sum(it.get("protein", 0) for it in items)
        food_list = "、".join(it.get("name", "?") for it in items)
        print(f"已记录 {args.date} {label}{moment_str}：{food_list}")
        print(f"合计：{total_cal:.0f} kcal | 蛋白质 {total_protein:.1f}g")
    elif args.category == "exercise":
        items = data.get("items", [])
        total_burned = sum(it.get("cal_burned", 0) for it in items)
        exercise_list = "、".join(f"{it.get('type','')}" for it in items)
        print(f"已记录 {args.date} {label}：{exercise_list}")
        print(f"合计消耗：{total_burned:.0f} kcal")
    elif args.category == "body":
        parts = [f"已记录 {args.date} {label}"]
        if data.get("weight_kg"):
            parts.append(f"体重 {data['weight_kg']:.1f}kg ({data['weight_kg']*2:.1f}斤)")
        if data.get("feeling"):
            parts.append(f"感觉：{data['feeling']}")
        print(" | ".join(parts))
    elif args.category == "milestone":
        print(f"已记录里程碑 {args.date}：{data.get('text', '')}")
    else:
        print(f"已记录 {args.date} [{args.category}]{moment_str}")


def cmd_daily_summary(args):
    """单日汇总：按类别展开当天所有记录并计算热量收支。多日场景用 trend。"""
    conn = get_db()
    d = args.date
    rows = conn.execute(
        "SELECT id, category, moment, data_json FROM entries WHERE date=? ORDER BY created_at",
        (d,),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"{d} 暂无记录。")
        return

    print(f"=== {d} 日汇总 ===\n")

    meals = [r for r in rows if r["category"] == "meal"]
    exercises = [r for r in rows if r["category"] == "exercise"]
    bodies = [r for r in rows if r["category"] == "body"]
    milestones = [r for r in rows if r["category"] == "milestone"]
    notes = [r for r in rows if r["category"] == "note"]

    # 身体状态
    if bodies:
        body_data = json.loads(bodies[-1]["data_json"])
        parts = []
        if body_data.get("weight_kg"):
            parts.append(f"体重 {body_data['weight_kg']:.1f}kg ({body_data['weight_kg']*2:.1f}斤)")
        if body_data.get("feeling"):
            parts.append(f"感觉：{body_data['feeling']}")
        extras = {k: v for k, v in body_data.items() if k not in ("weight_kg", "feeling")}
        for k, v in extras.items():
            parts.append(f"{k}: {v}")
        if parts:
            print(f"[身体] (id={bodies[-1]['id']}) " + " | ".join(parts))
            print()

    # 饮食
    day_cal = day_p = day_f = day_c = 0
    if meals:
        print("[饮食]")
        for row in meals:
            data = json.loads(row["data_json"])
            items = data.get("items", [])
            moment = row["moment"] or "未分类"
            moment_label = _moment_label(moment)
            food_list = "、".join(f"{it['name']}({it.get('qty','')})" for it in items)
            cal = sum(it.get("cal", 0) for it in items)
            protein = sum(it.get("protein", 0) for it in items)
            fat = sum(it.get("fat", 0) for it in items)
            carbs = sum(it.get("carbs", 0) for it in items)
            print(f"  [{moment_label}] (id={row['id']}) {food_list} — {cal:.0f} kcal")
            day_cal += cal
            day_p += protein
            day_f += fat
            day_c += carbs
        print(f"  ── 饮食合计：{day_cal:.0f} kcal | P {day_p:.1f}g | F {day_f:.1f}g | C {day_c:.1f}g")
        print()

    # 运动
    day_burned = 0
    if exercises:
        print("[运动]")
        for row in exercises:
            data = json.loads(row["data_json"])
            for it in data.get("items", []):
                print(f"  (id={row['id']}) {it.get('type','')} ({it.get('detail','')}) {it.get('duration_min',0)}min — {it.get('cal_burned',0):.0f} kcal")
            day_burned += sum(it.get("cal_burned", 0) for it in data.get("items", []))
        print(f"  ── 运动合计消耗：{day_burned:.0f} kcal")
        print()

    # 热量收支
    if meals or exercises:
        print("[热量收支]")
        print(f"  摄入：{day_cal:.0f} kcal")
        print(f"  运动消耗：{day_burned:.0f} kcal")
        net = day_cal - day_burned
        label = "盈余" if net > 0 else ("赤字" if net < 0 else "平衡")
        print(f"  净值（摄入-运动消耗）：{net:+.0f} kcal（{label}）")
        print(f"  注：未计入基础代谢(BMR)，实际赤字 = BMR + 运动消耗 - 摄入")
        print()

    # 里程碑
    if milestones:
        print("[里程碑]")
        for row in milestones:
            data = json.loads(row["data_json"])
            print(f"  (id={row['id']}) {data.get('text', '')}")
        print()

    # 备注
    if notes:
        print("[备注]")
        for row in notes:
            data = json.loads(row["data_json"])
            print(f"  (id={row['id']}) {data.get('text', '')}")
        print()


def cmd_show_trend(args):
    """多日趋势：展示日期范围内每天的摄入/消耗/净值及身体指标。

    两种指定范围方式（二选一）：
      --from/--to  精确指定起止日期
      --days       从今天往前推 N 天（合并了原 history 命令）

    身体指标列（如 weight_kg、waist_cm）根据范围内实际数据动态生成，
    只取数值字段，文本字段（如 feeling）不适合放趋势表。
    无数据的天显示 "-" 而非跳过，便于 agent 识别录入缺失。
    """
    conn = get_db()

    # ── 确定日期范围：--days 从今天往前推，否则用 --from/--to ──
    if args.days is not None:
        if args.days <= 0:
            print(f"错误：--days 必须为正整数，收到 {args.days}")
            sys.exit(1)
        end_date = date.today()
        start_date = end_date - timedelta(days=args.days - 1)
    elif args.start and args.end:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
        if start_date > end_date:
            print(f"错误：--from ({args.start}) 不能晚于 --to ({args.end})")
            sys.exit(1)
    else:
        print("错误：请指定 --from/--to 或 --days")
        sys.exit(1)

    # ── 第一遍：逐天收集数据，同时发现所有 body 数值字段名 ──
    body_keys = []  # 按首次出现的顺序排列
    day_rows = []   # [(date_str, {intake, burned, body, has_data}), ...]

    current = start_date
    while current <= end_date:
        d = current.isoformat()
        rows = conn.execute(
            "SELECT category, data_json FROM entries WHERE date=?", (d,)
        ).fetchall()

        intake = 0
        burned = 0
        body = {}
        has_data = len(rows) > 0

        for row in rows:
            data = json.loads(row["data_json"])
            if row["category"] == "meal":
                intake += sum(it.get("cal", 0) for it in data.get("items", []))
            elif row["category"] == "exercise":
                burned += sum(it.get("cal_burned", 0) for it in data.get("items", []))
            elif row["category"] == "body":
                for k, v in data.items():
                    if isinstance(v, (int, float)):
                        # 同一天多条 body 记录时，取第一条（通常是晨起数据）
                        if k not in body:
                            body[k] = v
                        if k not in body_keys:
                            body_keys.append(k)

        day_rows.append((d, {"intake": intake, "burned": burned, "body": body, "has_data": has_data}))
        current += timedelta(days=1)

    conn.close()

    # ── 第二遍：打印表格（此时 body_keys 已确定，可以生成完整表头） ──
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()
    print(f"=== {start_str} ~ {end_str} 趋势 ===\n")

    # 表头：固定列（日期/摄入/运动/净值）+ 动态 body 列
    header = f"{'日期':<12} {'摄入kcal':>8} {'运动kcal':>8} {'净值':>8}"
    for key in body_keys:
        header += f" {key:>10}"
    print(header)
    sep_width = 39 + len(body_keys) * 11
    print("-" * sep_width)

    # 逐天输出
    total_intake = total_burned = 0
    days_with_data = 0

    for d, info in day_rows:
        if not info["has_data"]:
            # 无记录的天：所有列填 "-"
            row_str = f"{d:<12} {'-':>8} {'-':>8} {'-':>8}"
            for _ in body_keys:
                row_str += f" {'-':>10}"
            print(row_str)
        else:
            intake = info["intake"]
            burned = info["burned"]
            net = intake - burned
            row_str = f"{d:<12} {intake:>8.0f} {burned:>8.0f} {net:>+8.0f}"
            for key in body_keys:
                val = info["body"].get(key)
                row_str += f" {val:>10.1f}" if val is not None else f" {'-':>10}"
            print(row_str)
            total_intake += intake
            total_burned += burned
            days_with_data += 1

    # 平均值（仅基于有数据的天数，跳过无记录的天）
    if days_with_data > 0:
        print("-" * sep_width)
        avg_intake = total_intake / days_with_data
        avg_burned = total_burned / days_with_data
        avg_net = avg_intake - avg_burned
        avg_str = f"{'平均':<12} {avg_intake:>8.0f} {avg_burned:>8.0f} {avg_net:>+8.0f}"
        for key in body_keys:
            vals = [info["body"][key] for _, info in day_rows if key in info["body"]]
            if vals:
                avg_str += f" {sum(vals)/len(vals):>10.1f}"
            else:
                avg_str += f" {'-':>10}"
        print(avg_str)


def cmd_delete_entry(args):
    conn = get_db()
    row = conn.execute("SELECT id, date, category, moment, data_json FROM entries WHERE id=?", (args.id,)).fetchone()
    if not row:
        print(f"未找到记录 (id={args.id})")
        conn.close()
        return

    conn.execute("DELETE FROM entries WHERE id=?", (args.id,))
    conn.commit()
    conn.close()
    print(f"已删除 {row['date']} {_category_label(row['category'])} 记录 (id={args.id})")


def cmd_update_entry(args):
    """更新一条记录的 data_json，保留原 id/date/category/moment 不变。"""
    conn = get_db()
    row = conn.execute(
        "SELECT id, date, category, moment, data_json FROM entries WHERE id=?",
        (args.id,),
    ).fetchone()
    if not row:
        print(f"未找到记录 (id={args.id})")
        conn.close()
        return

    data = json.loads(args.data)
    conn.execute(
        "UPDATE entries SET data_json=? WHERE id=?",
        (json.dumps(data, ensure_ascii=False), args.id),
    )
    conn.commit()
    conn.close()
    print(f"已更新 {row['date']} {_category_label(row['category'])} 记录 (id={args.id})")


def cmd_set_profile(args):
    conn = get_db()
    conn.execute(
        "INSERT INTO profile (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (args.key, args.value),
    )
    conn.commit()
    conn.close()
    print(f"已设置 {args.key} = {args.value}")


def cmd_get_profile(args):
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM profile ORDER BY key").fetchall()
    conn.close()

    if not rows:
        print("暂无个人档案信息。")
        return

    print("=== 个人档案 ===\n")
    for row in rows:
        print(f"  {row['key']}: {row['value']}")


def cmd_delete_profile(args):
    """删除一个档案字段。用于清理不再需要的 key（如阶段切换时）。"""
    conn = get_db()
    row = conn.execute("SELECT key, value FROM profile WHERE key=?", (args.key,)).fetchone()
    if not row:
        print(f"未找到档案字段：{args.key}")
        conn.close()
        return

    conn.execute("DELETE FROM profile WHERE key=?", (args.key,))
    conn.commit()
    conn.close()
    print(f"已删除档案字段：{args.key}")


# ─── 辅助 ───


def _category_label(cat):
    return {"meal": "饮食", "exercise": "运动", "body": "身体状态",
            "milestone": "里程碑", "note": "备注"}.get(cat, cat)


def _moment_label(moment):
    # moment 直接存中文（如"午餐""下午加餐""夜宵"），原样返回即可。
    # 历史数据可能还有英文 key，做一次兼容映射。
    legacy = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐",
              "snack": "加餐"}
    return legacy.get(moment, moment)


# ─── 参数解析 ───


def main():
    parser = argparse.ArgumentParser(description="Calories Tracker CLI")
    sub = parser.add_subparsers(dest="command")

    # log
    p = sub.add_parser("log", help="记录一条数据")
    p.add_argument("--date", required=True)
    p.add_argument("--category", required=True, help="meal/exercise/body/milestone/note")
    p.add_argument("--moment", default=None, help="中文餐次标签，如 早餐/午餐/下午加餐/夜宵（仅 meal 时使用，不确定时不传）")
    p.add_argument("--data", required=True, help="JSON 数据")

    # summary
    p = sub.add_parser("summary", help="查询当日汇总")
    p.add_argument("--date", required=True)

    # trend（合并了原 history 命令，--from/--to 或 --days 二选一）
    p = sub.add_parser("trend", help="查询多日趋势")
    p.add_argument("--from", dest="start", default=None, help="起始日期 YYYY-MM-DD")
    p.add_argument("--to", dest="end", default=None, help="结束日期 YYYY-MM-DD")
    p.add_argument("--days", type=int, default=None, help="从今天往前推N天（与 --from/--to 二选一）")

    # delete
    p = sub.add_parser("delete", help="删除一条记录")
    p.add_argument("--id", required=True, type=int)

    # update
    p = sub.add_parser("update", help="更新一条记录的数据")
    p.add_argument("--id", required=True, type=int)
    p.add_argument("--data", required=True, help="新的 JSON 数据")

    # set-profile
    p = sub.add_parser("set-profile", help="设置个人档案")
    p.add_argument("--key", required=True)
    p.add_argument("--value", required=True)

    # get-profile
    sub.add_parser("get-profile", help="查看个人档案")

    # delete-profile
    p = sub.add_parser("delete-profile", help="删除一个档案字段")
    p.add_argument("--key", required=True, help="要删除的档案字段名")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "log": cmd_add_entry,
        "summary": cmd_daily_summary,
        "trend": cmd_show_trend,
        "delete": cmd_delete_entry,
        "update": cmd_update_entry,
        "set-profile": cmd_set_profile,
        "get-profile": cmd_get_profile,
        "delete-profile": cmd_delete_profile,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
