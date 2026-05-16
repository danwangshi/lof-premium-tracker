# Pull Request: 协作开发功能合并

## 📋 概述

本 PR 将 danwangshi 分支的协作开发成果合并到主仓库，新增了场内份额追踪、申购限额筛选、365天历史图表等核心功能，同时优化了项目架构和文档体系。

---

## ✨ 新增功能

### 1. 场内份额数据集成 📊

**功能描述：**
- 集成上交所（SSE）和深交所（SZSE）官方 API，获取 LOF 基金场内份额数据
- 支持每日自动抓取 T-1 日份额数据（APScheduler 定时任务，每天 07:00 执行）
- 计算并展示"新增份额"（对比上一个不同日期的份额变化）
- 非交易日自动跳过，避免无效数据

**技术实现：**
- 新增 `backend/datasource/share_source.py` - 交易所份额数据源
- 数据库新增字段：`shares`, `shares_date`, `shares_source`, `shares_incr`
- 前端表格和移动端卡片均展示份额数据（单位：万份）

**API 端点：**
- `GET /api/shares` - 获取份额数据（支持单只基金历史和全量最新）
- `POST /api/shares/fetch` - 手动触发份额抓取

---

### 2. 申购限额多选筛选 🔍

**功能描述：**
- 移除原有的"暂停申购基金自动过滤"逻辑
- 新增下拉多选框，支持按申购限额筛选基金
- 特殊选项："暂停申购"、"开放申购"
- 数值选项：显示具体限额（格式化：元/万/亿）
- 一键清空筛选功能

**优先级规则：**
```
如果 can_purchase == False → 显示"暂停申购"（即使有 limit 值）
如果 can_purchase != False && limit == None → 显示"开放申购"
如果 can_purchase != False && limit != None → 显示具体限额
```

**技术实现：**
- 后端新增 `/api/purchase-limits` 端点，动态生成筛选选项
- 前端 `js/app.js` 实现多选下拉框和筛选逻辑
- 支持 URL 参数传递：`?purchase_limit=suspended&purchase_limit=10000`

---

### 3. 365天历史图表扩展 📈

**功能描述：**
- 历史数据保留期从 21 天扩展到 365 天
- 图表支持多时间范围切换：七日/一月/三月/六月/一年
- 指标体系切换：场内价格+场外净值 / 溢价率（正红负绿双色）
- 热门基金图表预渲染缓存（Top5 溢价 + Top5 折价，每 5 分钟刷新）

**技术实现：**
- 数据库表 `daily_kline` 存储 365 天日线数据
- 新增 `backend/chart_cache.py` - 图表缓存管理器
- 前端 Chart.js 配置支持多指标切换和颜色映射

---

### 4. 定时任务系统 ⏰

**功能描述：**
- 集成 APScheduler，实现每日 07:00 自动抓取份额数据
- 替代原有的 threading 临时方案，更稳定可靠
- 支持任务状态查询和管理

**技术实现：**
- `backend/app.py` 初始化 BackgroundScheduler
- 定时任务：`_scheduled_fetch_shares()`
- 日志记录任务执行状态

---

### 5. 数据源架构优化 🔄

**改进内容：**
- 统一数据源接口：`backend/datasource/base.py` 抽象基类
- 主备双源策略：AkShare（主）+ Legacy（备）
- 熔断机制：连续失败 3 次自动降级，5 分钟后重试
- NAV 逐基金降级：最大化保留主源有效数据

**数据源清单：**
- **主源**：AKShare（开源 Python 库）
- **后备源**：
  - 东方财富 push2delay（沪市行情）
  - 腾讯 qt.gtimg.cn（深市行情）
  - 天天基金 fundgz（净值补缺）
  - 交易所官方 API（份额数据）

---

## 🛠️ 技术改进

### 代码结构优化
- ✅ 将 `requirements.txt` 移至根目录（符合 Python 项目规范）
- ✅ 数据源模块化：`backend/datasource/` 目录统一管理
- ✅ 新增 `.gitignore` 规则，忽略虚拟环境和临时文件
- ✅ 完善环境变量管理：`.env.example` + `.env`

### 文档体系完善
- ✅ 恢复并更新 `CHANGELOG.md`（技术更新日志）
- ✅ 恢复并更新 `CHANGELOG_USER.md`（用户友好版）
- ✅ 恢复并更新 `ENV_SETUP.md`（环境配置指南）
- ✅ README.md 全面升级，添加文档跳转链接
- ✅ 新增"贡献者"章节，明确协作关系

### 部署优化
- ✅ 懒更新机制：用户访问时自动检测并刷新数据
- ✅ 种子文件加载：Railway 重启后快速恢复服务
- ✅ 历史数据降级：实时 API 失败时使用 PostgreSQL 数据

---

## 📊 数据变更

### 数据库 Schema 更新

