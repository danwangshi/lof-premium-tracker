# -*- coding: utf-8 -*-
"""
测试交易所份额数据获取功能
"""
import sys
import os
import logging

# 添加 backend 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from datasource.share_source import get_share_source
from history_db import get_history_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger('test-shares')


def test_fetch_shares():
    """测试获取份额数据"""
    logger.info("=" * 80)
    logger.info("测试交易所份额数据获取")
    logger.info("=" * 80)
    
    client = get_share_source()
    
    # 测试上交所
    logger.info("\n【1】测试上交所数据获取...")
    try:
        sse_data = client.fetch_sse_shares(max_pages=2)
        logger.info(f"获取到 {len(sse_data)} 条上交所数据")
        if sse_data:
            logger.info(f"示例: {sse_data[0]}")
    except Exception as e:
        logger.error(f"上交所数据获取失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # 测试深交所
    logger.info("\n【2】测试深交所数据获取...")
    try:
        szse_data = client.fetch_szse_shares(max_pages=2)
        logger.info(f"获取到 {len(szse_data)} 条深交所数据")
        if szse_data:
            logger.info(f"示例: {szse_data[0]}")
    except Exception as e:
        logger.error(f"深交所数据获取失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # 测试合并数据
    logger.info("\n【3】测试合并数据...")
    try:
        all_shares = client.fetch_all_shares()
        logger.info(f"合并后共 {len(all_shares)} 只基金的份额数据")
        if all_shares:
            first_code = list(all_shares.keys())[0]
            logger.info(f"示例 ({first_code}): {all_shares[first_code]}")
    except Exception as e:
        logger.error(f"合并数据失败: {e}")
        import traceback
        logger.error(traceback.format_exc())


def test_save_shares():
    """测试保存份额数据到数据库"""
    logger.info("\n" + "=" * 80)
    logger.info("测试保存份额数据到数据库")
    logger.info("=" * 80)
    
    try:
        client = get_share_source()
        hdb = get_history_db()
        
        # 获取少量数据用于测试
        all_shares = client.fetch_all_shares()
        
        if all_shares:
            # 只保存前10条作为测试
            test_data = dict(list(all_shares.items())[:10])
            logger.info(f"准备保存 {len(test_data)} 条份额数据")
            
            hdb.save_shares_batch(test_data)
            logger.info("保存成功")
            
            # 验证读取
            first_code = list(test_data.keys())[0]
            latest = hdb.get_latest_shares(first_code)
            logger.info(f"验证读取 - 基金 {first_code}: {latest}")
            
            all_latest = hdb.get_all_latest_shares()
            logger.info(f"数据库中最新份额记录数: {len(all_latest)}")
        else:
            logger.warning("未获取到份额数据")
            
    except Exception as e:
        logger.error(f"保存份额数据失败: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == '__main__':
    print("=" * 80)
    print("LOF基金份额数据测试")
    print("=" * 80)
    
    # 测试1: 获取份额数据
    test_fetch_shares()
    
    # 测试2: 保存到数据库
    test_save_shares()
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
