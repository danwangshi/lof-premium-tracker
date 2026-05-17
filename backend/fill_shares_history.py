#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
填充前三个交易日的基金份额数据
从交易所接口读取真实数据并保存到 fund_shares 表
"""

import sys
import os
from datetime import datetime, timedelta

# 添加 backend 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from datasource.share_source import ExchangeShareSource
from history_db import get_history_db
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger('fill_shares')


def get_previous_trading_dates(days=3):
    """
    获取前 N 个交易日（简单实现：跳过周末）
    
    Args:
        days: 需要获取的天数
    
    Returns:
        日期列表，格式: ['2026-05-15', '2026-05-14', ...]
    """
    dates = []
    current = datetime.now()
    
    while len(dates) < days:
        current -= timedelta(days=1)
        # 跳过周末 (5=Saturday, 6=Sunday)
        if current.weekday() < 5:
            dates.append(current.strftime('%Y-%m-%d'))
    
    return dates


def fill_shares_for_dates(dates):
    """
    为指定日期填充份额数据
    
    Args:
        dates: 日期列表
    """
    source = ExchangeShareSource()
    hdb = get_history_db()
    
    total_saved = 0
    
    for date in dates:
        logger.info(f"开始获取 {date} 的份额数据...")
        
        try:
            # 从交易所获取该日期的份额数据
            shares_data = source.fetch_all_shares(date=date)
            
            if not shares_data:
                logger.warning(f"{date} 没有获取到份额数据")
                continue
            
            logger.info(f"{date} 获取到 {len(shares_data)} 只基金的份额数据")
            
            # 保存到数据库
            hdb.save_shares_batch(shares_data, date=date)
            total_saved += len(shares_data)
            
            logger.info(f"✓ {date} 保存成功，共 {len(shares_data)} 条记录")
            
        except Exception as e:
            logger.error(f"处理 {date} 时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            continue
    
    logger.info(f"\n{'='*60}")
    logger.info(f"完成！共保存 {total_saved} 条份额记录")
    logger.info(f"{'='*60}")


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始填充前三个交易日的份额数据")
    logger.info("=" * 60)
    
    # 获取前三个交易日
    dates = get_previous_trading_dates(days=3)
    logger.info(f"目标日期: {dates}")
    
    # 填充数据
    fill_shares_for_dates(dates)
    
    logger.info("\n任务完成！")


if __name__ == '__main__':
    main()
