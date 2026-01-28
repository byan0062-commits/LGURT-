"""
LGURT Dashboard v5.1 - Data Processor
Excel处理 + 计算逻辑 + Phase1/Phase2生成 + 诊断生成
"""
import pandas as pd
from io import BytesIO

ALGO_VERSION = 'v5.1'

# ==================== SKU角色配置 ====================
SKU_ROLE_CONFIG = {
    'profit': {'name': '盈利款', 'allowedLoss': 0, 'stopLoss': 0, 'windowWeeks': None},
    'traffic': {'name': '引流款', 'allowedLoss': -0.10, 'stopLoss': -0.15, 'windowWeeks': 8},
    'defense': {'name': '防御款', 'allowedLoss': -0.15, 'stopLoss': -0.25, 'windowWeeks': 4},
    'test': {'name': '测试款', 'allowedLoss': -0.30, 'stopLoss': -0.50, 'windowWeeks': 8}
}

def process_excel_file(file, params):
    """
    处理上传的Excel文件，返回计算结果
    """
    days = params.get('days', 31)
    
    # 读取Excel
    if hasattr(file, 'read'):
        content = file.read()
        file_obj = BytesIO(content)
    else:
        file_obj = file
    
    xl = pd.ExcelFile(file_obj)
    
    # 解析各sheet
    sales_df = parse_sheet(xl, 'sales_data', skip=19)
    master_df = parse_sheet(xl, 'sku_master', skip=18)
    ads_df = parse_sheet(xl, 'ad_data', skip=18)
    inv_df = parse_sheet(xl, 'inventory_data', skip=15)
    fc_df = parse_sheet(xl, 'fixed_costs', skip=12)
    
    # 构建SKU信息映射
    sku_info = {}
    if master_df is not None and len(master_df) > 0:
        for _, row in master_df.iterrows():
            sku = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ''
            if sku:
                sku_info[sku] = {
                    'name': str(row.iloc[2]) if len(row) > 2 and pd.notna(row.iloc[2]) else sku,
                    'cat': str(row.iloc[3]) if len(row) > 3 and pd.notna(row.iloc[3]) else '未分类',
                    'cost': safe_float(row.iloc[4]) if len(row) > 4 else 0,
                    'freight': safe_float(row.iloc[5]) if len(row) > 5 else 0
                }
    
    # 构建广告数据映射
    ad_by_sku = {}
    ad_by_asin = {}
    if ads_df is not None and len(ads_df) > 0:
        for _, row in ads_df.iterrows():
            asin = str(row.iloc[1]) if len(row) > 1 and pd.notna(row.iloc[1]) else ''
            sku = str(row.iloc[2]).strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ''
            ad = {
                'spend': safe_float(row.iloc[10]) if len(row) > 10 else 0,
                'imp': safe_float(row.iloc[7]) if len(row) > 7 else 0,
                'clk': safe_float(row.iloc[8]) if len(row) > 8 else 0,
                'sales': safe_float(row.iloc[4]) if len(row) > 4 else 0
            }
            if sku:
                if sku not in ad_by_sku:
                    ad_by_sku[sku] = {'spend': 0, 'imp': 0, 'clk': 0, 'sales': 0}
                ad_by_sku[sku]['spend'] += ad['spend']
                ad_by_sku[sku]['imp'] += ad['imp']
                ad_by_sku[sku]['clk'] += ad['clk']
                ad_by_sku[sku]['sales'] += ad['sales']
            elif asin:
                key = asin.split('-')[0]
                if key not in ad_by_asin:
                    ad_by_asin[key] = {'spend': 0, 'imp': 0, 'clk': 0, 'sales': 0}
                ad_by_asin[key]['spend'] += ad['spend']
                ad_by_asin[key]['imp'] += ad['imp']
                ad_by_asin[key]['clk'] += ad['clk']
                ad_by_asin[key]['sales'] += ad['sales']
    
    # 构建库存映射
    inv_by_sku = {}
    if inv_df is not None and len(inv_df) > 0:
        for _, row in inv_df.iterrows():
            sku = str(row.iloc[1]) if len(row) > 1 and pd.notna(row.iloc[1]) else ''
            if sku:
                inv_by_sku[sku] = {
                    'ful': safe_float(row.iloc[5]) if len(row) > 5 else 0,
                    'inb': safe_float(row.iloc[6]) if len(row) > 6 else 0,
                    'rsv': safe_float(row.iloc[7]) if len(row) > 7 else 0
                }
    
    # 解析固定成本
    mf_monthly = 0
    if fc_df is not None and len(fc_df) > 0:
        last_row = fc_df.iloc[-1]
        labor = safe_float(last_row.iloc[1]) if len(last_row) > 1 else 0
        rent = safe_float(last_row.iloc[2]) if len(last_row) > 2 else 0
        sw = safe_float(last_row.iloc[3]) if len(last_row) > 3 else 0
        other1 = safe_float(last_row.iloc[4]) if len(last_row) > 4 else 0
        other2 = safe_float(last_row.iloc[5]) if len(last_row) > 5 else 0
        mf_monthly = labor + rent + sw + other1 + other2
    
    mf_daily = mf_monthly / 30
    mf_period = mf_daily * days
    
    # 处理销售数据
    skus = []
    if sales_df is not None and len(sales_df) > 0:
        for _, row in sales_df.iterrows():
            sku = str(row.iloc[2]) if len(row) > 2 and pd.notna(row.iloc[2]) else ''
            asin = str(row.iloc[1]) if len(row) > 1 and pd.notna(row.iloc[1]) else ''
            rev = safe_float(row.iloc[6]) if len(row) > 6 else 0
            
            if not sku or rev <= 0:
                continue
            
            info = sku_info.get(sku, {'name': sku, 'cat': '未分类', 'cost': 0, 'freight': 0})
            units = safe_float(row.iloc[5]) if len(row) > 5 else 0
            rfm = abs(safe_float(row.iloc[8])) if len(row) > 8 else 0
            ref = safe_float(row.iloc[9]) if len(row) > 9 else 0
            fba = safe_float(row.iloc[10]) if len(row) > 10 else 0
            
            cogs = info['cost'] * units
            frt = info['freight'] * units
            pp = rev - ref - fba - cogs - frt - rfm
            pm = pp / rev if rev > 0 else 0
            
            # 获取广告数据
            ad = ad_by_sku.get(sku)
            if not ad:
                key = asin.split('-')[0] if asin else ''
                ad = ad_by_asin.get(key, {'spend': 0, 'imp': 0, 'clk': 0, 'sales': 0})
            
            op = pp - ad['spend']
            om = op / rev if rev > 0 else 0
            ar = ad['spend'] / rev if rev > 0 else 0
            
            # 获取库存数据
            iv = inv_by_sku.get(sku, {'ful': 0, 'inb': 0, 'rsv': 0})
            du = units / days
            
            skus.append({
                'sku': sku,
                'asin': asin,
                'name': info['name'],
                'cat': info['cat'],
                'units': round(units, 0),
                'du': round(du, 1),
                'rev': round(rev, 2),
                'ref': round(ref, 2),
                'fba': round(fba, 2),
                'cogs': round(cogs, 2),
                'frt': round(frt, 2),
                'rfmFee': round(rfm, 2),
                'pp': round(pp, 2),
                'pm': round(pm, 4),
                'adSpend': round(ad['spend'], 2),
                'adImp': ad['imp'],
                'adClk': ad['clk'],
                'adSales': round(ad['sales'], 2),
                'op': round(op, 2),
                'om': round(om, 4),
                'ar': round(ar, 4),
                'acos': round(ad['spend'] / ad['sales'], 4) if ad['sales'] > 0 else 0,
                'roas': round(ad['sales'] / ad['spend'], 2) if ad['spend'] > 0 else 0,
                'ful': iv['ful'],
                'inb': iv['inb'],
                'rsv': iv['rsv']
            })
    
    # 按经营利润排序
    skus.sort(key=lambda x: x['op'], reverse=True)
    
    # 计算汇总
    t = {
        'rev': sum(s['rev'] for s in skus),
        'units': sum(s['units'] for s in skus),
        'ref': sum(s['ref'] for s in skus),
        'fba': sum(s['fba'] for s in skus),
        'cogs': sum(s['cogs'] for s in skus),
        'frt': sum(s['frt'] for s in skus),
        'rfmFee': sum(s['rfmFee'] for s in skus),
        'pp': sum(s['pp'] for s in skus),
        'adSpend': sum(s['adSpend'] for s in skus),
        'op': sum(s['op'] for s in skus),
        'imp': sum(s['adImp'] for s in skus),
        'clk': sum(s['adClk'] for s in skus),
        'adSales': sum(s['adSales'] for s in skus)
    }
    
    d_rev = t['rev'] / days if days > 0 else 0
    om = t['op'] / t['rev'] if t['rev'] > 0 else 0
    np = t['op'] - mf_period
    be = mf_daily / om if om > 0 else 0
    
    summary = {
        **t,
        'days': days,
        'dRev': round(d_rev, 2),
        'pm': round(t['pp'] / t['rev'], 4) if t['rev'] > 0 else 0,
        'ar': round(t['adSpend'] / t['rev'], 4) if t['rev'] > 0 else 0,
        'om': round(om, 4),
        'mfMonthly': mf_monthly,
        'mfDaily': round(mf_daily, 2),
        'mfPeriod': round(mf_period, 2),
        'np': round(np, 2),
        'npm': round(np / t['rev'], 4) if t['rev'] > 0 else 0,
        'ctr': round(t['clk'] / t['imp'], 4) if t['imp'] > 0 else 0,
        'cpc': round(t['adSpend'] / t['clk'], 2) if t['clk'] > 0 else 0,
        'acos': round(t['adSpend'] / t['adSales'], 4) if t['adSales'] > 0 else 0,
        'roas': round(t['adSales'] / t['adSpend'], 2) if t['adSpend'] > 0 else 0,
        'dailyBreakEven': round(be, 2)
    }
    
    return {'summary': summary, 'skus': skus}


