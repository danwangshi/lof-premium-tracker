# -*- coding: utf-8 -*-
"""
LOF场内份额自动抓取脚本
每天早上7点执行，从交易所获取最新份额数据并保存到数据库
非交易日如果获取不到数据则不保存
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
logger = logging.getLogger("auto-shares")

def fetch_and_save_shares():
    """
    获取并保存份额数据
    每天早上7点执行，查询前一天（T-1）的份额数据
    如果那天是非交易日，接口返回空数据，则不保存
    """
    logger.info("=" * 60)
    logger.info("开始执行份额自动抓取任务")
    logger.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    source = get_share_source()
    hdb = get_history_db()
    
    # 计算前一天的日期（T-1）
    yesterday = datetime.now() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    logger.info(f"目标查询日期: {target_date}（前一天）")
    
    # 1. 获取上交所数据 (SSE) - 指定日期
    try:
        logger.info(f"正在获取上交所(SSE)份额数据（日期: {target_date}）...")
        sse_data_list = source.fetch_sse_shares(max_pages=10, date=target_date)
        sse_map = {item['fund_code']: item for item in sse_data_list}
        logger.info(f"  SSE: 获取到 {len(sse_map)} 条数据")
    except Exception as e:
        logger.error(f"  SSE 获取失败: {e}")
        sse_map = {}

    # 2. 获取深交所数据 (SZSE) - 指定日期
    try:
        logger.info(f"正在获取深交所(SZSE)份额数据（日期: {target_date}）...")
        szse_data_list = source.fetch_szse_shares(date=target_date, max_pages=20)
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
    
    total_count = len(merged)
    logger.info(f"合并后共 {total_count} 条份额数据")
    
    # 4. 关键判断：如果获取到的数据为空，说明 target_date 是非交易日，不保存
    if total_count == 0:
        logger.warning(f"⚠️  {target_date} 未获取到任何份额数据，可能是非交易日，跳过保存")
        logger.info("任务结束")
        return False
    
    # 5. 有数据才保存（使用 target_date 作为保存日期）
    logger.info(f"✅ 获取到 {target_date} 的真实数据，准备保存到数据库...")
    try:
        hdb.save_shares_batch(merged, date=target_date)
        logger.info(f"✅ 成功保存 {total_count} 条份额记录到数据库（日期: {target_date}）")
        
        # 验证是否真的保存成功
        sample_code = list(merged.keys())[0] if merged else None
        if sample_code:
            latest = hdb.get_latest_shares(sample_code)
            if latest:
                logger.info(f"  验证示例: {sample_code} 最新份额日期={latest['date']}, 份额={latest['shares']}")
        
        logger.info("任务完成")
        return True
    except Exception as e:
        logger.error(f"❌ 保存失败: {e}")
        return False

if __name__ == '__main__':
    success = fetch_and_save_shares()
    sys.exit(0 if success else 1)
