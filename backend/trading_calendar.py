"""
交易日历工具
使用 exchange_calendars 库判断交易日
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def is_trading_day(date: Optional[datetime] = None) -> bool:
    """
    判断指定日期是否为交易日（使用真实交易日历）
    
    Args:
        date: 要判断的日期，默认为今天
        
    Returns:
        bool: True 表示交易日，False 表示非交易日
    """
    if date is None:
        date = datetime.now()
    
    try:
        import exchange_calendars as xcals
        import pandas as pd
        
        sse_calendar = xcals.get_calendar("XSHG")
        target_date = pd.Timestamp(date.date())
        
        is_trading = sse_calendar.is_session(target_date)
        return is_trading
    except Exception as e:
        # 如果交易日历失败，降级为简单的周一到周五判断
        logger.warning(f"[交易日判断] 交易日历查询失败 ({e})，使用简单判断")
        is_trading = date.weekday() < 5  # 0-4为周一到周五
        return is_trading


def get_last_trading_date() -> str:
    """
    获取上一个交易日的日期（使用真实交易日历）
    
    Returns:
        日期字符串，格式 YYYY-MM-DD
    """
    from datetime import datetime
    
    logger.info("[交易日判断] 开始获取上一个交易日...")
    
    try:
        import exchange_calendars as xcals
        import pandas as pd
        
        sse_calendar = xcals.get_calendar("XSHG")
        today = pd.Timestamp(datetime.now().date())
        
        # 获取上一个交易日（新版 API）
        last_session = sse_calendar.previous_session(today)
        last_trading_date = last_session.strftime('%Y-%m-%d')
        
        logger.info(f"[交易日判断] 上一个交易日: {last_trading_date}")
        return last_trading_date
        
    except Exception as e:
        logger.warning(f"[交易日判断] 交易日历查询失败 ({e})，使用简单减1天")
        # 降级方案：简单减1天，如果是周末继续往前找
        check_date = datetime.now() - timedelta(days=1)
        while check_date.weekday() >= 5:  # 跳过周末
            check_date -= timedelta(days=1)
        
        last_trading_date = check_date.strftime('%Y-%m-%d')
        logger.info(f"[交易日判断] 上一个交易日（降级）: {last_trading_date}")
        return last_trading_date


def get_previous_trading_date(date: str, days_back: int = 1) -> str:
    """
    获取指定日期往前推 N 个交易日的日期
    
    Args:
        date: 起始日期，格式 YYYY-MM-DD
        days_back: 往前推的交易日数量
        
    Returns:
        日期字符串，格式 YYYY-MM-DD
    """
    try:
        import exchange_calendars as xcals
        import pandas as pd
        from datetime import datetime
        
        sse_calendar = xcals.get_calendar("XSHG")
        start_date = pd.Timestamp(datetime.strptime(date, '%Y-%m-%d').date())
        
        # 获取前 N 个交易日
        sessions = sse_calendar.sessions_in_range(
            sse_calendar.first_session_label,
            start_date
        )
        
        if len(sessions) <= days_back:
            # 如果不够，返回第一个交易日
            return sessions[0].strftime('%Y-%m-%d')
        
        previous_date = sessions[-(days_back + 1)]
        return previous_date.strftime('%Y-%m-%d')
        
    except Exception as e:
        logger.warning(f"[交易日判断] 获取前{days_back}个交易日失败 ({e})，使用简单计算")
        # 降级方案
        from datetime import datetime, timedelta
        check_date = datetime.strptime(date, '%Y-%m-%d')
        count = 0
        while count < days_back:
            check_date -= timedelta(days=1)
            if check_date.weekday() < 5:  # 只算工作日
                count += 1
        return check_date.strftime('%Y-%m-%d')
