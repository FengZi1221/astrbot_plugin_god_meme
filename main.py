import asyncio
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger, AstrBotConfig
from astrbot.core.star.filter.event_message_type import EventMessageType

import astrbot.api.message_components as Comp


@register("shen_meme", "FengZi", "神图：神 @某人 / 神 QQ号 自动生成图片", "1.0.2")
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

        target_name = await self._get_group_display_name(event, target_qq)

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
        try:
            for seg in (event.message_obj.message or []):
                if seg.__class__.__name__.lower() == "at" and hasattr(seg, "qq"):
                    qq = str(getattr(seg, "qq"))
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

    async def _get_group_display_name(self, event: AstrMessageEvent, target_qq: str) -> str:
        """
        优先：群名片(card) -> 昵称(nickname) -> QQ号兜底
        仅 aiocqhttp (OneBot v11) 在群聊里可用 get_group_member_info。:contentReference[oaicite:1]{index=1}
        """
        group_id = getattr(event.message_obj, "group_id", "") or ""
        if not group_id:
            return str(target_qq)

        try:
            if str(event.get_sender_id()) == str(target_qq):
                name = event.get_sender_name()
                if name:
                    return name
        except Exception:
            pass

        # 只在 aiocqhttp 平台调用 OneBot API
        if (getattr(event, "get_platform_name", None) and event.get_platform_name() != "aiocqhttp"):
            return str(target_qq)

        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            if not isinstance(event, AiocqhttpMessageEvent):
                return str(target_qq)

            client = event.bot  # aiocqhttp client
            payloads = {
                "group_id": int(group_id),
                "user_id": int(target_qq),
                "no_cache": True
            }
            ret = await client.api.call_action("get_group_member_info", **payloads)

            # OneBot 常见返回：{"status":"ok","data":{...}}
            data = None
            if isinstance(ret, dict):
                data = ret.get("data") or ret.get("result") or ret

            if isinstance(data, dict):
                card = (data.get("card") or "").strip()
                if card:
                    return card
                nickname = (data.get("nickname") or "").strip()
                if nickname:
                    return nickname
        except Exception as e:
            logger.warning(f"[shen_meme] get_group_member_info failed: {e}")

        return str(target_qq)

    async def _fetch_meme_bytes(self, qq: str, name: str) -> bytes:
        params = {"qq": str(qq), "name": str(name)}
        url = f"{self.api_base.rstrip('/')}/meme?{urlencode(params)}"
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._blocking_http_get, url)

    def _blocking_http_get(self, url: str) -> bytes:
        req = Request(url, headers={"User-Agent": "AstrBot-ShenMeme/1.0"})
        with urlopen(req, timeout=20) as resp:
            return resp.read()

    async def terminate(self):
        logger.info("[shen_meme] terminated.")
