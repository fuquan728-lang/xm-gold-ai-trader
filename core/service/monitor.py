# -*- coding: utf-8 -*-
"""
ServiceMonitor - 服务监控模块 (Phase 1)
负责响应：心跳、账户数据监控、交易统计、状态打印

从 MT5AITradingService 拆分而来 (2026-07-04)
"""

import os
import json
import time
import threading
import glob as _glob_module
from typing import Dict, Any, Optional, Callable

from core.logger import monitor, logger
from core.mql5_data import get_mql5_data_manager
from core import config


class ServiceMonitor:
    """服务监控模块
    - 心跳循环（高可用架构）
    - MT5 账户数据文件监控
    - 交易统计计算与展示
    - 定期状态打印
    """

    def __init__(
        self,
        service_registry,
        local_instance,
        file_handler,
        web_dashboard=None,
        observation_journal=None,
        current_mode_getter: Optional[Callable[[], str]] = None,
    ):
        self._service_registry = service_registry
        self._local_instance = local_instance
        self._file_handler = file_handler
        self._web_dashboard = web_dashboard
        self._observation_journal = observation_journal
        self._current_mode_getter = current_mode_getter or (lambda: "auto")

        self.running = False

        # 状态打印间隔
        self._last_status_print = 0.0
        self._status_print_interval = 60.0

        # 交易统计（初始化为空）
        self._trade_stats: Dict[str, Any] = {
            "total_trades": 0,
            "win_trades": 0,
            "loss_trades": 0,
            "win_rate": 0,
            "total_profit": 0,
            "total_loss": 0,
            "profit_factor": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "buy_trades": 0,
            "sell_trades": 0,
            "sl_hits": 0,
            "tp_hits": 0,
        }

    # ---- 心跳 ----

    def start_heartbeat(self) -> threading.Thread:
        """启动心跳线程"""
        t = threading.Thread(target=self._heartbeat_loop, daemon=True)
        t.start()
        return t

    def _heartbeat_loop(self):
        """心跳循环"""
        logger.info("[HEART] 心跳线程启动")
        while self.running:
            try:
                self._service_registry.heartbeat(self._local_instance.service_id)
                time.sleep(5)
            except Exception as e:
                logger.warning(f"[WARN]  心跳异常: {e}")
                time.sleep(1)

    # ---- 账户数据监控 ----

    def start_account_monitor(self) -> threading.Thread:
        """启动账户数据监控线程"""
        t = threading.Thread(target=self._monitor_account_data, daemon=True)
        t.start()
        return t

    def _monitor_account_data(self):
        """监控 MT5 账户数据文件"""
        logger.info("[DATA] 账户数据监控线程启动")

        possible_locations = []
        last_modified = 0

        while self.running:
            try:
                # 先尝试用 file_handler 的路径
                fh = self._file_handler
                if fh._cached_path:
                    possible_locations.insert(0, fh._cached_path)

                # 添加常见 MT5 Files 目录
                common_paths = [
                    os.path.join(
                        os.path.expanduser("~"),
                        "AppData", "Roaming", "MetaQuotes", "Terminal",
                        "*", "MQL5", "Files",
                    ),
                    os.path.join(
                        os.path.expanduser("~"),
                        "AppData", "Roaming", "MetaQuotes", "Terminal",
                        "*", "Files",
                    ),
                ]

                account_file = None
                # 先检查 file_handler 的位置
                if fh._cached_path:
                    test_file = os.path.join(fh._cached_path, "mt5_account.json")
                    if os.path.exists(test_file):
                        account_file = test_file

                # 如果没找到，尝试其他常见位置
                if not account_file:
                    for path in common_paths:
                        matches = _glob_module.glob(path)
                        for p in matches:
                            test_file = os.path.join(p, "mt5_account.json")
                            if os.path.exists(test_file):
                                account_file = test_file
                                break

                # 如果找到文件
                if account_file:
                    mtime = os.path.getmtime(account_file)
                    if mtime > last_modified:
                        last_modified = mtime
                        try:
                            with open(account_file, "r", encoding="utf-8") as f:
                                content = f.read().strip()

                            if content:
                                data = json.loads(content)
                                if data.get("type") == "mql5_data":
                                    mql5_manager = get_mql5_data_manager()
                                    success = mql5_manager.update_from_json(data)
                                    if success:
                                        logger.debug(f"[OK] 账户数据已更新")
                        except json.JSONDecodeError as e:
                            logger.debug(f"[DATA] JSON解析失败: {e}")
                        except OSError as e:
                            logger.debug(f"[DATA] 文件读取IO错误: {e}")
                        except Exception as e:
                            logger.warning(f"[WARN]  读取账户数据异常: {e}")

                time.sleep(1)
            except Exception as e:
                logger.debug(f"[WARN]  账户数据监控异常: {e}")
                time.sleep(1)

    # ---- 交易统计 ----

    def update_trade_stats(self, trade_history: list):
        """更新交易统计"""
        if not trade_history:
            return

        total_trades = 0
        win_trades = 0
        loss_trades = 0
        total_profit = 0.0
        total_loss = 0.0
        buy_trades = 0
        sell_trades = 0
        sl_hits = 0
        tp_hits = 0

        for trade in trade_history:
            if trade.get("entry") != "OUT":
                continue

            total_trades += 1
            profit = trade.get("profit", 0)
            trade_type = trade.get("type", "")
            sl = trade.get("sl", 0)
            tp = trade.get("tp", 0)

            # MT5平仓逻辑：OUT记录的deal_type是平仓方向
            if trade_type == "BUY":
                sell_trades += 1  # BUY OUT = 平空仓 = SELL开仓
            elif trade_type == "SELL":
                buy_trades += 1  # SELL OUT = 平多仓 = BUY开仓

            if profit >= 0:
                win_trades += 1
                total_profit += profit
            else:
                loss_trades += 1
                total_loss += abs(profit)
                if sl > 0:
                    sl_hits += 1

            if tp > 0:
                tp_hits += 1

        if total_trades > 0:
            win_rate = win_trades / total_trades * 100
            avg_win = total_profit / win_trades if win_trades > 0 else 0
            avg_loss = total_loss / loss_trades if loss_trades > 0 else 0
            profit_factor = total_profit / total_loss if total_loss > 0 else 0

            logger.info(f"[STATS] 交易统计 (最近{total_trades}笔):")
            logger.info(
                f"  总交易: {total_trades} | 盈利: {win_trades} | "
                f"亏损: {loss_trades} | 胜率: {win_rate:.1f}%"
            )
            logger.info(
                f"  总盈利: ${total_profit:.2f} | 总亏损: ${total_loss:.2f} | "
                f"盈亏比: {profit_factor:.2f}"
            )
            logger.info(f"  平均盈利: ${avg_win:.2f} | 平均亏损: ${avg_loss:.2f}")
            logger.info(f"  多单: {buy_trades} | 空单: {sell_trades}")

            self._trade_stats = {
                "total_trades": total_trades,
                "win_trades": win_trades,
                "loss_trades": loss_trades,
                "win_rate": win_rate,
                "total_profit": total_profit,
                "total_loss": total_loss,
                "profit_factor": profit_factor,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "buy_trades": buy_trades,
                "sell_trades": sell_trades,
                "sl_hits": sl_hits,
                "tp_hits": tp_hits,
            }

            # 更新 Dashboard 显示
            if self._web_dashboard:
                self._web_dashboard.trade_stats = self._trade_stats.copy()

    def get_trade_stats(self) -> dict:
        """获取交易统计"""
        return getattr(
            self,
            "_trade_stats",
            {
                "total_trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "win_rate": 0,
                "total_profit": 0,
                "total_loss": 0,
                "profit_factor": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "buy_trades": 0,
                "sell_trades": 0,
                "sl_hits": 0,
                "tp_hits": 0,
            },
        )

    # ---- 状态打印 ----

    def print_status(self, force: bool = False):
        """定期打印服务状态（可外部设置间隔）"""
        now = time.time()
        if force or (now - self._last_status_print) >= self._status_print_interval:
            self._last_status_print = now
            stats = monitor.get_stats()

            status_msg = f"[UP] 状态: 请求={stats['total_requests']}"
            if stats["total_requests"] > 0:
                avg_ms = stats["average_response_time"] * 1000
                status_msg += f" | 平均={avg_ms:.0f}ms"

            cache_total = stats["cache_hits"] + stats["cache_misses"]
            if cache_total > 0:
                hit_rate = stats["cache_hits"] / cache_total * 100
                status_msg += f" | 缓存={hit_rate:.0f}%"

            status_msg += f" | 模式={self._current_mode_getter().upper()}"
            logger.info(status_msg)

    @property
    def status_print_interval(self) -> float:
        return self._status_print_interval

    @status_print_interval.setter
    def status_print_interval(self, value: float):
        self._status_print_interval = value
