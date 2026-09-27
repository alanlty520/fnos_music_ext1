"""charts.py 单元测试：测试多排行榜歌单元数据、缓存与接口兼容。"""
import os
import tempfile
import unittest

from proxy import charts
from proxy import recommend as dailyrec


class TestCharts(unittest.TestCase):
    def test_charts_list(self):
        # 验证酷狗榜单 20 个，网易云榜单 18 个，共 38 个
        self.assertEqual(len(charts.KG_CHARTS), 20)
        self.assertEqual(len(charts.WY_CHARTS), 18)
        self.assertEqual(len(charts.ALL_CHARTS), 38)

        # 检查开关过滤
        all_enabled = charts.list_enabled_charts(True, True, True)
        self.assertEqual(len(all_enabled), 38)

        kg_only = charts.list_enabled_charts(True, True, False)
        self.assertEqual(len(kg_only), 20)

        wy_only = charts.list_enabled_charts(True, False, True)
        self.assertEqual(len(wy_only), 18)

        none_enabled = charts.list_enabled_charts(False, True, True)
        self.assertEqual(len(none_enabled), 0)

        # 检查自定义白名单过滤
        custom_enabled = charts.list_enabled_charts(True, True, True, custom_whitelist="kg_8888,wy_19723756")
        self.assertEqual(len(custom_enabled), 2)
        self.assertEqual({c["id"] for c in custom_enabled}, {"kg_8888", "wy_19723756"})

    def test_guid_helpers(self):
        guid = charts.chart_guid("kg_8888")
        self.assertEqual(guid, "online:playlist:chart:kg_8888")
        self.assertTrue(charts.is_chart_guid(guid))
        self.assertEqual(charts.chart_id_from_guid(guid), "kg_8888")
        self.assertFalse(charts.is_chart_guid("online:playlist:daily:20260927"))

        # 验证 recommend.py 中的兼容
        self.assertEqual(dailyrec.online_playlist_kind(guid), "chart")
        self.assertTrue(dailyrec.is_recommend_playlist_guid(guid))

    def test_build_record(self):
        rec = charts.build_chart_playlist_record("kg_8888", track_count=50)
        self.assertEqual(rec["name"], "TOP500")
        self.assertEqual(rec["title"], "TOP500")
        self.assertEqual(rec["trackCount"], 50)
        self.assertTrue(rec["isDaily"])
        self.assertTrue(rec["coverId"].startswith("track_"))

        rec_wy = charts.build_chart_playlist_record("wy_19723756", track_count=100)
        self.assertEqual(rec_wy["name"], "飙升榜")
        self.assertEqual(rec_wy["title"], "飙升榜")
        self.assertEqual(rec_wy["trackCount"], 100)
        self.assertTrue(rec_wy["coverId"].startswith("track_"))

    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_dir = os.environ.get("FNMUSIC_RECOMMEND_DIR")
            os.environ["FNMUSIC_RECOMMEND_DIR"] = tmpdir
            try:
                test_tracks = [
                    {"id": "lx:kg:abc", "title": "测试歌曲", "artist": "测试歌手", "duration_s": 180}
                ]
                charts.save_chart_cache("kg_test", "20260927", test_tracks)
                loaded = charts.load_chart_cache("kg_test", "20260927")
                self.assertIsNotNone(loaded)
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0]["title"], "测试歌曲")
            finally:
                if old_dir is not None:
                    os.environ["FNMUSIC_RECOMMEND_DIR"] = old_dir
                else:
                    os.environ.pop("FNMUSIC_RECOMMEND_DIR", None)

    def test_find_track_and_cover(self):
        sample_tracks = [
            {
                "id": "lx:wy:12345678",
                "source": "lx",
                "title": "开始懂了",
                "artist": "孙燕姿",
                "album": "我要的幸福",
                "cover_url": "https://p1.music.126.net/sample.jpg",
                "duration_s": 271,
            }
        ]
        charts.save_chart_cache("wy_5453912201", charts._today(), sample_tracks, cover_url="https://p1.music.126.net/header.jpg")
        
        # 测试根据 online guid 和原始 id 查找
        found = charts.find_track("online:lx:wy:12345678")
        self.assertIsNotNone(found)
        self.assertEqual(found["title"], "开始懂了")
        self.assertEqual(found["cover_url"], "https://p1.music.126.net/sample.jpg")

        # 测试榜单封面获取
        cover = charts.get_chart_cover("wy_5453912201")
        self.assertEqual(cover, "https://p1.music.126.net/header.jpg")

        # 测试无效 dummy 封面识别
        self.assertTrue(charts._is_dummy_cover("https://p1.music.126.net/L1m2N3o4P5q6R7s8T9u0Vw==/109951168172823456.jpg"))
        self.assertTrue(charts._is_dummy_cover("https://imge.kugou.com/mcommon/400/20230607/20230607172031123456.png"))
        self.assertFalse(charts._is_dummy_cover("https://p1.music.126.net/pcYHpMkdStnvXZTzkVa-TmA==/109951166952713766.jpg"))


if __name__ == "__main__":
    unittest.main()