def generate_ad_plan(summary, skus):
    """
    生成广告优化计划 (Phase1/Phase2结构化输出)
    任务1核心实现
    """
    s = summary
    current_ad_ratio = s['ar']
    pricing_margin = s['pm']
    daily_rev = s['dRev']
    daily_fixed = s['mfDaily']
    
    break_even_ad_ratio = pricing_margin - (daily_fixed / daily_rev if daily_rev > 0 else 0)
    target_ad_ratio = max(0, break_even_ad_ratio * 0.9)
    need_reduce = current_ad_ratio > target_ad_ratio
    gap = max(0, current_ad_ratio - target_ad_ratio)
    ad_dependency = s['adSales'] / s['rev'] if s['rev'] > 0 else 0
    
    ad_skus = [x for x in skus if x['adSpend'] > 0]
    
    # ========== Phase 1: 无意义消耗清单 ==========
    phase1_waste_list = []
    
    # 1) 高花费零归因
    for x in ad_skus:
        if x['adSpend'] > 30 and x['adSales'] == 0:
            phase1_waste_list.append({
                'sku': x['sku'],
                'asin': x['asin'],
                'wasted_spend': x['adSpend'],
                'reason': f"广告花费${x['adSpend']:.0f}但归因销售为0",
                'suggested_action': 'pause',
                'action_desc': '暂停该SKU所有广告投放'
            })
    
    # 2) ACOS极高 (>300%)
    for x in ad_skus:
        if x['acos'] > 3 and x['adSpend'] > 20:
            if not any(p['sku'] == x['sku'] for p in phase1_waste_list):
                phase1_waste_list.append({
                    'sku': x['sku'],
                    'asin': x['asin'],
                    'wasted_spend': x['adSpend'] * 0.8,
                    'reason': f"ACOS={x['acos']*100:.0f}%极高，投入产出严重失衡",
                    'suggested_action': 'restructure',
                    'action_desc': '砍掉80%预算，仅保留核心词'
                })
    
    # 3) 广告占比>毛利率×2
    for x in ad_skus:
        if x['ar'] > x['pm'] * 2 and x['adSpend'] > 30 and x['pm'] > 0:
            if not any(p['sku'] == x['sku'] for p in phase1_waste_list):
                phase1_waste_list.append({
                    'sku': x['sku'],
                    'asin': x['asin'],
                    'wasted_spend': max(0, x['adSpend'] - x['rev'] * x['pm'] * 0.8),
                    'reason': f"广告占比{x['ar']*100:.1f}%超过毛利率{x['pm']*100:.1f}%的2倍",
                    'suggested_action': 'negate',
                    'action_desc': '否定低效词，预算降至毛利80%'
                })
    
    phase1_total_savings = sum(max(0, w['wasted_spend']) for w in phase1_waste_list)
    phase1_ratio_reduction = phase1_total_savings / s['rev'] if s['rev'] > 0 else 0
    after_phase1_ratio = max(0, current_ad_ratio - phase1_ratio_reduction)
    
    # Phase 1 汇总动作
    phase1_actions = []
    pause_items = [w for w in phase1_waste_list if w['suggested_action'] == 'pause']
    restructure_items = [w for w in phase1_waste_list if w['suggested_action'] == 'restructure']
    negate_items = [w for w in phase1_waste_list if w['suggested_action'] == 'negate']
    
    if pause_items:
        phase1_actions.append({
            'action': '暂停零归因投放',
            'skuCount': len(pause_items),
            'spend': sum(w['wasted_spend'] for w in pause_items),
            'impact': '销量影响≈0（本来就没有归因）'
        })
    if restructure_items:
        phase1_actions.append({
            'action': '砍掉ACOS>300%投放80%',
            'skuCount': len(restructure_items),
            'spend': sum(w['wasted_spend'] for w in restructure_items),
            'impact': '销量影响<3%（这些投放ROI极差）'
        })
    if negate_items:
        phase1_actions.append({
            'action': '降超支SKU至毛利80%线',
            'skuCount': len(negate_items),
            'spend': sum(w['wasted_spend'] for w in negate_items),
            'impact': '销量影响5-8%'
        })
    
    # ========== Phase 2: 增量优化周计划 ==========
    phase2_gap = max(0, after_phase1_ratio - target_ad_ratio)
    phase2_plan = []
    
    if phase2_gap > 0:
        weekly_reduction = 0.015
        weeks_needed = int(phase2_gap / weekly_reduction) + 1
        temp_ratio = after_phase1_ratio
        
        for w in range(1, min(weeks_needed, 12) + 1):
            reduction = min(weekly_reduction, temp_ratio - target_ad_ratio)
            if reduction <= 0:
                break
            temp_ratio -= reduction
            
            if w == 1:
                actions = ['降长尾词竞价20%', '否定7天内无转化词']
            elif w == 2:
                actions = ['否定ACOS>目标50%词', '降低自动广告预算15%']
            elif w <= 4:
                actions = ['收缩低效campaign预算', '暂停点击>50无订单词']
            elif w <= 6:
                actions = ['结构性调整：合并相似campaign', '提升核心词占比']
            else:
                actions = ['持续监控自然位变化', '若排名下滑暂停继续降幅']
            
            phase2_plan.append({
                'week': w,
                'target_ad_ratio': round(temp_ratio, 4),
                'delta': round(reduction, 4),
                'daily_budget': round(daily_rev * temp_ratio, 2),
                'actions': actions,
                'checkpoint': '检查自然排名与自然单量' if w % 2 == 0 else None
            })
    
    # ========== 销量影响度三档估算 ==========
    impact_per_point = {
        'conservative': {'rate': round(ad_dependency * 0.25, 4), 'desc': '乐观场景：自然流量强，广告主要做增量'},
        'moderate': {'rate': round(ad_dependency * 0.5, 4), 'desc': '中性场景：广告与自然互相影响'},
        'aggressive': {'rate': round(ad_dependency * 0.8, 4), 'desc': '悲观场景：高度依赖广告拉动排名'}
    }
    
    total_reduction_pct = gap * 100
    sales_impact = {
        'conservative': round(total_reduction_pct * impact_per_point['conservative']['rate'], 1),
        'moderate': round(total_reduction_pct * impact_per_point['moderate']['rate'], 1),
        'aggressive': round(total_reduction_pct * impact_per_point['aggressive']['rate'], 1)
    }
    
    risk_threshold = 5
    has_nonlinear_risk = total_reduction_pct > risk_threshold
    risk_warning = f"累计降幅>{risk_threshold}%，可能触发排名下滑。建议分阶段执行，每阶段后观察3-5天自然位变化。" if has_nonlinear_risk else None
    
    return {
        'algoVersion': ALGO_VERSION,
        'currentAdRatio': current_ad_ratio,
        'targetAdRatio': target_ad_ratio,
        'breakEvenAdRatio': break_even_ad_ratio,
        'needReduce': need_reduce,
        'gap': gap,
        'adDependency': ad_dependency,
        'phase1': {
            'wasteList': phase1_waste_list,
            'totalSavings': phase1_total_savings,
            'ratioReduction': phase1_ratio_reduction,
            'afterRatio': after_phase1_ratio,
            'actions': phase1_actions,
            'salesImpactAssumption': 'Phase1针对"无意义消耗"，理论上这些花费对销量贡献极低或为零，因此砍掉后销量影响应<5%'
        },
        'phase2': {
            'gap': phase2_gap,
            'plan': phase2_plan,
            'weeksNeeded': len(phase2_plan)
        },
        'impact': {
            'perPointPct': impact_per_point,
            'totalPct': sales_impact,
            'formula': '每降1%广告占比 → 销量降 (广告依赖度×系数)%'
        },
        'riskThreshold': risk_threshold,
        'hasNonlinearRisk': has_nonlinear_risk,
        'riskWarning': risk_warning
    }