**新增字段（premium_snapshots 表）：**
```sql
ALTER TABLE premium_snapshots 
ADD COLUMN shares NUMERIC,              -- 场内份额
ADD COLUMN shares_date VARCHAR(10),     -- 份额日期
ADD COLUMN shares_source VARCHAR(10),   -- 数据来源（SSE/SZSE）
ADD COLUMN shares_incr NUMERIC;         -- 新增份额
```

**新增表（daily_kline）：**
```sql
CREATE TABLE daily_kline (
    code VARCHAR(6) NOT NULL,
    date DATE NOT NULL,
    price NUMERIC(10, 4),
    amount NUMERIC(15, 2),
    change_pct NUMERIC(6, 3),
    nav NUMERIC(10, 4),
    premium_rate NUMERIC(6, 3),
    PRIMARY KEY (code, date)
);
```

---

## 🔌 API 变更

### 新增端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/purchase-limits` | 获取申购限额选项 |
| `GET` | `/api/shares` | 获取份额数据 |
| `POST` | `/api/shares/fetch` | 触发份额抓取 |
| `GET` | `/api/tasks` | 查看后台任务状态 |

### 修改端点

| 端点 | 变更 |
|------|------|
| `GET /api/funds` | 新增 `purchase_limit` 筛选参数，返回字段增加 `shares`, `shares_incr` |
| `GET /api/funds/<code>` | 返回字段增加份额相关信息 |
| `GET /api/funds/<code>/chart` | 支持 `days` 参数（7/30/365） |

---

## 📱 前端变更

### UI 改进
- ✅ 申购限额下拉多选框（右侧工具栏）
- ✅ 移动端卡片显示"新增份额xxx万"
- ✅ 排行榜可点击查看详情
- ✅ 基金详情弹窗 KPI 网格居中，显示日期和单位
- ✅ 头部按钮靠右对齐，状态栏移到侧边栏

### 交互优化
- ✅ 一键清空筛选
- ✅ 深色/浅色模式全局适配
- ✅ 自定义滚动条样式
- ✅ 图表悬停显示套利模拟

---

## ⚠️ Breaking Changes

**无破坏性变更**，所有原有 API 保持兼容。

---

## 🧪 测试建议

### 本地测试
```bash
# 1. 克隆仓库
git clone https://github.com/MistyBridge/lof-premium-tracker.git
cd lof-premium-tracker

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，设置数据库连接

# 4. 启动服务
python backend/app.py

# 5. 访问 http://localhost:5000
```

### 关键功能验证
- [ ] 场内份额数据正常显示
- [ ] 申购限额筛选功能正常
- [ ] 365天图表切换流畅
- [ ] 定时任务按时执行
- [ ] 数据源降级机制生效

---

## 📝 提交历史概览

主要提交（最近 15 个）：
```
3b91523 docs: 添加贡献者章节，明确项目协作关系
59638fe docs: 全面更新 README.md，反映 v1.2.0 项目最新状态
9b1ba8b docs: 优化 README.md 为项目入口，添加文档跳转链接
86882a3 docs: 恢复更新日志和技术文档，完善项目文档体系
48074f4 docs: 更新 README.md，补充新功能说明和优化部署指南
27b3761 chore: 删除冗余文档文件，保持项目整洁
769e4ca 更新 .gitignore 文件，添加虚拟环境和临时文件忽略规则
5cc6aba chore: 清理项目，删除测试和临时文件
b615f9e feat: 完善基金监控功能
151132d feat: 前端集成场内份额数据展示
a9e6587 refactor: 将份额数据源集成至 datasource 目录
f57b3c1 chore: 将 requirements.txt 移至根目录
dd2a183 docs: 添加份额数据功能验证报告
4c11d8c feat: 集成交易所LOF份额数据获取功能
6ca465d feat: 添加PostgreSQL数据库支持和本地开发配置
```

---

## 👥 贡献者

| 贡献者 | GitHub | 主要贡献 |
|--------|--------|----------|
| MistyBridge | [@MistyBridge](https://github.com/MistyBridge) | 项目创始人，核心架构设计 |
| danwangshi | [@danwangshi](https://github.com/danwangshi) | 场内份额集成、申购限额筛选、历史图表扩展、定时任务系统 |

---

## 📄 相关文档

- [技术文档](docs/TECH.md) - 系统架构和数据流说明
- [开发指南](docs/DEVELOPMENT.md) - 本地环境搭建和调试
- [环境配置](ENV_SETUP.md) - 环境变量和数据库设置
- [更新日志](CHANGELOG_USER.md) - 详细的功能更新说明

---

## ✅ 检查清单

- [x] 代码符合项目规范
- [x] 新增功能已测试
- [x] 文档已更新
- [x] 无破坏性变更
- [x] 向后兼容
- [x] 数据库迁移脚本就绪
- [x] 依赖包已更新（requirements.txt）

---

## 💬 备注

本 PR 是协作开发的成果汇总，所有新增功能均使用公开免费数据源，无需私有 API Key 或授权。欢迎 Review 并提出建议！
