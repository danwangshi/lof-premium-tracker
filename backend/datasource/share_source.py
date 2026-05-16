"""
交易所LOF场内份额数据获取客户端
从上交所和深交所获取LOF基金的场内份额数据
"""
import requests
import json
import time
import random
import re
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ExchangeShareSource:
    """交易所场内份额数据源：从上交所和深交所获取LOF基金场内份额"""
    
    name = "ExchangeShares"
    """交易所场内份额数据客户端"""
    
    def __init__(self):
        # 上交所Session
        self.sse_session = requests.Session()
        self.sse_session.headers.update({
            'accept': '*/*',
            'Referer': 'https://www.sse.com.cn/',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 16; MEIZU 20 Build/BQ2A.251110.001-BP2A.250605.031.A3; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/146.0.7680.178 Mobile Safari/537.36',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
        })
        
        # 深交所Session
        self.szse_session = requests.Session()
        self.szse_session.headers.update({
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'x-request-type': 'ajax',
            'x-requested-with': 'XMLHttpRequest',
            'Referer': 'https://www.sse.org.cn/market/fund/volume/lof/index.html',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 16; MEIZU 20 Build/BQ2A.251110.001-BP2A.250605.031.A3; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/146.0.7680.178 Mobile Safari/537.36',
        })
    
    def fetch_sse_shares(self, max_pages: int = 10, date: str = None) -> List[Dict]:
        """
        获取上交所LOF份额数据
        
        Args:
            max_pages: 最大页数（每页100条）
            date: 指定日期，格式 YYYY-MM-DD。如果不指定，则获取最新数据
            
        Returns:
            清洗后的份额数据列表
        """
        if date:
            logger.info(f"开始获取上交所LOF份额数据（日期: {date}）...")
        else:
            logger.info("开始获取上交所LOF份额数据...")
        all_data = []
        total_count = 0
        page_size = 100  # 固定分页大小
        required_pages = max_pages
        
        for page in range(1, max_pages + 1):
            data, page_info = self._request_sse_page(page, date=date)
            
            if not data:
                logger.warning(f"上交所第{page}页无数据，停止分页")
                break
            
            # 首次请求时记录总页数并计算需要请求的页数
            if page == 1 and page_info:
                total_count = page_info.get('total', 0)
                # 根据total_count和page_size计算需要请求的页数
                required_pages = (total_count + page_size - 1) // page_size  # 向上取整
                logger.info(f"上交所总共 {total_count} 条记录，每页{page_size}条，需请求 {required_pages} 页")
            
            all_data.extend(data)
            logger.info(f"上交所第{page}页: {len(data)}条记录")
            
            # 如果已获取所有记录，提前退出
            if len(all_data) >= total_count:
                logger.info(f"已获取全部 {total_count} 条记录")
                break
            
            # 如果已达到计算的页数，停止请求
            if page >= required_pages:
                logger.info(f"已达到计算页数 {required_pages}，停止请求")
                break
            
            # 随机延迟防爬虫
            time.sleep(random.uniform(1, 2))
        
        # 清洗数据
        cleaned_data = self._clean_sse_data(all_data)
        logger.info(f"上交所总共获取 {len(cleaned_data)} 条份额数据")
        
        return cleaned_data
    
    def _request_sse_page(self, page: int, date: str = None) -> tuple:
        """
        请求上交所单页数据
        
        Args:
            page: 页码（从1开始）
            date: 指定日期，格式 YYYY-MM-DD。如果不指定，则获取最新数据
        
        Returns:
            (result_list, page_info_dict)
        """
        url = "https://query.sse.com.cn/commonQuery.do"
        
        # 动态构造参数
        timestamp = int(time.time() * 1000)
        callback_name = f"jsonpCallback{random.randint(10000000, 99999999)}"
        
        # 处理日期参数：YYYY-MM-DD -> YYYYMMDD
        search_date = ''
        if date:
            search_date = date.replace('-', '')
        
        params = {
            'jsonCallBack': callback_name,
            'isPagination': 'true',
            'PRODUCT_TYPE': '11,14',  # 11=LOF, 14=ETF
            'SEARCH_DATE': search_date,
            'type': 'inParams',
            'sqlId': 'COMMON_SSE_SJ_JJSJ_JJGM_LOFGMTJ_L',
            'pageHelp.pageSize': '100',  # 固定分页大小100
            'pageHelp.cacheSize': '1',
            'pagecache': 'false',
            'pageHelp.pageNo': str(page),
            'pageHelp.beginPage': str(page),  # 与pageNo一致
            'pageHelp.endPage': str(page),    # 与pageNo一致
            '_': str(timestamp)
        }
        
        try:
            r = self.sse_session.get(url, params=params, timeout=10)
            
            if r.status_code != 200:
                logger.error(f"上交所API请求失败: {r.status_code}")
                return None, None
            
            # 解析JSONP响应
            text = r.text
            match = re.search(r'\((\{.*\})\)', text, re.DOTALL)
            
            if not match:
                logger.error("无法解析JSONP响应")
                return None, None
            
            json_str = match.group(1)
            data = json.loads(json_str)
            
            result = data.get('result', [])
            page_info = data.get('pageHelp', {})
            
            if not isinstance(result, list):
                return None, None
            
            return result, page_info
            
        except Exception as e:
            logger.error(f"上交所API请求异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, None
    
    def _clean_sse_data(self, raw_list: List[Dict]) -> List[Dict]:
        """清洗上交所数据（自动去重）"""
        cleaned = []
        seen_codes = set()  # 用于去重
        
        for item in raw_list:
            try:
                fund_code = item.get('FUND_CODE', '').strip()
                
                # 跳过重复的基金代码
                if fund_code in seen_codes:
                    continue
                seen_codes.add(fund_code)
                
                # 去除千分位逗号并转换为浮点数
                shares_str = item.get('INTERNAL_VOL', '0').replace(',', '')
                shares = float(shares_str)
                
                # 转换日期格式：20260513 -> 2026-05-13
                trade_date = item.get('TRADE_DATE', '')
                if len(trade_date) == 8:
                    formatted_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
                else:
                    formatted_date = trade_date
                
                cleaned.append({
                    'fund_code': fund_code,
                    'shares': shares,
                    'date': formatted_date,
                    'source': 'SSE'
                })
            except Exception as e:
                logger.warning(f"清洗上交所数据失败: {item}, 错误: {e}")
                continue
        
        return cleaned
    
    def fetch_szse_shares(self, date: str = None, max_pages: int = 20) -> List[Dict]:
        """
        获取深交所LOF份额数据
        
        Args:
            date: 查询日期（YYYY-MM-DD格式），默认为昨天
            max_pages: 最大页数（每页20条）
            
        Returns:
            清洗后的份额数据列表
        """
        if date is None:
            # 默认使用上一个交易日（T-1日）
            date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        logger.info(f"开始获取深交所LOF份额数据（日期: {date}）...")
        all_data = []
        total_count = 0
        page_count = 0
        
        for page in range(1, max_pages + 1):
            data, page_info = self._request_szse_page(page, date)
            
            if not data:
                logger.warning(f"深交所第{page}页无数据，停止分页")
                break
            
            # 首次请求时记录总页数
            if page == 1 and page_info:
                total_count = page_info.get('recordcount', 0)
                page_count = page_info.get('pagecount', 0)
                logger.info(f"深交所总共 {total_count} 条记录，共 {page_count} 页")
            
            all_data.extend(data)
            logger.info(f"深交所第{page}页: {len(data)}条记录")
            
            # 如果已获取所有页，提前退出
            if page >= page_count:
                logger.info(f"已获取全部 {page_count} 页数据")
                break
            
            # 随机延迟防爬虫
            time.sleep(random.uniform(1, 2))
        
        # 清洗数据
        cleaned_data = self._clean_szse_data(all_data)
        logger.info(f"深交所总共获取 {len(cleaned_data)} 条份额数据")
        
        return cleaned_data
    
    def _request_szse_page(self, page: int, date: str) -> tuple:
        """
        请求深交所单页数据
        
        Returns:
            (result_list, page_info_dict)
        """
        url = "https://www.sse.org.cn/api/report/ShowReport/data"
        
        # 动态构造参数
        random_val = random.random()
        
        params = {
            'SHOWTYPE': 'JSON',
            'CATALOGID': 'scsj_fund_jjgm',
            'TABKEY': 'tab1',
            'PAGENO': str(page),
            'txtStart': date,
            'txtEnd': date,
            'jjlb': 'LOF',
            'random': str(random_val)
        }
        
        try:
            r = self.szse_session.get(url, params=params, timeout=10)
            
            if r.status_code != 200:
                logger.error(f"深交所API请求失败: {r.status_code}")
                return None, None
            
            data = r.json()
            
            if not isinstance(data, list) or len(data) == 0:
                return None, None
            
            first = data[0]
            if 'data' not in first:
                return None, None
            
            result = first['data']
            page_info = first.get('metadata', {})
            
            return result, page_info
            
        except Exception as e:
            logger.error(f"深交所API请求异常: {e}")
            return None, None
    
    def _clean_szse_data(self, raw_list: List[Dict]) -> List[Dict]:
        """清洗深交所数据"""
        cleaned = []
        
        for item in raw_list:
            try:
                # Trim基金代码空格
                fund_code = item.get('fund_code', '').strip()
                
                # 去除千分位逗号并转换为浮点数
                shares_str = item.get('current_size', '0').replace(',', '')
                shares = float(shares_str)
                
                cleaned.append({
                    'fund_code': fund_code,
                    'shares': shares,
                    'date': item.get('size_date', ''),
                    'source': 'SZSE'
                })
            except Exception as e:
                logger.warning(f"清洗深交所数据失败: {item}, 错误: {e}")
                continue
        
        return cleaned
    
    def fetch_all_shares(self) -> Dict[str, Dict]:
        """
        获取所有交易所的份额数据并合并
        
        Returns:
            字典，key为基金代码，value为份额信息
        """
        logger.info("开始获取所有交易所份额数据...")
        
        # 获取上交所数据
        sse_data = self.fetch_sse_shares()
        
        # 获取深交所数据
        szse_data = self.fetch_szse_shares()
        
        # 合并数据（以基金代码为key）
        merged = {}
        
        for item in sse_data:
            code = item['fund_code']
            merged[code] = item
        
        for item in szse_data:
            code = item['fund_code']
            # 如果已存在，保留最新的
            if code in merged:
                if item['date'] >= merged[code]['date']:
                    merged[code] = item
            else:
                merged[code] = item
        
        logger.info(f"合并后共 {len(merged)} 只基金的份额数据")
        
        return merged


# 单例模式
_share_source_instance = None

def get_share_source() -> ExchangeShareSource:
    """获取 ExchangeShareSource 单例"""
    global _share_source_instance
    if _share_source_instance is None:
        _share_source_instance = ExchangeShareSource()
    return _share_source_instance


def reset_share_source():
    """重置数据源（用于测试）"""
    global _share_source_instance
    _share_source_instance = None


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    client = get_share_source()
    
    print("=" * 80)
    print("测试交易所份额数据获取")
    print("=" * 80)
    
    # 测试上交所
    print("\n【1】测试上交所数据获取...")
    sse_data = client.fetch_sse_shares(max_pages=2)
    print(f"获取到 {len(sse_data)} 条上交所数据")
    if sse_data:
        print(f"示例: {sse_data[0]}")
    
    # 测试深交所
    print("\n【2】测试深交所数据获取...")
    szse_data = client.fetch_szse_shares(max_pages=2)
    print(f"获取到 {len(szse_data)} 条深交所数据")
    if szse_data:
        print(f"示例: {szse_data[0]}")
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
