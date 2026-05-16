# -*- coding: utf-8 -*-
"""
份额历史数据补填脚本
用于获取并存储最近两个交易日的场内份额数据，以便计算“新增份额”
"""
import os
import sys
import logging
from datetime import datetime, timedelta

# 添加 backend 目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datasource.share_source import get_share_source
from history_db import get_history_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("seed-shares")

def get_previous_trading_days(n=2):
    """
    简单估算前 n 个交易日（跳过周末）
    注意：这不考虑法定节假日，但在实际生产中，交易所 API 
    如果查询非交易日通常会返回空或最近一个交易日的数据。
    """
    days = []
    d = datetime.now()
    while len(days) < n:
        d -= timedelta(days=1)
        # 0=Monday, 6=Sunday
        if d.weekday() < 5: 
            days.append(d.strftime('%Y-%m-%d'))
    return days

def main():
    logger.info("开始补填份额历史数据...")
    
    source = get_share_source()
    hdb = get_history_db()
    
    # 获取前两个交易日日期
    target_dates = get_previous_trading_days(2)
    logger.info(f"目标日期: {target_dates}")
    
    for date_str in target_dates:
        logger.info(f"正在处理日期: {date_str}")
        
        # 1. 获取上交所数据 (SSE)
        try:
            sse_data_list = source.fetch_sse_shares(max_pages=10, date=date_str)
            sse_map = {item['fund_code']: item for item in sse_data_list}
            logger.info(f"  SSE: 获取到 {len(sse_map)} 条数据")
        except Exception as e:
            logger.error(f"  SSE 获取失败: {e}")
            sse_map = {}

        # 2. 获取深交所数据 (SZSE)
        try:
            szse_data_list = source.fetch_szse_shares(date=date_str, max_pages=20)
            szse_map = {item['fund_code']: item for item in szse_data_list}
            logger.info(f"  SZSE: 获取到 {len(szse_map)} 条数据")
        except Exception as e:
            logger.error(f"  SZSE 获取失败: {e}")
            szse_map = {}

        # 3. 合并数据
        merged = {}
        merged.update(sse_map)
        for code, item in szse_map.items():
            if code not in merged or item['date'] >= merged[code]['date']:
                merged[code] = item
        
        if merged:
            # 4. 存入数据库
            hdb.save_shares_batch(merged, date=date_str)
            logger.info(f"  已保存 {len(merged)} 条份额记录到数据库")
        else:
            logger.warning(f"  日期 {date_str} 未获取到任何有效数据")

    logger.info("份额历史数据补填完成！")

if __name__ == '__main__':
    main()
