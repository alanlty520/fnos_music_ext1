"""多排行榜歌单管理模块：支持酷狗与网易云热门榜单生成飞牛在线歌单。

提供 20 个酷狗榜单（TOP500、国潮音乐榜、网络热歌榜等）与 18 个网易云官方榜单
（飙升榜、新歌榜、古典榜、电音榜等），自动拉取、缓存并对齐飞牛前端数据格式。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

logger = logging.getLogger("fnmusic_proxy.charts")

CHART_GUID_PREFIX = "online:playlist:chart:"
DEFAULT_UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
DEFAULT_UA_PC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 酷狗音乐榜单列表（严格对齐主流热门排行榜）
KG_CHARTS: list[dict[str, Any]] = [
    {"id": "kg_8888", "name": "TOP500", "source": "kg", "rankid": 8888, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143249767677.png"},
    {"id": "kg_52144", "name": "国潮音乐榜", "source": "kg", "rankid": 52144, "cover": "https://imge.kugou.com/mcommon/400/20210929/20210929175404555896.png"},
    {"id": "kg_52767", "name": "视频号热歌酷狗榜", "source": "kg", "rankid": 52767, "cover": "https://imge.kugou.com/mcommon/400/20220112/20220112105954605929.png"},
    {"id": "kg_31313", "name": "民谣榜", "source": "kg", "rankid": 31313, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143615367389.png"},
    {"id": "kg_33161", "name": "纯音乐榜", "source": "kg", "rankid": 33161, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143627918342.png"},
    {"id": "kg_33162", "name": "电音榜", "source": "kg", "rankid": 33162, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143639943265.png"},
    {"id": "kg_23784", "name": "网络热歌榜", "source": "kg", "rankid": 23784, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143303648439.png"},
    {"id": "kg_6666", "name": "飙升榜", "source": "kg", "rankid": 6666, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143314995483.png"},
    {"id": "kg_52055", "name": "短视频热歌榜", "source": "kg", "rankid": 52055, "cover": "https://imge.kugou.com/mcommon/400/20210929/20210929175440620612.png"},
    {"id": "kg_46908", "name": "摇滚榜", "source": "kg", "rankid": 46908, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143715876542.png"},
    {"id": "kg_24971", "name": "DJ热歌榜", "source": "kg", "rankid": 24971, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143727938472.png"},
    {"id": "kg_54884", "name": "国乐榜", "source": "kg", "rankid": 54884, "cover": "https://imge.kugou.com/mcommon/400/20220926/20220926183354316719.png"},
    {"id": "kg_52054", "name": "百万收藏榜", "source": "kg", "rankid": 52054, "cover": "https://imge.kugou.com/mcommon/400/20210929/20210929175422894563.png"},
    {"id": "kg_59717", "name": "短视频收藏人气榜", "source": "kg", "rankid": 59717, "cover": "https://imge.kugou.com/mcommon/400/20230607/20230607172031123456.png"},
    {"id": "kg_24306", "name": "新歌榜", "source": "kg", "rankid": 24306, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143325674823.png"},
    {"id": "kg_52895", "name": "名品堂", "source": "kg", "rankid": 52895, "cover": "https://imge.kugou.com/mcommon/400/20220223/20220223164928123456.png"},
    {"id": "kg_31308", "name": "内地榜", "source": "kg", "rankid": 31308, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143415123456.png"},
    {"id": "kg_33163", "name": "粤语金曲榜", "source": "kg", "rankid": 33163, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143438123456.png"},
    {"id": "kg_31310", "name": "欧美榜", "source": "kg", "rankid": 31310, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143501123456.png"},
    {"id": "kg_30972", "name": "伤感榜", "source": "kg", "rankid": 30972, "cover": "https://imge.kugou.com/mcommon/400/20201208/20201208143524123456.png"},
]

# 网易云音乐榜单列表（严格对齐网易云官方 Toplist）
WY_CHARTS: list[dict[str, Any]] = [
    {"id": "wy_19723756", "name": "飙升榜", "source": "wy", "toplist_id": 19723756, "cover": "https://p1.music.126.net/pcYHpMkdStnvXZTzkVa-TmA==/109951166952713766.jpg"},
    {"id": "wy_3779629", "name": "新歌榜", "source": "wy", "toplist_id": 3779629, "cover": "https://p1.music.126.net/wVmyNSOnn_jhOPkiagllMw==/109951166952686384.jpg"},
    {"id": "wy_2884035", "name": "原创榜", "source": "wy", "toplist_id": 2884035, "cover": "https://p1.music.126.net/iFZ_nw2VaeK2UzsDH-winQ==/109951166961388699.jpg"},
    {"id": "wy_3778678", "name": "热歌榜", "source": "wy", "toplist_id": 3778678, "cover": "https://p1.music.126.net/GhhuF6Ep5Tmanih7Gt6Q==/109951166952688017.jpg"},
    {"id": "wy_71385702", "name": "网易云古典榜", "source": "wy", "toplist_id": 71385702, "cover": "https://p1.music.126.net/vctb1OSyD64x80p0_R112A==/109951168172715456.jpg"},
    {"id": "wy_1978921795", "name": "网易云电音榜", "source": "wy", "toplist_id": 1978921795, "cover": "https://p1.music.126.net/5405105260334812/109951168172728956.jpg"},
    {"id": "wy_991319590", "name": "网易云中文说唱榜", "source": "wy", "toplist_id": 991319590, "cover": "https://p1.music.126.net/3G2w7b_V0A27mY_bZ14A==/109951168172737890.jpg"},
    {"id": "wy_5338990334", "name": "实时分享榜", "source": "wy", "toplist_id": 5338990334, "cover": "https://p1.music.126.net/J0m0vP0-gUa3H-B7n8M8vw==/109951168172745678.jpg"},
    {"id": "wy_21845217", "name": "网易云全球说唱榜", "source": "wy", "toplist_id": 21845217, "cover": "https://p1.music.126.net/j_z3P6Vz0K4vQ9L7e0U_5A==/109951168172754321.jpg"},
    {"id": "wy_60198", "name": "潮流风向榜", "source": "wy", "toplist_id": 60198, "cover": "https://p1.music.126.net/G67_1K_8B7j7e5Q7E5y7A==/109951168172765432.jpg"},
    {"id": "wy_5059632704", "name": "音乐合伙人推荐榜", "source": "wy", "toplist_id": 5059632704, "cover": "https://p1.music.126.net/U9X7Xj1x8b0fG-X2-V3tqQ==/109951168172778901.jpg"},
    {"id": "wy_5059642708", "name": "音乐合伙人热歌榜", "source": "wy", "toplist_id": 5059642708, "cover": "https://p1.music.126.net/z8j7H6k5L4v3M2n1P0q9Rw==/109951168172789012.jpg"},
    {"id": "wy_5059644681", "name": "音乐合伙人留名榜", "source": "wy", "toplist_id": 5059644681, "cover": "https://p1.music.126.net/K3n4M5v6L7k8P9q0R1s2Tw==/109951168172790123.jpg"},
    {"id": "wy_5312894314", "name": "音乐合伙人高分新歌榜", "source": "wy", "toplist_id": 5312894314, "cover": "https://p1.music.126.net/P1q2R3s4T5u6V7w8X9y0Zw==/109951168172801234.jpg"},
    {"id": "wy_5312895267", "name": "音乐合伙人高分榜", "source": "wy", "toplist_id": 5312895267, "cover": "https://p1.music.126.net/A1b2C3d4E5f6G7h8I9j0Kw==/109951168172812345.jpg"},
    {"id": "wy_5453912201", "name": "黑胶VIP爱听榜", "source": "wy", "toplist_id": 5453912201, "cover": "https://p1.music.126.net/L1m2N3o4P5q6R7s8T9u0Vw==/109951168172823456.jpg"},
    {"id": "wy_71384707", "name": "网易云ACG榜", "source": "wy", "toplist_id": 71384707, "cover": "https://p1.music.126.net/W1x2Y3z4A5b6C7d8E9f0Gw==/109951168172834567.jpg"},
    {"id": "wy_745956260", "name": "网易云韩语榜", "source": "wy", "toplist_id": 745956260, "cover": "https://p1.music.126.net/H1i2J3k4L5m6N7o8P9q0Rw==/109951168172845678.jpg"},
]

ALL_CHARTS: list[dict[str, Any]] = KG_CHARTS + WY_CHARTS
_CHART_MAP: dict[str, dict[str, Any]] = {c["id"]: c for c in ALL_CHARTS}

# 内存快速缓存，避免高频并发重复拉取
_MEM_CACHE: dict[str, tuple[float, list[dict]]] = {}
_FETCH_LOCKS: dict[str, asyncio.Lock] = {}


def chart_guid(chart_id: str) -> str:
    return f"{CHART_GUID_PREFIX}{chart_id}"


def is_chart_guid(guid: str | None) -> bool:
    return bool(guid and str(guid).startswith(CHART_GUID_PREFIX))


def chart_id_from_guid(guid: str | None) -> str:
    s = str(guid or "")
    if s.startswith(CHART_GUID_PREFIX):
        return s[len(CHART_GUID_PREFIX):]
    return ""


def chart_meta(chart_id: str) -> dict[str, Any] | None:
    return _CHART_MAP.get(chart_id)


def _cache_dir() -> str:
    d = os.environ.get("FNMUSIC_RECOMMEND_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "recommend_cache"
    )
    chart_dir = os.path.join(d, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    return chart_dir


def _cache_file(chart_id: str, day: str) -> str:
    return os.path.join(_cache_dir(), f"{chart_id}_{day}.json")


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


_CHART_COVERS: dict[str, str] = {}


def load_chart_cache(chart_id: str, day: str) -> list[dict] | None:
    # 1. 查内存
    mem = _MEM_CACHE.get(chart_id)
    if mem:
        ts, data = mem
        # 缓存有效 4 小时
        if time.time() - ts < 14400 and data:
            return data

    # 2. 查本地文件
    path = _cache_file(chart_id, day)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                tracks = data.get("tracks") or []
                cov = data.get("cover")
                if cov:
                    _CHART_COVERS[chart_id] = str(cov)
                if tracks:
                    _MEM_CACHE[chart_id] = (time.time(), tracks)
                    return tracks
            elif isinstance(data, list) and data:
                _MEM_CACHE[chart_id] = (time.time(), data)
                return data
        except Exception as e:
            logger.warning("Failed to load chart cache from %s: %s", path, e)
    return None


def save_chart_cache(chart_id: str, day: str, tracks: list[dict], cover_url: str = "") -> None:
    _MEM_CACHE[chart_id] = (time.time(), tracks)
    if cover_url:
        _CHART_COVERS[chart_id] = cover_url
    path = _cache_file(chart_id, day)
    tmp_path = path + f".tmp.{os.getpid()}"
    try:
        payload = {"cover": cover_url, "tracks": tracks}
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception as e:
        logger.warning("Failed to save chart cache to %s: %s", path, e)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def get_chart_cover(chart_id: str) -> str:
    if chart_id in _CHART_COVERS and _CHART_COVERS[chart_id]:
        return _CHART_COVERS[chart_id]
    day = _today()
    tracks = load_chart_cache(chart_id, day)
    if chart_id in _CHART_COVERS and _CHART_COVERS[chart_id]:
        return _CHART_COVERS[chart_id]
    # 取第一首带封面的歌曲
    if tracks:
        for t in tracks:
            url = str(t.get("cover_url") or "")
            if url and "artistpicserver.kuwo.cn" not in url:
                _CHART_COVERS[chart_id] = url
                return url
    meta = chart_meta(chart_id) or {}
    return str(meta.get("cover") or "")


async def fetch_kg_chart(client: httpx.AsyncClient, rankid: int, limit: int = 100) -> tuple[list[dict], str]:
    """拉取酷狗音乐排行榜单歌曲与封面"""
    url = "http://m.kugou.com/rank/info/"
    params = {"rankid": rankid, "page": 1, "json": "true"}
    headers = {"User-Agent": DEFAULT_UA_MOBILE}
    try:
        r = await client.get(url, params=params, headers=headers, timeout=10.0)
        r.raise_for_status()
        res = r.json() or {}
        rows = (res.get("songs") or {}).get("list") or []
        info = res.get("info") or {}
        cover_url = str(info.get("banner_9") or info.get("banner_7") or info.get("imgurl") or "").replace("{size}", "400")
    except Exception as e:
        logger.warning("kg rank %s fetch failed: %s", rankid, e)
        return [], ""

    tracks: list[dict] = []
    for it in rows:
        if not isinstance(it, dict):
            continue
        fhash = str(it.get("hash") or "")
        if not fhash:
            continue
        authors = it.get("authors") or []
        singer = " / ".join(
            str(a.get("author_name") or "")
            for a in authors
            if isinstance(a, dict) and a.get("author_name")
        )
        title = str(it.get("songname") or it.get("filename") or "").replace(f"{singer} - ", "").strip()
        if not title:
            continue
        cover = str(it.get("album_sizable_cover") or "").replace("{size}", "480")
        tracks.append({
            "id": f"lx:kg:{fhash}",
            "source": "lx",
            "title": title,
            "artist": singer,
            "album": "",
            "duration_s": int(it.get("duration") or 0),
            "cover_url": cover,
            "ext": "mp3",
            "hash": fhash,
            "mixsongid": str(it.get("album_audio_id") or ""),
        })
        if len(tracks) >= limit:
            break
    if not cover_url and tracks:
        cover_url = tracks[0].get("cover_url") or ""
    return tracks, cover_url


async def fetch_wy_chart(
    client: httpx.AsyncClient,
    toplist_id: int,
    netease_enabled: bool = False,
    limit: int = 100
) -> tuple[list[dict], str]:
    """拉取网易云音乐排行榜单歌曲与封面"""
    url = "https://music.163.com/api/playlist/detail"
    params = {"id": toplist_id}
    headers = {
        "User-Agent": DEFAULT_UA_PC,
        "Referer": "https://music.163.com/",
        "Cookie": "os=pc; appver=9.1.15",
    }
    try:
        r = await client.get(url, params=params, headers=headers, timeout=12.0)
        r.raise_for_status()
        res = r.json() or {}
        result = res.get("result") or res.get("playlist") or {}
        tracks_data = result.get("tracks") or []
        cover_url = str(result.get("coverImgUrl") or result.get("picUrl") or "")
    except Exception as e:
        logger.warning("wy toplist %s fetch failed: %s", toplist_id, e)
        return [], ""

    tracks: list[dict] = []
    source = "netease" if netease_enabled else "lx"
    for it in tracks_data:
        if not isinstance(it, dict):
            continue
        sid = str(it.get("id") or "")
        if not sid:
            continue
        title = str(it.get("name") or "").strip()
        artists = it.get("artists") or it.get("ar") or []
        artist = " / ".join(str(a.get("name") or "") for a in artists if isinstance(a, dict))
        album_data = it.get("album") or it.get("al") or {}
        album = str(album_data.get("name") or "") if isinstance(album_data, dict) else ""
        cover = str(album_data.get("picUrl") or "") if isinstance(album_data, dict) else ""
        duration_ms = it.get("duration") or it.get("dt") or 0

        item_id = sid if netease_enabled else f"lx:wy:{sid}"
        tracks.append({
            "id": item_id,
            "source": source,
            "title": title,
            "artist": artist,
            "album": album,
            "duration_s": float(duration_ms) / 1000.0,
            "cover_url": cover,
            "ext": "mp3",
            "song_id": sid,
        })
        if len(tracks) >= limit:
            break
    if not cover_url and tracks:
        cover_url = tracks[0].get("cover_url") or ""
    return tracks, cover_url


async def get_or_load_chart_tracks(
    chart_id: str,
    client: httpx.AsyncClient | None = None,
    netease_enabled: bool = False,
    limit: int = 100
) -> list[dict]:
    """获取指定榜单的歌曲列表（优先缓存，无则抓取并落盘）"""
    meta = chart_meta(chart_id)
    if not meta:
        return []

    day = _today()
    cached = load_chart_cache(chart_id, day)
    if cached:
        return cached

    lock = _FETCH_LOCKS.setdefault(chart_id, asyncio.Lock())
    async with lock:
        cached = load_chart_cache(chart_id, day)
        if cached:
            return cached

        owned_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
            owned_client = True
        try:
            tracks: list[dict] = []
            cover_url = ""
            if meta["source"] == "kg":
                tracks, cover_url = await fetch_kg_chart(client, meta["rankid"], limit=limit)
            elif meta["source"] == "wy":
                tracks, cover_url = await fetch_wy_chart(client, meta["toplist_id"], netease_enabled=netease_enabled, limit=limit)

            if tracks:
                save_chart_cache(chart_id, day, tracks, cover_url=cover_url)
            return tracks
        finally:
            if owned_client:
                await client.aclose()


def build_chart_playlist_record(chart_id: str, track_count: int = 0) -> dict[str, Any]:
    """构造飞牛前端所需的歌单元数据"""
    meta = chart_meta(chart_id) or {"name": "排行榜", "cover": ""}
    guid = chart_guid(chart_id)
    now = int(time.time())
    name = meta.get("name") or "排行榜"
    cover_url = get_chart_cover(chart_id)
    fake_id = hashlib.md5(f"fnmusic-ext::{guid}".encode()).hexdigest()
    return {
        "guid": guid,
        "name": name,
        "title": name,
        "coverUrl": cover_url,
        "coverId": f"track_{fake_id}",
        "createdAt": now,
        "updatedAt": now,
        "trackCount": track_count or 100,
        "isDaily": True,
    }


def list_enabled_charts(
    enable_charts: bool = True,
    enable_kg: bool = True,
    enable_wy: bool = True,
    custom_whitelist: "str | list[str] | set[str] | None" = None,
) -> list[dict[str, Any]]:
    """根据开关配置和自定义白名单返回要注入的榜单列表"""
    if not enable_charts:
        return []
    res: list[dict[str, Any]] = []
    if enable_kg:
        res.extend(KG_CHARTS)
    if enable_wy:
        res.extend(WY_CHARTS)

    wl_raw = custom_whitelist if custom_whitelist is not None else os.environ.get("FNMUSIC_ENABLED_CHARTS", "")
    if isinstance(wl_raw, str):
        wl = {x.strip() for x in wl_raw.split(",") if x.strip()}
    elif isinstance(wl_raw, (list, set)):
        wl = {str(x).strip() for x in wl_raw if str(x).strip()}
    else:
        wl = set()

    if wl:
        res = [c for c in res if c["id"] in wl]
    return res
