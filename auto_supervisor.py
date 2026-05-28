"""
auto_supervisor.py — 补跑总控 V1.2.1
每5分钟由 launchd 调起，检查当日各任务状态，按需补跑。
状态文件：output/auto_state.json
日志：由 run_supervisor.sh 将 stdout/stderr 重定向至 logs/auto_run.log
"""
import fcntl
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR   = BASE_DIR / "logs"
STATE_FILE = OUTPUT_DIR / "auto_state.json"
PYTHON     = str(BASE_DIR / ".venv" / "bin" / "python3")

LOGS_DIR.mkdir(exist_ok=True)
_log_fmt = logging.Formatter("[%(asctime)s] [supervisor] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
# 只挂一个 StreamHandler（stdout）：
# run_supervisor.sh 已经做了 `exec >> auto_run.log 2>&1`，stdout 会被重定向到日志文件。
# 之前同时挂 FileHandler + StreamHandler 会导致每行日志被写两次到 auto_run.log，
# 出现"===== START pick ====="重复打印的视觉假象。
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_log_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_stream_handler])
logger = logging.getLogger(__name__)


# ─────────────────── 进程锁（防止并发重入） ──────────────────────

def _try_lock() -> bool:
    """获取文件排他锁，进程退出时自动释放。失败说明另一实例正在运行。"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        fh = open(OUTPUT_DIR / ".supervisor.lock", "w")
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _try_lock._fh = fh   # 挂到模块上，防止 GC 释放（释放即解锁）
        return True
    except OSError:
        return False


# ─────────────────── 状态读写 ────────────────────────────────────

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _set(state: dict, date_str: str, **kwargs) -> None:
    """更新指定日期的字段并立即持久化。"""
    state.setdefault(date_str, {}).update(kwargs)
    _save_state(state)


# ─────────────────── 任务执行 ────────────────────────────────────

_task_lock_handles: dict = {}   # 持有锁文件句柄，进程退出时自动释放


def _acquire_task_lock(label: str, date_str: str) -> bool:
    """
    每个 (任务, 日期) 申请一把独立的文件锁。
    成功返回 True；失败说明同日同任务已有实例在跑（或最近异常死掉但 fd 仍在）。
    """
    OUTPUT_DIR.mkdir(exist_ok=True)
    lock_path = OUTPUT_DIR / f".task_{label}_{date_str}.lock"
    try:
        fh = open(lock_path, "w")
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _task_lock_handles[(label, date_str)] = fh   # 防 GC
        return True
    except OSError:
        return False


def _run(label: str, extra_args: list) -> bool:
    """
    运行 python run.py [extra_args]。
    子进程 stdout/stderr 继承自父进程（由 run_supervisor.sh 重定向到 auto_run.log）。
    返回是否成功（exit code == 0）。

    新增：每个 (任务, 日期) 独立文件锁，确保"同一任务同一日期只允许一个实例执行"。
    """
    ds = datetime.now().strftime("%Y-%m-%d")
    if not _acquire_task_lock(label, ds):
        logger.warning(
            f"[task-lock] 任务 {label} ({ds}) 已有实例在运行，本次跳过；不重复推送微信"
        )
        return False

    cmd = [PYTHON, str(BASE_DIR / "run.py")] + extra_args
    logger.info(f"===== START {label} =====")
    sys.stdout.flush()
    try:
        rc = subprocess.call(cmd, cwd=str(BASE_DIR))
    except Exception as e:
        logger.error(f"执行异常: {e}")
        rc = -1
    sys.stdout.flush()
    logger.info(f"===== END {label} exit={rc} =====")
    return rc == 0


# ─────────────────── 微信提醒 ────────────────────────────────────

def _notify(title: str, body: str) -> None:
    """错过关键窗口时通过 Server酱 发送微信提醒，失败不中断主逻辑。"""
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
        sys.path.insert(0, str(BASE_DIR))
        import notifier
        sendkey = os.environ.get("SERVERCHAN_SENDKEY", "")
        if sendkey and not sendkey.startswith("SCTxxx"):
            notifier.send_to_serverchan(title, body, sendkey)
        else:
            logger.info(f"提醒（未配置推送）：{title} — {body}")
    except Exception as e:
        logger.warning(f"发送提醒失败（不影响主逻辑）: {e}")


# ─────────────────── 工具 ────────────────────────────────────────

def _last_friday(today: date) -> date:
    """返回 today 当天或之前最近的周五（weekday=4）。"""
    return today - timedelta(days=(today.weekday() - 4) % 7)


# ─────────────────── CSV 权威源校验（V1.4 误报修复） ─────────────
# 背景：state.json 里 check_buy_done 来自子进程 exit code（_run 返回值）。
#       但 run.py 在 check_buy 业务跑完（已写 CSV + 已推送微信）之后，
#       decision_log.write_buy_decision 可能因数据兜底缺陷抛 TypeError 导致 exit=1。
#       这会使 check_buy_done 永远为 False，10:00 之后 supervisor 误判
#       "错过 9:36 窗口" 并发"任务补跑提醒"——而事实是 9:36 已经按时完成。
#
# 修复：以 output/trade_review.csv 为权威源。今日 (report_date=YYYYMMDD)
#       如果存在任意一行 buy_signal_0935 字段非空（True 或 False 均算"已检查"），
#       则证明 check_buy 业务上已完成，supervisor 不应再推"错过窗口"。

TRADE_REVIEW_CSV = BASE_DIR / "output" / "trade_review.csv"


def _check_buy_csv_completed_today(today: date) -> tuple:
    """
    读 trade_review.csv 判断今天 check_buy 业务上是否已完成。
    严格只读，无任何写入。

    返回 (completed: bool, n_with_signal: int, n_total: int, detail: str)
      - completed:    今天 trade_review.csv 已含 buy_signal_0935 非空的行（任意一行即算完成）
      - n_with_signal: 今天 buy_signal_0935 非空的行数
      - n_total:      今天的总行数
      - detail:       人类可读的诊断字符串

    设计原则：
      - 任何读取异常 → 返回 completed=False，让上层退到原有逻辑（不影响安全）
      - 不依赖 pandas（保持 supervisor 轻量；用 csv 标准库够了）
    """
    today_yyyymmdd = today.strftime("%Y%m%d")
    if not TRADE_REVIEW_CSV.exists():
        return False, 0, 0, "trade_review.csv 不存在"

    try:
        import csv as _csv
        # 用 utf-8-sig 自动剥离 trade_review.csv 头部的 BOM(﻿)
        # 否则 fieldnames[0] 会是 '﻿report_date' 导致列名匹配失败
        with TRADE_REVIEW_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            reader = _csv.DictReader(f)
            if "report_date" not in (reader.fieldnames or []) or \
               "buy_signal_0935" not in (reader.fieldnames or []):
                return False, 0, 0, "CSV 缺关键列 report_date / buy_signal_0935"

            n_total        = 0
            n_with_signal  = 0
            for row in reader:
                if str(row.get("report_date", "")).strip() != today_yyyymmdd:
                    continue
                n_total += 1
                sig = str(row.get("buy_signal_0935", "")).strip().lower()
                # 非空 + 不是 NaN 字面值 = 已检查过（True / False 都算）
                if sig and sig not in ("nan", "none", "null"):
                    n_with_signal += 1

        completed = n_with_signal > 0
        detail = (
            f"today={today_yyyymmdd}  rows={n_total}  with_signal={n_with_signal}  "
            f"→ {'已完成 (CSV 权威)' if completed else '未完成'}"
        )
        return completed, n_with_signal, n_total, detail
    except Exception as e:
        return False, 0, 0, f"读 CSV 异常（退到原有逻辑）: {type(e).__name__}: {e}"


# ─────────────────── 主逻辑 ──────────────────────────────────────

def run_supervisor() -> None:
    now     = datetime.now()
    today   = now.date()
    ds      = today.strftime("%Y-%m-%d")   # 今天的 state key
    hhmm    = now.hour * 60 + now.minute   # 当前时间（分钟整数，方便比较）
    weekday = today.weekday()              # 0=Mon … 6=Sun
    is_td   = weekday < 5                  # 周一-周五视为交易日（不排除节假日）

    state = _load_state()

    # ── 1. 盘前选股 python run.py ──────────────────────────────────
    #   08:50 起允许运行；09:35 后补跑标记 delayed_pick；15:00 后视为错过
    if is_td:
        day = state.setdefault(ds, {})
        if not day.get("pick_done"):
            if hhmm < 8 * 60 + 50:
                logger.info("等待 08:50 盘前选股窗口，本次跳过")

            elif hhmm < 15 * 60:
                delayed = hhmm > 9 * 60 + 35
                if delayed:
                    logger.info("pick 延迟补跑（当前时间 > 09:35），标记 delayed_pick=true")
                extra = {"delayed_pick": True} if delayed else {}
                ok = _run("pick", [])
                _set(state, ds, pick_done=ok,
                     pick_time=now.strftime("%H:%M:%S"), **extra)

            elif not day.get("missed_pick_notified"):
                logger.warning("当前时间 >= 15:00，今日盘前选股窗口已错过")
                _set(state, ds, missed_pick_window=True, missed_pick_notified=True)
                _notify(
                    "【朱哥短线雷达｜任务补跑提醒】",
                    "今天电脑开机较晚（15:00后），今日盘前选股窗口已错过，"
                    "不生成今日报告，以免数据失真。",
                )

    # ── 1.5. 主题龙头 python run.py --theme-auto ──────────────────
    # 08:55 起允许运行；下午补跑标记 delayed；不设错过窗口（数据仍有参考价值）
    if is_td:
        day = state.setdefault(ds, {})
        if not day.get("theme_auto_done") and hhmm >= 8 * 60 + 55:
            delayed = hhmm > 9 * 60 + 35
            extra   = {"delayed_theme_auto": True} if delayed else {}
            if delayed:
                logger.info("theme_auto 延迟补跑（当前时间 > 09:35），标记 delayed_theme_auto=true")
            ok = _run("theme_auto", ["--theme-auto"])
            _set(state, ds, theme_auto_done=ok,
                 theme_auto_time=now.strftime("%H:%M:%S"), **extra)

    # ── 2. 买入确认 python run.py --check-buy ─────────────────────
    #   09:36-10:00 且 pick 已完成 → 运行；10:00 后且 pick 曾完成 → 提醒错过
    #   若 pick 本身未跑，check_buy 跳过（无推荐记录，跑了也无意义）
    if is_td:
        day = state.setdefault(ds, {})

        # ── 2.a 自愈：state.json 标 check_buy_done=False，但 CSV 显示业务已完成 ──
        # 修复 2026-05-27 误报：run.py 子进程 exit=1（decision_log 异常）
        # 但 CSV 实际已写入 buy_signal_0935，9:36 业务已成功。以 CSV 为权威源。
        if not day.get("check_buy_done"):
            csv_done, n_sig, n_total, csv_detail = _check_buy_csv_completed_today(today)
            if csv_done:
                logger.info(
                    f"[check_buy] CSV 权威源显示业务已完成 → 自愈 state.check_buy_done=True  ｜ {csv_detail}"
                )
                _set(state, ds,
                     check_buy_done=True,
                     check_buy_recovered_from_csv=True,
                     check_buy_csv_rows=n_total,
                     check_buy_csv_with_signal=n_sig)

        if not day.get("check_buy_done"):
            pick_done = day.get("pick_done", False)
            T_START, T_END = 9 * 60 + 36, 10 * 60

            if T_START <= hhmm <= T_END:
                if pick_done:
                    ok = _run("check_buy", ["--check-buy"])
                    # 子进程 exit=0 → 直接信；exit!=0 → 再读 CSV 兜底
                    # （decision_log 异常会让 exit=1，但 CSV 已经写好了）
                    if not ok:
                        csv_done, n_sig, n_total, csv_detail = _check_buy_csv_completed_today(today)
                        if csv_done:
                            logger.warning(
                                f"[check_buy] 子进程 exit!=0，但 CSV 显示已写入 → "
                                f"按 CSV 标记完成  ｜ {csv_detail}"
                            )
                            ok = True
                            _set(state, ds,
                                 check_buy_recovered_from_csv=True,
                                 check_buy_csv_rows=n_total,
                                 check_buy_csv_with_signal=n_sig)
                    _set(state, ds, check_buy_done=ok,
                         check_buy_time=now.strftime("%H:%M:%S"))
                else:
                    logger.info("check_buy 窗口内但 pick 尚未完成，等待下一轮")

            elif hhmm > T_END and pick_done and not day.get("missed_check_buy_notified"):
                # 防御性二次校验：到这里说明 state 显示未完成 + 自愈也没救回（业务确实没跑），
                # 再读一次 CSV 兜底；只有 CSV 也确认未跑过，才推送"错过窗口"提醒
                csv_done, n_sig, n_total, csv_detail = _check_buy_csv_completed_today(today)
                if csv_done:
                    logger.info(
                        f"[check_buy] 10:00 后再次校验 CSV：业务已完成，"
                        f"抑制'错过窗口'误报  ｜ {csv_detail}"
                    )
                    _set(state, ds,
                         check_buy_done=True,
                         check_buy_recovered_from_csv=True,
                         check_buy_csv_rows=n_total,
                         check_buy_csv_with_signal=n_sig,
                         missed_check_buy_notified=True)   # 标"已处理"，避免后续轮再判
                else:
                    logger.warning(
                        f"当前时间 > 10:00，今日 check_buy 窗口已错过，不补跑  ｜ {csv_detail}"
                    )
                    _set(state, ds, missed_check_buy_window=True,
                         missed_check_buy_notified=True)
                    _notify(
                        "【朱哥短线雷达｜任务补跑提醒】",
                        "今天电脑开机较晚，已错过 9:36 买入确认窗口，"
                        "本日不做模拟买入，以免数据失真。",
                    )

    # ── 2.5. 10:00 二次确认观察 python run.py --second-check ─────
    # 10:00-10:30 窗口；要求当日 check_buy 已完成；仅观察不买入
    if is_td:
        day = state.setdefault(ds, {})
        if not day.get("second_check_done"):
            check_buy_done = day.get("check_buy_done", False)
            T_START, T_END = 10 * 60, 10 * 60 + 30
            if T_START <= hhmm <= T_END:
                if check_buy_done:
                    ok = _run("second_check", ["--second-check"])
                    _set(state, ds, second_check_done=ok,
                         second_check_time=now.strftime("%H:%M:%S"))
                else:
                    logger.info("second_check 窗口内但 check_buy 尚未完成，等待下一轮")
            elif hhmm > T_END and not day.get("missed_second_check_notified"):
                logger.info("当前时间 > 10:30，今日二次观察窗口已错过，不补跑（观察项不强制）")
                _set(state, ds,
                     missed_second_check_window=True,
                     missed_second_check_notified=True)

    # ── 3. T+1 复盘 python run.py --update-review ─────────────────
    #   任意日 19:00 后运行一次即可；update_review 内部已做幂等处理。
    #   阈值改自 15:25 → 19:00（2026-05-27 修复）：与 launchd
    #   com.zhuge.stock.update.plist 的 19:00 排程对齐，避开
    #   akshare 当日收盘后 K 线发布延迟，也避免 15:27 supervisor 轮询
    #   抢跑导致"今日已模拟买入的票还没到 T+1"就被误判为空复盘。
    day = state.setdefault(ds, {})
    if not day.get("update_review_done") and hhmm >= 19 * 60:
        ok = _run("update_review", ["--update-review"])
        _set(state, ds, update_review_done=ok,
             update_review_time=now.strftime("%H:%M:%S"))

    # ── 4. 周报 python run.py --review-summary ────────────────────
    #   周五 15:40 后运行；周末如上周五未跑则补跑（不重复）
    #   state key 用周五日期，确保周六/日补跑后不再重复
    last_fri = _last_friday(today)
    fri_str  = last_fri.strftime("%Y-%m-%d")
    if not state.get(fri_str, {}).get("summary_done"):
        is_fri_window  = (weekday == 4 and hhmm >= 15 * 60 + 40)
        is_weekend_run = (weekday >= 5)
        if is_fri_window or is_weekend_run:
            ok = _run("summary", ["--review-summary"])
            _set(state, fri_str, summary_done=ok,
                 summary_time=now.strftime("%H:%M:%S"))


# ─────────────────── 入口 ────────────────────────────────────────

if __name__ == "__main__":
    if not _try_lock():
        print(
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [supervisor] "
            "另一实例正在运行，本次退出"
        )
        sys.exit(0)

    logger.info(f"supervisor 启动")
    try:
        run_supervisor()
    except Exception as e:
        logger.exception(f"supervisor 异常退出: {e}")
        sys.exit(1)
    logger.info("supervisor 正常退出")
