"""缓存的降级行为：失败要可见，而不是静默。

2026-10-02 排查估算净值时踩到的：`cache_set` 原来是 `except Exception: pass`，
任何写入失败都没有任何痕迹。两个真实后果：

1. `est_nav:v2`（2.4MB，整个键空间里最大的键）被 Redis 的 allkeys-lru 淘汰后，
   页面上的估算净值整列变成 `--`，日志里一个字都没有 —— 而它的 TTL 明明写着
   72 小时，注释还说"覆盖周末及长假，非交易时段仍可查看最近估算值"。
2. 我自己的排查脚本忘了先 `init_redis`，`_pool` 为 None，写缓存"成功"了、
   回读是 None —— 探针自己的 bug 被伪装成"Redis 写不进去"，差点误判成产品缺陷。

所以 `cache_set` 现在返回 bool，并记录失败原因。
"""
import asyncio

import cache as cachemod


class _BadPool:
    """任何写入都失败的假连接池。"""

    async def set(self, *a, **kw):
        raise ConnectionError("connection refused")

    async def get(self, *a, **kw):
        raise ConnectionError("connection refused")


def _set(*a, **kw):
    return asyncio.run(cachemod.cache_set(*a, **kw))


class TestCacheSetReportsFailure:
    def test_not_initialized_returns_false(self, monkeypatch):
        """忘了 init_redis → 必须返回 False，不能假装写成功。"""
        monkeypatch.setattr(cachemod, "_pool", None)
        assert _set("k", {"a": 1}, ttl=60) is False

    def test_redis_error_returns_false(self, monkeypatch):
        monkeypatch.setattr(cachemod, "_pool", _BadPool())
        assert _set("k", {"a": 1}, ttl=60) is False

    def test_failure_is_logged(self, monkeypatch, caplog):
        """失败必须留下日志 —— 这次事故就是"什么都没记"才拖了很久。"""
        monkeypatch.setattr(cachemod, "_pool", None)
        with caplog.at_level("WARNING"):
            _set("est_nav:v2", {}, ttl=60)
        assert any("est_nav:v2" in r.message or "est_nav:v2" in str(r.args)
                   for r in caplog.records), caplog.text

    def test_never_raises(self, monkeypatch):
        """降级是设计目标：缓存坏了不能把业务请求带崩。"""
        monkeypatch.setattr(cachemod, "_pool", _BadPool())
        assert _set("k", {"a": 1}, ttl=60) is False  # 不抛异常即为通过


class TestCacheSetSuccess:
    def test_returns_true_on_success(self, monkeypatch):
        written = {}

        class _OkPool:
            async def set(self, key, payload, ex=None):
                written[key] = (payload, ex)
                return True

        monkeypatch.setattr(cachemod, "_pool", _OkPool())
        assert _set("k", {"a": 1}, ttl=60) is True
        assert "k" in written
        assert written["k"][1] == 60
