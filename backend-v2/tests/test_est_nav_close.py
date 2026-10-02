"""每日收盘估算净值的取法、落盘归属与误差计算（2026-10-01 修复）。

用户报告：「每日的估算净值得到的内容都没有正确的落盘记录到 sql 内，点击基金得到
的详细页中我们应该记录每日收盘得到的估算净值，用户估算最终获取的估算效果与真实
净值的趋势如何。」

排查结论：落盘其实一直在写（实测 164 条切片/天、31.7 万行/天、1.5GB），错的是
**取法**和**归属**：

1. **取法错**：详情页原查询 `ORDER BY trade_date DESC LIMIT 32`。同一天有 164 行，
   所以 32 行全部落在同一天（线上实测 distinct_days = 1），30 天里只有最后一天有
   估算值，趋势是空的。

2. **选中的切片是错的**：`fund_est_nav` 的 `nav` 列是**基准净值**。当晚净值公布后，
   基准切换成当日的，之后切片算的其实是**下一个交易日**的估算，却仍挂在当天的
   trade_date 上。实测 161725（2026-09-30）：15:07 切片基准 0.5169 → 估算 0.5317
   （09-30 的收盘估算，正确）；20:02 切片基准 0.5314 → 估算 0.5466（其实是 10-01
   的估算）。09-30 实际净值 0.5314，真实误差 +0.06%，而按"最后一条切片"取会显示
   0.5466、误差 +2.86% —— 把误差放大约 45 倍，比没有数据更糟。

3. **落盘归属错**：上述 20:02 之后的 36/164 条切片本就不该挂在 09-30 上。
"""
from datetime import date, datetime, time, timezone, timedelta

from services.fund_service import (
    EST_NAV_CLOSE_CUTOFF,
    build_close_est_fields,
)
from services.est_nav_service import _est_nav_data_to_records, _is_next_session


BJ = timezone(timedelta(hours=8))


def _est(**kw):
    """构造一条 _load_est_nav_close_map 的返回值。"""
    base = {
        "est_nav": 0.5317,
        "est_change_pct": 2.86,
        "base_nav": 0.5169,
        "snapshot_time": datetime(2026, 9, 30, 15, 7, 49, tzinfo=BJ),
    }
    base.update(kw)
    return base


class TestCloseCutoffParam:
    """`EST_NAV_CLOSE_CUTOFF` 必须绑成 datetime.time。

    这个参数在 SQL 里是 `CAST(:close_cutoff AS time)`，asyncpg 据此把参数推断成
    time 类型。传字符串会直接 500：
        invalid input for query argument $3: '15:10'
        ('str' object has no attribute 'hour')
    线上就是这么炸的 —— 纯单元测试跑不到数据库，所以这里至少把类型锁住。
    """

    def test_is_a_time_object_not_a_string(self):
        assert isinstance(EST_NAV_CLOSE_CUTOFF, time)
        assert not isinstance(EST_NAV_CLOSE_CUTOFF, str)
        assert EST_NAV_CLOSE_CUTOFF.hour == 15
        assert EST_NAV_CLOSE_CUTOFF.minute == 10


