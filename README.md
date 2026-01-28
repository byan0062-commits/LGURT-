# LGURT Business Dashboard v5.1

Amazon 运营数据分析仪表盘 - 极简商务版

## 🆕 v5.1 更新

### 任务0: UI 风格升级
- **Design Tokens**: 使用CSS变量定义颜色/字体/间距/阴影
- **双主题支持**: `theme-dark`(默认) / `theme-light`
- **语义化类**: `.panel` `.kpi-card` `.badge` `.chip` `.data-table` `.alert`
- **主题切换**: 右上角 🌙/☀️ 按钮，保存到localStorage

### 任务1: 广告梯度结构化输出
- **Phase1 无意义消耗清单**: 结构化数组，每条包含sku/wasted_spend/reason/suggested_action
- **Phase2 增量优化周计划**: 每周target_ad_ratio/delta/actions/checkpoint
- **销量影响度三档**: conservative/moderate/aggressive估算
- **非线性风险阈值**: 累计>5%触发警告

### 任务2: PDF 导出完整版
- **章节覆盖**: 封面/Executive Summary/Overview/Profit/Ads/Inventory/Config
- **筛选一致**: 导出数据与页面筛选保持一致
- **页脚元数据**: run_id/timestamp/algo_version

### 任务3: Excel/PDF/DB 一致性
- **ResultBundle统一**: summary/skus/ads/inventory/diagnostics/config
- **一致性校验**: checksum_rev/checksum_op双层校验
- **API回放**: GET /api/runs/{id} 返回完整ResultBundle

## 📦 文件结构

```
amazon-dashboard-local/
├── index_standalone.html  # 纯前端完整版 (1327行)
├── app.py                 # Flask后端
├── data_processor.py      # 数据处理模块
├── templates/
│   ├── index.html         # Flask版前端
│   └── login.html         # 登录页面
├── requirements.txt       # Python依赖
├── docker-compose.yml     # Docker编排
├── Dockerfile            # 镜像构建
└── README.md             # 本文档
```

## 🚀 快速开始

### 模式1: 纯前端 (无需后端)
```bash
# 直接打开浏览器
open index_standalone.html
```

### 模式2: Flask后端
```bash
pip install flask pandas openpyxl werkzeug
python app.py
# 访问 http://localhost:5001
# 默认用户: demo / demo123
```

## 📊 Design Tokens

```css
:root {
    /* 颜色 */
    --bg-app: #0a0a0f;
    --bg-surface: #141418;
    --text-primary: #f5f5f7;
    --text-secondary: #a1a1a6;
    --accent-primary: #0071e3;
    --accent-success: #30d158;
    --accent-danger: #ff453a;
    
    /* 间距 */
    --space-sm: 8px;
    --space-md: 16px;
    --space-lg: 24px;
    
    /* 圆角 */
    --radius-md: 10px;
    --radius-lg: 16px;
}
```

## 🎯 广告两阶段优化

### Phase 1: 无意义消耗清单
```json
{
  "wasteList": [
    {
      "sku": "A1-YG-black",
      "wasted_spend": 150.5,
      "reason": "广告花费$150但归因销售为0",
      "suggested_action": "pause",
      "action_desc": "暂停该SKU所有广告投放"
    }
  ],
  "totalSavings": 500,
  "salesImpactAssumption": "销量影响<5%"
}
```

### Phase 2: 周计划表
```json
{
  "plan": [
    {
      "week": 1,
      "target_ad_ratio": 0.15,
      "delta": 0.015,
      "daily_budget": 120,
      "actions": ["降长尾词竞价20%", "否定7天内无转化词"],
      "checkpoint": null
    }
  ]
}
```

### 销量影响度三档
| 类型 | 公式 | 说明 |
|-----|------|------|
| conservative | ad_dependency × 0.25 | 乐观场景 |
| moderate | ad_dependency × 0.5 | 中性场景 |
| aggressive | ad_dependency × 0.8 | 悲观场景 |

## 📋 API 接口

### 认证
```
POST /api/auth/login     - 登录
POST /api/auth/register  - 注册
POST /api/auth/logout    - 登出
GET  /api/auth/me        - 当前用户
```

### Runs (ResultBundle)
```
POST   /api/runs/upload  - 上传Excel→计算→落库→返回run_id
GET    /api/runs         - 列表 (分页)
GET    /api/runs/{id}    - 回放完整ResultBundle
DELETE /api/runs/{id}    - 删除
GET    /api/runs/{id}/verify - 一致性校验
```

### ResultBundle 结构
```json
{
  "run_id": "run_abc123",
  "algo_version": "v5.1",
  "created_at": "2026-01-28T12:00:00Z",
  "params": {...},
  "summary": {...},
  "skus": [...],
  "ads": {...},        // Phase1/Phase2
  "inventory": [...],
  "diagnostics": [...],
  "config": {...},
  "checksum": {"rev": 10000, "op": 1500}
}
```

## 📄 Excel 导出结构

| Sheet | 内容 |
|-------|------|
| Summary_Store | 店铺汇总 + Phase1/Phase2预估 |
| SKU_Full | SKU利润+广告+库存+诊断 |
| Ads_Detail | Phase1清单+Phase2周计划+影响度 |
| Inventory_Detail | DOS+补货建议 |
| Config_And_Definitions | 配置+字段定义+一致性校验 |

## 🔍 一致性校验

### 前端校验
```javascript
const checksumRev = skus.reduce((a, x) => a + x.rev, 0);
if (Math.abs(checksumRev - summary.rev) > 1) {
    console.warn('一致性校验警告');
}
```

### DB回放校验
```bash
curl /api/runs/{id}/verify
# 返回 {"is_consistent": true, "difference": {"rev": 0.01, "op": 0.02}}
```

## 📱 验收用例

### 1. Phase1清单样例
- 上传含零归因SKU的数据
- 广告页面显示Phase1无意义消耗清单
- 每条包含: SKU/浪费金额/原因/建议动作

### 2. Phase2周计划样例
- 当Phase1执行后广告占比仍高于目标
- 显示Week 1-N的降幅计划
- 每周包含: 目标占比/降幅/日预算/执行动作

### 3. PDF章节完整性
- 封面: 周期/run_id/algo_version
- Executive Summary: KPI+一句话结论
- Overview: 四象限分布
- Profit: 盈利/亏损TOP10
- Ads: Phase1+Phase2+影响度
- Inventory: 低库存清单
- Config: 参数+字段定义

### 4. run_id回放一致性
- 调用 GET /api/runs/{id}
- 返回的ResultBundle可直接渲染
- checksum字段与存储一致

### 5. UI回归检查
- ✅ 上传功能正常
- ✅ 筛选功能正常
- ✅ Tab切换正常
- ✅ Modal弹窗正常
- ✅ PDF导出正常
- ✅ Excel导出正常
- ✅ 主题切换正常

## 📄 License
MIT
