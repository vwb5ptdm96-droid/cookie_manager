"""
agent_repair_dispatcher.py
契合 cookie_manager 的 Agent 自动维修调度器
负责防抖熔断、Token预算限制，并通过非交互子进程调用 Claude Code
"""
import os
import sys
import time
import logging
import subprocess
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class AgentRepairDispatcher:
    def __init__(self, cooldown_seconds: int = 1800):
        self.cooldown_seconds = cooldown_seconds
        self._last_triggered: Dict[str, float] = {}

    def is_in_cooldown(self, channel: str, shop_name: str, issue_type: str) -> bool:
        """根据渠道+店铺+问题类型做防抖控制，防止同一账号频繁失败刷爆 Token"""
        fingerprint = f"{channel}:{shop_name}:{issue_type}"
        now = time.time()
        last_time = self._last_triggered.get(fingerprint, 0.0)
        if now - last_time < self.cooldown_seconds:
            logger.info(f"[Dispatcher] {fingerprint} 处于冷却期内 ({int(now - last_time)}s < {self.cooldown_seconds}s)，跳过重复调用")
            return True
        self._last_triggered[fingerprint] = now
        return False

    def trigger_claude_repair(
        self,
        ticket_id: int,
        channel: str,
        shop_name: str,
        cdp_port: int,
        script_path: str,
        issue_type: str = "SCRIPT_FAILURE",
        max_turns: int = 4,
        max_seconds: int = 120
    ) -> Optional[subprocess.Popen]:
        """
        异步触发 Claude Code 执行自动维修
        """
        if self.is_in_cooldown(channel, shop_name, issue_type):
            return None

        prompt = (
            f"系统自动生成维修工单 Ticket #{ticket_id}。\n"
            f"渠道: {channel}, 店铺: {shop_name}, CDP 调试端口: {cdp_port}。\n"
            f"目标脚本: {script_path}。\n"
            f"【预算与SOP要求】：\n"
            f"1. 本任务交互上限为 {max_turns} 轮，严禁过度重试。\n"
            f"2. 请执行 /repair-ticket {ticket_id} {script_path} {cdp_port} 探查现场并尝试排除阻挡。\n"
            f"3. 若发现人机滑块验证码或账号封禁，立即停止操作并在工单报告中说明转人工处理！"
        )

        cmd = ["claude", "-p", prompt, "--max-turns", str(max_turns)]
        logger.info(f"[Dispatcher] 正在为 Ticket #{ticket_id} 唤起 Claude Code (max_turns={max_turns})...")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return proc
        except FileNotFoundError:
            logger.error("[Dispatcher] 未找到 claude CLI，请确保已全局安装 @anthropic-ai/claude-code 并在系统 PATH 中")
            return None
        except Exception as e:
            logger.error(f"[Dispatcher] 唤起 Claude Code 失败: {e}")
            return None

# 全局单例
agent_repair_dispatcher = AgentRepairDispatcher(cooldown_seconds=1800)