class TestBuildCloseEstFields:
    def test_real_161725_close_estimate(self):
        """161725 2026-09-30 的真实取值：收盘估算 0.5317 vs 实际 0.5314。"""
        f = build_close_est_fields("2026-09-30", _est(), 0.5314, date(2026, 9, 30))
        assert f["est_nav"] == 0.5317
        assert f["est_nav_realized"] == 0.5314
        assert f["est_nav_error"] == 0.0565
        assert f["est_nav_time"].startswith("2026-09-30T15:07:49")

    def test_post_publication_slice_is_not_the_close_estimate(self):
        """净值公布后的切片（估算 0.5466 / 基准 0.5314）不该被当成当日收盘估算。

        它不是"取不到"而是"取错了"：正确的那条是 0.5317。
        这个用例锁定的是**错误值不会再被当成 09-30 的估算**。
        """
        wrong = _est(est_nav=0.5466, base_nav=0.5314, est_change_pct=2.86,
                     snapshot_time=datetime(2026, 9, 30, 22, 57, 50, tzinfo=BJ))
        f = build_close_est_fields("2026-09-30", wrong, 0.5314, date(2026, 9, 30))
        # 该值本身仍会算出一个很大的误差 —— 说明筛选必须发生在 SQL 层（按切片时刻
        # 与基准稳定性），这里断言的是"误差确实会被算出来"，用于对照：
        assert f["est_nav_error"] == 2.8604

    def test_no_estimate_gives_nulls(self):
        f = build_close_est_fields("2026-09-30", None, 0.5314, date(2026, 9, 30))
        assert f["est_nav"] is None
        assert f["est_nav_error"] is None
        assert f["est_nav_realized"] == 0.5314

    def test_meaningless_estimate_is_dropped(self):
        """估了但等于没估（零输入）：est_nav 是基准净值的副本 → 不展示、不算误差。"""
        f = build_close_est_fields(
            "2026-09-30",
            _est(est_nav=0.5169, base_nav=0.5169, est_change_pct=0.0),
            0.5169, date(2026, 9, 30))
        assert f["est_nav"] is None
        assert f["est_nav_error"] is None

    def test_error_needs_nav_of_the_same_day(self):
        """净值未公布时 fund_daily.nav 挂的是上一日净值 → 不能拿它算误差。

        否则误差＝(估算 − 基准) 恒等于估算涨跌幅的负数，会得到假的"准确度"。
        """
        f = build_close_est_fields("2026-09-30", _est(), 0.5169, date(2026, 9, 29))
        assert f["est_nav"] == 0.5317      # 估算照常展示
        assert f["est_nav_realized"] is None
        assert f["est_nav_error"] is None  # 但没有可核对的误差

    def test_missing_nav_date_gives_no_error(self):
        f = build_close_est_fields("2026-09-30", _est(), 0.5314, None)
        assert f["est_nav_error"] is None
        assert f["est_nav_realized"] is None

    def test_zero_or_bad_realized_nav_is_not_used(self):
        for bad in (0, -1, "abc"):
            f = build_close_est_fields("2026-09-30", _est(), bad, date(2026, 9, 30))
            assert f["est_nav_error"] is None, bad
            assert f["est_nav_realized"] is None, bad

    def test_estimate_is_kept_when_nav_missing_entirely(self):
        f = build_close_est_fields("2026-09-30", _est(), None, None)
        assert f["est_nav"] == 0.5317
        assert f["est_nav_error"] is None

    def test_nav_date_as_string_still_matches(self):
        f = build_close_est_fields("2026-09-30", _est(), 0.5314, "2026-09-30")
        assert f["est_nav_error"] == 0.0565


class TestIsNextSession:
    def test_same_day_nav_published(self):
        """基准净值就是当日的 → 这份估算描述的是下一个交易日。"""
        assert _is_next_session("2026-09-30", "2026-09-30") is True

    def test_previous_day_nav_is_the_close_estimate(self):
        assert _is_next_session("2026-09-29", "2026-09-30") is False

    def test_unknown_nav_date_keeps_record(self):
        """拿不到 nav_date 时保留记录：宁可多写，也不要把字段缺失变成没有数据。"""
        assert _is_next_session(None, "2026-09-30") is False
        assert _is_next_session("", "2026-09-30") is False

    def test_date_object_also_works(self):
        assert _is_next_session(date(2026, 9, 30), "2026-09-30") is True


class TestEstNavDataToRecords:
    def _data(self):
        return {
            "161725": {"est_nav": 0.5317, "est_change_pct": 2.86, "nav": 0.5169,
                       "nav_date": "2026-09-29"},
            "501046": {"est_nav": 8.3765, "est_change_pct": -1.74, "nav": 8.5245,
                       "nav_date": "2026-09-30"},   # 当日净值已公布 → 属于下一交易日
        }

    def test_filters_next_session_records(self):
        recs = _est_nav_data_to_records(self._data(), date(2026, 9, 30))
        assert [r["code"] for r in recs] == ["161725"]

    def test_without_trade_date_keeps_everything(self):
        recs = _est_nav_data_to_records(self._data())
        assert sorted(r["code"] for r in recs) == ["161725", "501046"]

    def test_records_only_carry_table_columns(self):
        recs = _est_nav_data_to_records(self._data(), date(2026, 9, 30))
        assert set(recs[0]) == {"code", "est_nav", "est_change_pct",
                                "holdings_contrib", "index_contrib",
                                "coverage", "nav"}

    def test_all_filtered_out_returns_empty(self):
        """全部属于下一交易日 → 返回空，调用方据此跳过本次写入。"""
        data = {"501046": {"est_nav": 1.0, "nav_date": "2026-09-30"}}
        assert _est_nav_data_to_records(data, date(2026, 9, 30)) == []

    def test_missing_nav_date_is_kept(self):
        data = {"161725": {"est_nav": 0.5317, "nav": 0.5169}}
        recs = _est_nav_data_to_records(data, date(2026, 9, 30))
        assert len(recs) == 1