def calc_inventory(skus, params):
    """计算库存指标"""
    lead_time = params.get('lead_time_days', 35)
    safety_days = params.get('safety_days', 30)
    target_cover = params.get('target_cover_days', 90)
    low_threshold = params.get('low_stock_threshold', 7)
    over_threshold = params.get('overstock_threshold', 120)
    
    result = []
    for sku in skus:
        ful = sku.get('ful', 0)
        inb = sku.get('inb', 0)
        rsv = sku.get('rsv', 0)
        du = sku.get('du', 0)
        
        if du <= 0:
            result.append({
                'sku': sku['sku'],
                'sellableDOS': None,
                'totalDOS': None,
                'stockoutGap': None,
                'status': 'no-sales',
                'overstockRisk': False,
                'ropUnits': 0,
                'targetUnits': 0,
                'availableUnits': 0,
                'orderQty': 0
            })
            continue
        
        sellable_dos = ful / du
        total_dos = (ful + inb - rsv) / du
        stockout_gap = max(0, lead_time - sellable_dos)
        
        if sellable_dos < low_threshold:
            status = 'critical'
        elif sellable_dos < lead_time:
            status = 'reorder-now'
        elif sellable_dos < 15:
            status = 'watch'
        else:
            status = 'healthy'
        
        overstock_risk = total_dos > over_threshold
        rop_units = (lead_time + safety_days) * du
        target_units = target_cover * du
        available_units = ful + inb - rsv
        order_qty = max(0, target_units - available_units)
        
        result.append({
            'sku': sku['sku'],
            'sellableDOS': round(sellable_dos, 1),
            'totalDOS': round(total_dos, 1),
            'stockoutGap': round(stockout_gap, 1),
            'status': status,
            'overstockRisk': overstock_risk,
            'ropUnits': round(rop_units, 0),
            'targetUnits': round(target_units, 0),
            'availableUnits': round(available_units, 0),
            'orderQty': round(order_qty, 0)
        })
    
    return result


