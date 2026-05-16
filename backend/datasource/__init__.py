# -*- coding: utf-8 -*-
"""
数据源插件包
"""
from datasource.base import LOFDataSource
from datasource.legacy import LegacySource
from datasource.ak_share import AkShareSource
from datasource.share_source import ExchangeShareSource
from datasource.manager import DataSourceManager, get_datasource_manager

__all__ = [
    "LOFDataSource",
    "LegacySource",
    "AkShareSource",
    "ExchangeShareSource",  # 注意：这不是 LOFDataSource 子类，是独立的份额数据源
    "DataSourceManager",
    "get_datasource_manager",
]
