#!/usr/bin/env python3
"""
补充历史份额数据脚本
从交易所 API 获取最近几天的份额数据并保存到数据库
"""

import sys
import os
from datetime import datetime, timedelta

# 添加 backend 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from datasource.share_source import ExchangeShareSource
from history_db import HistoryDB
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_previous_trading_days(days=3):
    """获取前 N 个交易日（简化版，跳过周末）"""
    trading_days = []
    today = datetime.now()
    
    # 从今天开始往前找
    check_date = today - timedelta(days=1)
    
    while len(trading_days) < days:
        # 跳过周末
        if check_date.weekday() < 5:  # 0-4 是周一到周五
            trading_days.append(check_date.strftime('%Y-%m-%d'))
        check_date -= timedelta(days=1)
    
    return trading_days


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始补充历史份额数据")
    logger.info("=" * 60)
    
    # 初始化
    share_source = ExchangeShareSource()
    hdb = HistoryDB()
    
    # 获取需要补充的日期（最近 3 个交易日）
    target_dates = get_previous_trading_days(days=3)
    logger.info(f"需要补充的日期: {target_dates}")
    
    for target_date in target_dates:
        logger.info(f"\n{'='*60}")
        logger.info(f"处理日期: {target_date}")
        logger.info(f"{'='*60}")
        
        try:
            # 获取该日期的份额数据
            logger.info(f"正在从交易所获取 {target_date} 的份额数据...")
            shares_data = share_source.fetch_all_shares(date=target_date)
            
            if not shares_data:
                logger.warning(f"⚠️  日期 {target_date} 未获取到数据")
                continue
            
            logger.info(f"✓ 获取到 {len(shares_data)} 条份额数据")
            
            # 保存到数据库
            saved_count = hdb.save_shares_batch(shares_data, date=target_date)
            logger.info(f"✓ 保存 {saved_count} 条数据到数据库")
            
        except Exception as e:
            logger.error(f"✗ 处理日期 {target_date} 失败: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # 统计结果
    logger.info(f"\n{'='*60}")
    logger.info("补充完成！")
    logger.info(f"{'='*60}")
    
    logger.info("\n✓ 所有操作完成！")


if __name__ == '__main__':
    main()
