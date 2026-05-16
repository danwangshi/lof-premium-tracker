# LOF基金份额数据功能说明

## 概述

本功能集成了从上交所和深交所获取LOF基金场内份额数据的能力，并将数据存储到PostgreSQL数据库中，提供API接口供前端调用。

## 功能特性

1. **数据来源**
   - 上交所（SSE）：通过上交所官网API获取
   - 深交所（SZSE）：通过深交所官网API获取

2. **数据存储**
   - 使用PostgreSQL数据库存储历史份额数据
   - 自动清理超过21天的旧数据
   - 支持按基金代码查询历史份额变化

3. **自动更新**
   - 每次数据刷新时自动在后台获取份额数据
   - 不阻塞主数据抓取流程
   - 支持手动触发份额数据更新

## API接口

### 1. 获取份额数据

**GET /api/shares**

获取基金份额数据

**参数：**
- `code`（可选）：基金代码，不传则返回所有基金最新份额
- `days`（可选）：查询天数，默认30天（仅在指定code时有效）

**示例：**
```bash
# 获取所有基金最新份额
curl http://localhost:5000/api/shares

# 获取某只基金的份额历史（最近30天）
curl http://localhost:5000/api/shares?code=501018

# 获取某只基金的份额历史（最近90天）
curl http://localhost:5000/api/shares?code=501018&days=90
```

**响应示例：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "code": "501018",
    "name": "南方原油A",
    "latest": {
      "date": "2026-05-15",
      "code": "501018",
      "shares": 1234567890.50,
      "source": "SSE"
    },
    "history": [
      {
        "date": "2026-05-15",
        "code": "501018",
        "shares": 1234567890.50,
        "source": "SSE"
      },
      ...
    ]
  }
}
```

### 2. 手动触发份额数据抓取

**POST /api/shares/fetch**

立即触发份额数据抓取（后台执行）

**示例：**
```bash
curl -X POST http://localhost:5000/api/shares/fetch
```

**响应示例：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "份额数据抓取任务已启动（后台执行）"
  }
}
```

## 数据库表结构

### fund_shares 表

存储基金份额历史数据

| 字段 | 类型 | 说明 |
|------|------|------|
| date | DATE | 日期 |
| code | VARCHAR(6) | 基金代码 |
| shares | NUMERIC(18,2) | 份额数量 |
| source | VARCHAR(10) | 数据来源（SSE/SZSE） |
| created_at | TIMESTAMPTZ | 创建时间 |

**主键：** (date, code)  
**索引：** idx_shares_code_date (code, date DESC)

## 使用方法

### 1. 测试份额数据获取

运行测试脚本验证功能：

```bash
python test_shares.py
```

### 2. 启动服务

```bash
cd backend
python app.py
```

服务启动后会自动：
1. 从交易所获取份额数据
2. 保存到PostgreSQL数据库
3. 将份额数据合并到基金缓存中

### 3. 查看份额数据

访问API接口查看数据：

```bash
# 浏览器访问
http://localhost:5000/api/shares

# 或使用curl
curl http://localhost:5000/api/shares?code=501018
```

## 技术实现

### 核心模块

1. **exchange_share_client.py**
   - 交易所份额数据获取客户端
   - 支持上交所和深交所API
   - 自动分页、去重、数据清洗

2. **history_db.py**
   - 扩展了数据库模型，添加fund_shares表
   - 提供份额数据的保存和查询方法
   - 自动清理过期数据

3. **data_fetcher.py**
   - 在主数据抓取流程中集成份额数据获取
   - 使用后台线程异步执行，不阻塞主流程
   - 将份额数据合并到基金缓存

4. **app.py**
   - 提供RESTful API接口
   - 支持查询和手动触发更新

### 数据流程

```
用户访问/定时刷新
    ↓
data_fetcher.fetch_all()
    ↓
步骤1-5: 价格、净值、溢价率、申购状态、费率
    ↓
步骤6: 后台线程获取份额数据
    ↓
exchange_share_client.fetch_all_shares()
    ↓
合并上交所和深交所数据
    ↓
保存到PostgreSQL (history_db.save_shares_batch)
    ↓
更新内存缓存
```

## 注意事项

1. **网络请求**
   - 交易所API可能有访问频率限制
   - 已实现随机延迟防爬虫机制
   - 建议在低峰期进行大量数据抓取

2. **数据准确性**
   - 份额数据通常T+1日公布
   - 最新数据可能不是当天
   - 数据来源标注（SSE/SZSE）便于追溯

3. **性能优化**
   - 份额数据在后台线程中获取，不阻塞主流程
   - 数据库使用连接池提高并发性能
   - 定期清理过期数据保持数据库轻量

## 故障排查

### 问题1：无法获取份额数据

**检查：**
- 网络连接是否正常
- 交易所API是否可访问
- 查看日志中的错误信息

**解决：**
```bash
# 查看详细日志
export LOG_LEVEL=DEBUG
python backend/app.py
```

### 问题2：数据库保存失败

**检查：**
- PostgreSQL服务是否运行
- 数据库连接配置是否正确
- fund_shares表是否已创建

**解决：**
```bash
# 检查数据库连接
psql -h localhost -U postgres -d lof_funds

# 查看表结构
\d fund_shares
```

### 问题3：份额数据为空

**可能原因：**
- 非交易日无数据
- 部分基金无场内份额
- API接口临时不可用

**解决：**
- 等待下一个交易日再试
- 检查其他基金是否有数据
- 查看日志了解具体错误

## 更新日志

### v1.0 (2026-05-16)
- ✅ 初始版本发布
- ✅ 支持上交所和深交所份额数据获取
- ✅ PostgreSQL数据存储
- ✅ RESTful API接口
- ✅ 自动后台更新机制