def generate_diagnostics(skus, params):
    """生成SKU诊断建议"""
    lead_time = params.get('lead_time_days', 35)
    low_threshold = params.get('low_stock_threshold', 7)
    
    diagnostics = []
    for sku in skus:
        issues = []
        actions = []
        stop_loss = []
        is_healthy = True
        
        # 计算库存指标
        du = sku.get('du', 0)
        ful = sku.get('ful', 0)
        sellable_dos = ful / du if du > 0 else None
        
        # 库存风险
        if sellable_dos is not None and sellable_dos < low_threshold:
            issues.append({'type': 'critical', 'text': f"可售库存仅{sellable_dos:.1f}天，低于{low_threshold}天阈值"})
            actions.append({'priority': 0, 'text': '【紧急】立即补货或调拨', 'condition': '库存恢复前不做其他优化'})
            is_healthy = False
        
        # 定价毛利问题
        if sku['pm'] < 0:
            issues.append({'type': 'critical', 'text': f"定价毛利为负({sku['pm']*100:.1f}%)"})
            is_healthy = False
            actions.append({'priority': 1, 'text': '【诊断】检查成本结构', 'condition': '定位主要成本问题'})
        
        # 广告占比问题
        if sku['ar'] > sku['pm'] and sku['adSpend'] > 0:
            issues.append({'type': 'critical', 'text': f"广告占比({sku['ar']*100:.1f}%)超过毛利率({sku['pm']*100:.1f}%)"})
            is_healthy = False
            actions.append({'priority': 1, 'text': '【立即】执行Phase1砍无意义消耗', 'condition': '先砍ACOS>200%的词'})
        
        # 广告贡献
        ad_contrib = sku['adSales'] * sku['pm'] - sku['adSpend']
        if ad_contrib < 0 and sku['adSpend'] > 50:
            issues.append({'type': 'warning', 'text': f"广告贡献利润为负(${ad_contrib:.0f})"})
            actions.append({'priority': 2, 'text': '【优化】否定ACOS>50%词，降长尾竞价20%', 'condition': '2周后复盘效果'})
        
        # 四象限分类
        if sku['pm'] > 0 and ad_contrib >= 0:
            quadrant = 'star'
        elif sku['pm'] > 0 and ad_contrib < 0:
            quadrant = 'dog'
        elif sku['pm'] <= 0 and ad_contrib >= 0:
            quadrant = 'question'
        else:
            quadrant = 'eliminate'
        
        if quadrant == 'eliminate':
            actions.append({'priority': 1, 'text': '【启动退出】定价亏+广告亏，双重问题', 'condition': '除非有战略价值'})
            stop_loss.append('立即停止补货')
            is_healthy = False
        
        actions.sort(key=lambda x: x['priority'])
        
        diagnostics.append({
            'sku': sku['sku'],
            'quadrant': quadrant,
            'adContrib': round(ad_contrib, 2),
            'issues': issues,
            'actions': actions,
            'stopLoss': stop_loss,
            'isHealthy': is_healthy
        })
    
    return diagnostics


def parse_sheet(xl, name, skip):
    """解析Excel工作表"""
    if name not in xl.sheet_names:
        return None
    df = pd.read_excel(xl, sheet_name=name, header=None)
    return df.iloc[skip:] if len(df) > skip else df


def safe_float(val):
    """安全转换为浮点数"""
    try:
        if pd.isna(val):
            return 0
        return float(val)
    except:
        return 0
