import asyncio
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger, AstrBotConfig
from astrbot.core.star.filter.event_message_type import EventMessageType

import astrbot.api.message_components as Comp


@register("shen_meme", "FengZi", "神图：神 @某人 / 神 QQ号 自动生成图片", "1.0.4")
class ShenMemePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None, **kwargs):
        super().__init__(context)
        self.config = config

        self.api_base = "http://47.105.107.105:8000"
        if self.config:
            self.api_base = self.config.get("shen_api_base_url", self.api_base)

        self.data_dir = StarTools.get_data_dir("shen_meme")
        self.tmp_dir = self.data_dir / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[shen_meme] loaded. api_base={self.api_base}")

    @filter.event_message_type(EventMessageType.ALL, priority=100)
    async def on_any_message(self, event: AstrMessageEvent):
        if str(event.get_sender_id()) == str(event.get_self_id()):
            return

        text = (event.get_message_str() or "").strip()
        if not text.startswith("神"):
            return

        target_qq = self._extract_target_qq(event, text)
        if not target_qq:
            yield event.plain_result("用法：神 @某人  或  神 12345678")
            return

        group_id = getattr(event.message_obj, "group_id", "") or ""

        # ✅ 关键：拿 QQ 昵称 nickname（拿不到才回退为 QQ 号）
        target_name = await self._get_qq_nickname(event, target_qq, group_id=group_id)

        logger.info(
            f"[shen_meme] platform={getattr(event, 'get_platform_name', lambda: '')() if hasattr(event,'get_platform_name') else ''} "
            f"group_id={group_id} target_qq={target_qq} target_name={target_name}"
        )

        try:
            img_bytes = await self._fetch_meme_bytes(target_qq, target_name)
        except Exception as e:
            logger.exception(e)
            yield event.plain_result(f"生成失败：{e}")
            return

        out_path = self.tmp_dir / f"shen_{target_qq}_{int(time.time())}.png"
        out_path.write_bytes(img_bytes)

        res = event.chain_result([Comp.Image.fromFileSystem(str(out_path))])
        res.stop_event()
        yield res

    def _extract_target_qq(self, event: AstrMessageEvent, text: str):
        """
        支持：
          - 消息段里的 At
          - [At:123]
          - [CQ:at,qq=123]
          - 神 123456
        """
        try:
            for seg in (event.message_obj.message or []):
                if seg.__class__.__name__.lower() == "at":
                    # 常见字段：qq / user_id / target
                    for k in ("qq", "user_id", "target"):
                        if hasattr(seg, k):
                            qq = str(getattr(seg, k))
                            if qq.isdigit():
                                return qq
        except Exception:
            pass

        m = re.search(r"\[At:(\d+)\]", text)
        if m:
            return m.group(1)

        m = re.search(r"\[CQ:at,qq=(\d+)\]", text)
        if m:
            return m.group(1)

        m = re.match(r"^神\s*([0-9]{5,12})\s*$", text)
        if m:
            return m.group(1)

        return None

    def _get_call_action(self, event: AstrMessageEvent):
        """
        尽量从 event / bot 里找到 OneBot 的 call_action 能力。
        找不到就返回 None。
        """
        bot = getattr(event, "bot", None)
        if bot is None:
            return None

        api = getattr(bot, "api", None)
        if api is not None and hasattr(api, "call_action"):
            return api.call_action

        # 有些实现直接挂在 bot 上
        if hasattr(bot, "call_action"):
            return bot.call_action

        return None

    def _extract_data(self, ret):
        """
        兼容各种返回格式：{"data":...} / {"result":...} / 直接就是 data
        """
        if not isinstance(ret, dict):
            return None
        return ret.get("data") or ret.get("result") or ret.get("response") or ret

    async def _get_qq_nickname(self, event: AstrMessageEvent, target_qq: str, group_id: str = "") -> str:
        """
        只要底层能 call_action，就去取：
          1) get_group_member_info -> nickname
          2) get_stranger_info -> nickname
        都失败才返回 QQ号。

        ✅ 不再强行判断平台名/事件类型，避免你现在这种“永远兜底”的情况。
        """
        call_action = self._get_call_action(event)
        if call_action is None:
            return str(target_qq)

        # 1) 群内优先
        if group_id:
            try:
                ret = await call_action(
                    "get_group_member_info",
                    group_id=int(group_id),
                    user_id=int(target_qq),
                    no_cache=True,
                )
                data = self._extract_data(ret)
                if isinstance(data, dict):
                    nickname = (data.get("nickname") or "").strip()
                    if nickname:
                        return nickname
            except Exception as e:
                logger.warning(f"[shen_meme] get_group_member_info failed: {e}")

        # 2) 兜底：陌生人信息
        try:
            ret = await call_action(
                "get_stranger_info",
                user_id=int(target_qq),
                no_cache=True,
            )
            data = self._extract_data(ret)
            if isinstance(data, dict):
                nickname = (data.get("nickname") or "").strip()
                if nickname:
                    return nickname
        except Exception as e:
            logger.warning(f"[shen_meme] get_stranger_info failed: {e}")

        return str(target_qq)

    async def _fetch_meme_bytes(self, qq: str, name: str) -> bytes:
        # ✅ urlencode 用 utf-8，emoji 不会丢
        qs = urlencode({"qq": str(qq), "name": str(name)}, encoding="utf-8")
        url = f"{self.api_base.rstrip('/')}/meme?{qs}"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._blocking_http_get, url)

    def _blocking_http_get(self, url: str) -> bytes:
        req = Request(url, headers={"User-Agent": "AstrBot-ShenMeme/1.0"})
        with urlopen(req, timeout=20) as resp:
            return resp.read()

    async def terminate(self):
        logger.info("[shen_meme] terminated.")
