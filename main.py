"""
astrbot_plugin_greeting_bot - 定时问候插件
每天固定时间发送早安、午好、晚安问候
"""

import asyncio
import random
from datetime import datetime

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_greeting_bot",
    "author",
    "定时发送早安、午好、晚安问候",
    "1.0.0",
    "https://github.com/example/astrbot_plugin_greeting_bot"
)
class GreetingBot(Star):
    """定时问候插件主类"""

    # 问候类型键名和显示名
    GREETING_TYPES = {
        "morning": "🌅 早安",
        "noon": "☀️ 午好",
        "evening": "🌙 晚安",
    }

    def __init__(self, context: Context, config):
        super().__init__(context)
        self.config = config
        self._task = None
        self._stop_event = asyncio.Event()
        # 记录今天已经发送过的问候，避免重复发送
        # 格式: {date_str: {greeting_type: True}}
        self._sent_today = {}

        # 启动后台任务
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("[定时问候] 插件已加载，后台任务已启动")

    # ==================== 后台定时任务 ====================

    async def _schedule_loop(self):
        """主循环：每分钟检查是否有需要发送的问候"""
        logger.info("[定时问候] 定时任务循环已启动")
        try:
            while not self._stop_event.is_set():
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")

                # 重置每日记录（新的一天）
                if self._sent_today.get("date") != today_str:
                    self._sent_today = {"date": today_str}

                # 检查每个问候类型
                for gtype in self.GREETING_TYPES:
                    await self._check_and_send(gtype, now, today_str)

                # 等待到下一分钟（对齐到整分钟）
                await self._wait_until_next_minute(now)

        except asyncio.CancelledError:
            logger.info("[定时问候] 定时任务已取消")
        except Exception as e:
            logger.error(f"[定时问候] 定时任务异常: {e}")

    async def _wait_until_next_minute(self, now: datetime):
        """等待到下一个整分钟"""
        seconds = 60 - now.second
        # 至少等 1 秒，避免边界情况
        await asyncio.sleep(max(seconds, 1))

    async def _check_and_send(self, gtype: str, now: datetime, today_str: str):
        """检查指定类型的问候是否需要发送"""
        # 检查总开关
        if not self.config.get("enabled", True):
            return

        # 检查此问候类型是否启用
        gconfig = self.config.get(gtype, {})
        if not gconfig.get("enabled", True):
            return

        # 检查今天是否已发送
        if self._sent_today.get(gtype):
            return

        # 检查目标会话
        targets = self.config.get("targets", [])
        if not targets:
            return

        # 解析时间
        time_str = gconfig.get("time", "07:30")
        try:
            hour, minute = self._parse_time(time_str)
        except ValueError:
            logger.warning(f"[定时问候] 无效的时间格式: {time_str}")
            return

        # 到点了吗？（分钟级判断）
        if now.hour == hour and now.minute == minute:
            messages = gconfig.get("messages", [])
            if not messages:
                logger.warning(f"[定时问候] {gtype} 没有配置问候语")
                return

            # 随机选一条
            greeting = random.choice(messages)

            # 发送到所有目标
            for target in targets:
                try:
                    from astrbot.api.event import MessageChain
                    chain = MessageChain().message(greeting)
                    await self.context.send_message(target, chain)
                    logger.info(f"[定时问候] 已发送 {self.GREETING_TYPES[gtype]} 到 {target}")
                except Exception as e:
                    logger.error(f"[定时问候] 发送到 {target} 失败: {e}")

            # 标记已发送
            self._sent_today[gtype] = True

    @staticmethod
    def _parse_time(time_str: str):
        """解析 HH:MM 格式的时间字符串，返回 (hour, minute)"""
        time_str = time_str.strip()
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError(f"时间格式错误: {time_str}")
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"时间范围错误: {time_str}")
        return hour, minute

    # ==================== 指令 ====================

    @filter.command("greet_add")
    async def greet_add(self, event: AstrMessageEvent):
        """将当前会话添加到问候发送列表"""
        umo = event.unified_msg_origin
        targets = self.config.get("targets", [])

        if umo in targets:
            yield event.plain_result("✅ 当前会话已经在问候列表中了")
            return

        targets.append(umo)
        self.config["targets"] = targets
        try:
            self.config.save_config()
        except Exception as e:
            logger.warning(f"[定时问候] 保存配置失败: {e}")

        # 判断当前是群聊还是私聊
        sender_name = event.get_sender_name()
        yield event.plain_result(
            f"✅ 已将当前会话添加到问候列表！\n"
            f"发送者: {sender_name}\n"
            f"会话标识: {umo[:30]}...\n"
            f"\n现在共有 {len(targets)} 个目标会话"
        )

    @filter.command("greet_remove")
    async def greet_remove(self, event: AstrMessageEvent):
        """将当前会话从问候发送列表移除"""
        umo = event.unified_msg_origin
        targets = self.config.get("targets", [])

        if umo not in targets:
            yield event.plain_result("❌ 当前会话不在问候列表中")
            return

        targets.remove(umo)
        self.config["targets"] = targets
        try:
            self.config.save_config()
        except Exception as e:
            logger.warning(f"[定时问候] 保存配置失败: {e}")

        yield event.plain_result(
            f"✅ 已将当前会话从问候列表移除\n"
            f"现在共有 {len(targets)} 个目标会话"
        )

    @filter.command("greet_list")
    async def greet_list(self, event: AstrMessageEvent):
        """查看当前问候配置"""
        enabled = self.config.get("enabled", True)
        targets = self.config.get("targets", [])

        lines = [
            "📋 定时问候配置",
            f"全局开关: {'✅ 开启' if enabled else '❌ 关闭'}",
            f"目标会话数: {len(targets)}",
            "",
        ]

        for gtype, gname in self.GREETING_TYPES.items():
            gconfig = self.config.get(gtype, {})
            g_enabled = gconfig.get("enabled", True)
            g_time = gconfig.get("time", "--:--")
            g_msgs = gconfig.get("messages", [])

            status = "✅" if g_enabled else "❌"
            lines.append(f"{status} {gname}")
            lines.append(f"   时间: {g_time}")
            lines.append(f"   问候语数: {len(g_msgs)}")
            lines.append("")

        yield event.plain_result("\n".join(lines))

    @filter.command("greet_test")
    async def greet_test(self, event: AstrMessageEvent):
        """测试发送一条问候到当前会话"""
        args = event.message_str.strip().split()
        gtype = None
        if len(args) > 1:
            keyword = args[1].lower()
            for k in self.GREETING_TYPES:
                if k in keyword or self.GREETING_TYPES[k].split(" ")[1] in args[1]:
                    gtype = k
                    break

        # 如果没指定或指定 all，就发全部
        if gtype is None:
            # 只发早安作为示例
            gtype = "morning"

        gconfig = self.config.get(gtype, {})
        messages = gconfig.get("messages", [])
        if not messages:
            yield event.plain_result(f"❌ {self.GREETING_TYPES.get(gtype, gtype)} 没有配置问候语")
            return

        greeting = random.choice(messages)
        gname = self.GREETING_TYPES.get(gtype, gtype)
        yield event.plain_result(f"🧪 测试发送 [{gname}]:\n\n{greeting}")

    # ==================== 生命周期 ====================

    async def terminate(self):
        """插件被卸载/停用时调用"""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[定时问候] 插件已停止")
