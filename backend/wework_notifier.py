"""
企业微信通知模块
支持发送文本、Markdown等消息类型
"""
import requests
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class WeWorkNotifier:
    """企业微信通知器"""
    
    def __init__(self, corpid: str, corpsecret: str, agentid: str, 
                 touser: str, msgtype: str = "text"):
        """
        初始化企业微信通知器
        
        Args:
            corpid: 企业ID
            corpsecret: 应用Secret
            agentid: 应用ID
            touser: 接收人ID，多个用|隔开
            msgtype: 消息类型，默认text
        """
        self.corpid = corpid
        self.corpsecret = corpsecret
        self.agentid = agentid
        self.touser = touser
        self.msgtype = msgtype
        self.access_token = None
        self.token_expire_time = 0
        
    def get_access_token(self) -> Optional[str]:
        """
        获取access_token（带缓存）
        
        Returns:
            access_token字符串，失败返回None
        """
        import time
        
        # 检查token是否过期（提前5分钟刷新）
        current_time = time.time()
        if self.access_token and current_time < self.token_expire_time - 300:
            return self.access_token
        
        try:
            url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={self.corpid}&corpsecret={self.corpsecret}"
            response = requests.get(url, timeout=10)
            result = response.json()
            
            if result.get('errcode') == 0:
                self.access_token = result['access_token']
                expires_in = result.get('expires_in', 7200)
                self.token_expire_time = current_time + expires_in
                logger.info("企业微信access_token获取成功")
                return self.access_token
            else:
                logger.error(f"获取access_token失败: {result.get('errmsg')}")
                return None
        except Exception as e:
            logger.error(f"获取access_token异常: {str(e)}")
            return None
    
    def send_text_message(self, content: str) -> bool:
        """
        发送文本消息（自动分条发送）
        
        Args:
            content: 消息内容
            
        Returns:
            发送成功返回True，失败返回False
        """
        # 企业微信单条消息限制 2048 字节
        max_bytes = 2048
        content_bytes = content.encode('utf-8')
        
        # 如果不超过限制，直接发送
        if len(content_bytes) <= max_bytes:
            logger.info(f"准备发送文本消息，长度: {len(content)} 字符, {len(content_bytes)} 字节")
            return self._send_single_message({
                "touser": self.touser,
                "msgtype": "text",
                "agentid": self.agentid,
                "text": {
                    "content": content
                }
            })
        
        # 超过限制，需要分条发送
        logger.warning(f"消息内容过长 ({len(content_bytes)} 字节)，将分条发送")
        
        # 按行分割，保持完整性
        lines = content.split('\n')
        messages = []
        current_msg = []
        current_bytes = 0
        
        for line in lines:
            line_bytes = (line + '\n').encode('utf-8')
            
            # 如果当前消息加上新行会超限，先保存当前消息
            if current_bytes + len(line_bytes) > max_bytes and current_msg:
                messages.append('\n'.join(current_msg))
                current_msg = [line]
                current_bytes = len(line_bytes)
            else:
                current_msg.append(line)
                current_bytes += len(line_bytes)
        
        # 添加最后一条消息
        if current_msg:
            messages.append('\n'.join(current_msg))
        
        logger.info(f"将消息拆分为 {len(messages)} 条发送")
        
        # 逐条发送
        success_count = 0
        for i, msg in enumerate(messages, 1):
            logger.info(f"发送第 {i}/{len(messages)} 条消息，长度: {len(msg.encode('utf-8'))} 字节")
            if self._send_single_message({
                "touser": self.touser,
                "msgtype": "text",
                "agentid": self.agentid,
                "text": {
                    "content": msg
                }
            }):
                success_count += 1
                # 每条之间稍微延迟，避免频繁请求
                import time
                time.sleep(0.5)
        
        logger.info(f"分条发送完成: {success_count}/{len(messages)} 条成功")
        return success_count == len(messages)
    
    def _send_single_message(self, message: dict) -> bool:
        """
        发送单条消息（内部方法）
        
        Args:
            message: 消息体字典
            
        Returns:
            发送成功返回True，失败返回False
        """
        try:
            access_token = self.get_access_token()
            if not access_token:
                logger.error("无法获取access_token，消息发送失败")
                return False
            
            url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
            response = requests.post(
                url, 
                json=message,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            result = response.json()
            
            if result.get('errcode') == 0:
                logger.info(f"企业微信消息发送成功，invaliduser: {result.get('invaliduser', '')}")
                return True
            else:
                logger.error(f"企业微信消息发送失败: {result.get('errmsg')}")
                return False
                
        except Exception as e:
            logger.error(f"发送企业微信消息异常: {str(e)}")
            return False
    
    def send_system_notification(self, title: str, content: str) -> bool:
        """
        发送系统通知
        
        Args:
            title: 通知标题
            content: 通知内容
            
        Returns:
            发送成功返回True，失败返回False
        """
        # 使用纯文本格式，兼容个人微信
        message = (
            f"【{title}】\n\n"
            f"{content}\n\n"
            f"时间: {self._get_current_time()}"
        )
        
        return self.send_text_message(message)
    
    @staticmethod
    def _get_current_time() -> str:
        """获取当前时间字符串"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_notifier_from_env() -> Optional[WeWorkNotifier]:
    """
    从环境变量创建通知器
    
    支持两种配置方式：
    1. WEWORK_CONFIG: corpid,corpsecret,touser,agentid,msgtype(可选)
    2. 独立环境变量: WEWORK_CORPID, WEWORK_CORPSECRET, WEWORK_AGENTID, WEWORK_TOUSER
    
    Returns:
        WeWorkNotifier实例，配置不完整返回None
    """
    import os
    
    # 优先使用 WEWORK_CONFIG 格式
    wework_config = os.getenv('WEWORK_CONFIG', '').strip()
    
    if wework_config:
        # 解析逗号分隔的配置
        parts = [p.strip() for p in wework_config.split(',')]
        
        if len(parts) < 4:
            logger.warning(f"WEWORK_CONFIG 格式错误，至少需要4个参数: {wework_config}")
            return None
        
        corpid = parts[0]
        corpsecret = parts[1]
        touser = parts[2]
        agentid = parts[3]
        msgtype = parts[4] if len(parts) > 4 else 'text'
        
        logger.info("从 WEWORK_CONFIG 加载企业微信配置成功")
        
        return WeWorkNotifier(
            corpid=corpid,
            corpsecret=corpsecret,
            agentid=agentid,
            touser=touser,
            msgtype=msgtype
        )
    
    # 降级到独立环境变量方式
    corpid = os.getenv('WEWORK_CORPID', '').strip()
    corpsecret = os.getenv('WEWORK_CORPSECRET', '').strip()
    agentid = os.getenv('WEWORK_AGENTID', '').strip()
    touser = os.getenv('WEWORK_TOUSER', '').strip()
    
    # 检查必需的配置项
    required = {
        'WEWORK_CORPID': corpid,
        'WEWORK_CORPSECRET': corpsecret,
        'WEWORK_AGENTID': agentid,
        'WEWORK_TOUSER': touser
    }
    
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.warning(f"企业微信配置缺少必要参数: {', '.join(missing)}")
        return None
    
    logger.info("从独立环境变量加载企业微信配置成功")
    
    return WeWorkNotifier(
        corpid=corpid,
        corpsecret=corpsecret,
        agentid=agentid,
        touser=touser,
        msgtype='text'
    )
