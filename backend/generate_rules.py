"""Generate validation rules for all fillable zones across all templates.

Reads every fillable annotation, classifies the zone by analyzing the paragraph
text context, then updates the DB with appropriate field_name, min/max_chars,
allowed_chars, regex, and allowed_values.

Run: uv run python generate_rules.py
"""

import re
import json
from database import get_connection
from services.parser import DocxParser


def classify(text_before, text_after, full_text, paragraph_index, is_table_cell, is_zero_width):
    """Classify a fillable zone and return a rules dict."""
    R = {
        "field_name": "",
        "required": True,
        "min_chars": 0,
        "max_chars": 9999,
        "allowed_chars": "any",
        "regex": "",
        "allowed_values": [],
        "match_field": ""
    }

    tb = text_before.strip()
    ta = text_after  # shorthand

    def set_field(name, **kw):
        R["field_name"] = name
        for k, v in kw.items():
            if k in R:
                R[k] = v

    # ---- Signature / zero-width zones ----
    if is_zero_width:
        prefix = tb.rstrip("：:").strip()
        if "甲方（盖章）" in prefix:
            set_field("甲方盖章处")
            return R
        if "乙方（盖章）" in prefix:
            set_field("乙方盖章处")
            return R
        if "甲方（委托方）" in prefix:
            set_field("甲方签章处")
            return R
        if "乙方（服务方）" in prefix:
            set_field("乙方签章处")
            return R
        if "甲方（出租方）" in prefix:
            set_field("甲方签章处")
            return R
        if "乙方（承租方）" in prefix:
            set_field("乙方签章处")
            return R
        if "甲方（发包方）" in prefix:
            set_field("甲方签章处")
            return R
        if "乙方（承包方）" in prefix:
            set_field("乙方签章处")
            return R
        if "法定代表人/授权代表" in prefix:
            party = "甲方" if "甲方" in tb else ("乙方" if "乙方" in tb else "")
            set_field(f"{party}法定代表人/授权代表签字" if party else "法定代表人/授权代表签字")
            return R
        if "法定代表人/负责人" in prefix:
            party = "甲方" if "甲方" in tb else ("乙方" if "乙方" in tb else "")
            set_field(f"{party}法定代表人/负责人签字" if party else "法定代表人/负责人签字")
            return R
        if "法定代表人" in prefix:
            party = "甲方" if "甲方" in tb else ("乙方" if "乙方" in tb else "")
            set_field(f"{party}法定代表人签字" if party else "法定代表人签字")
            return R
        if "授权代理人" in prefix:
            party = "甲方" if "甲方" in tb else ("乙方" if "乙方" in tb else "")
            set_field(f"{party}授权代理人签字" if party else "授权代理人签字")
            return R
        if "盖章" in prefix:
            set_field("盖章处")
            return R
        set_field("签章处")
        return R

    # ---- Determine party context ----
    party = ""
    if "甲方" in tb:
        party = "甲方"
    elif "乙方" in tb:
        party = "乙方"

    # ---- What character immediately follows the fillable zone? ----
    after1 = ta[:1] if ta else ""
    after2 = ta[:2] if len(ta) >= 2 else ""
    after3 = ta[:3] if len(ta) >= 3 else ""

    # =================================================================
    # DATE FIELDS: ____年 / ____月 / ____日
    # =================================================================
    if after1 == "年":
        # Duration year (有效期为____年) vs date year
        if re.search(r'有效期为?\s*$', tb[-20:]):
            set_field("有效期（年）", allowed_chars="number", min_chars=1, max_chars=2)
            return R
        if "服务期限为" in tb[-20:]:
            set_field("服务期限（年）", allowed_chars="number", min_chars=1, max_chars=2)
            return R
        if "期限为" in tb[-10:]:
            set_field("期限（年）", allowed_chars="number", min_chars=1, max_chars=2)
            return R
        # Date year: check 自/至 context in recent text
        if re.search(r'自\s*$', tb[-10:]):
            set_field(f"{party}开始年" if party else "开始年", allowed_chars="number", min_chars=4, max_chars=4)
            return R
        if re.search(r'至\s*$', tb[-10:]):
            set_field(f"{party}结束年" if party else "结束年", allowed_chars="number", min_chars=4, max_chars=4)
            return R
        # Fallback: count years before
        yrs_before = full_text[:len(text_before)].count("年")
        if yrs_before == 0:
            set_field(f"{party}开始年" if party else "开始年", allowed_chars="number", min_chars=4, max_chars=4)
        elif yrs_before >= 2:
            set_field(f"{party}结束年" if party else "结束年", allowed_chars="number", min_chars=4, max_chars=4)
        else:
            set_field(f"{party}年" if party else "年", allowed_chars="number", min_chars=4, max_chars=4)
        return R

    if after1 == "月":
        if re.search(r'自\s*$', tb[-10:]):
            set_field(f"{party}开始月" if party else "开始月", allowed_chars="number", min_chars=1, max_chars=2)
            return R
        if re.search(r'至\s*$', tb[-10:]):
            set_field(f"{party}结束月" if party else "结束月", allowed_chars="number", min_chars=1, max_chars=2)
            return R
        mos_before = full_text[:len(text_before)].count("月")
        if mos_before == 0:
            set_field(f"{party}开始月" if party else "开始月", allowed_chars="number", min_chars=1, max_chars=2)
        elif mos_before >= 2:
            set_field(f"{party}结束月" if party else "结束月", allowed_chars="number", min_chars=1, max_chars=2)
        else:
            set_field(f"{party}月" if party else "月", allowed_chars="number", min_chars=1, max_chars=2)
        return R

    if after1 == "日":
        if re.search(r'提前\s*$', tb[-10:]):
            set_field("提前通知天数", allowed_chars="number", min_chars=1, max_chars=3)
            return R
        if re.search(r'自\s*$', tb[-10:]):
            set_field(f"{party}开始日" if party else "开始日", allowed_chars="number", min_chars=1, max_chars=2)
            return R
        if re.search(r'至\s*$', tb[-10:]):
            set_field(f"{party}结束日" if party else "结束日", allowed_chars="number", min_chars=1, max_chars=2)
            return R
        days_before = full_text[:len(text_before)].count("日")
        if days_before == 0:
            set_field(f"{party}开始日" if party else "开始日", allowed_chars="number", min_chars=1, max_chars=2)
        elif days_before >= 3:
            set_field(f"{party}结束日" if party else "结束日", allowed_chars="number", min_chars=1, max_chars=2)
        else:
            set_field(f"{party}日" if party else "日", allowed_chars="number", min_chars=1, max_chars=2)
        return R

    # =================================================================
    # PERCENT: ____%
    # =================================================================
    if after1 == "%":
        bt = tb[-40:]  # look at recent context
        if "税率" in bt:
            set_field("增值税税率(%)", allowed_chars="number", min_chars=1, max_chars=2)
        elif "接通率" in bt:
            set_field("接通率指标(%)", allowed_chars="number", min_chars=1, max_chars=3)
        elif "满意度" in bt:
            set_field("客户满意度指标(%)", allowed_chars="number", min_chars=1, max_chars=3)
        elif "流失率" in bt:
            set_field("人员流失率指标(%)", allowed_chars="number", min_chars=1, max_chars=3)
        elif "利润率" in bt:
            set_field("利润率(%)", allowed_chars="number", min_chars=1, max_chars=3)
        elif re.search(r'(预付款|进度款|尾款).*总费用的', bt):
            set_field("支付比例(%)", allowed_chars="number", min_chars=1, max_chars=3)
        elif "支付总费用的" in bt:
            set_field("支付比例(%)", allowed_chars="number", min_chars=1, max_chars=3)
        elif "退工" in bt or "退回" in bt:
            set_field("退工比例(%)", allowed_chars="number", min_chars=1, max_chars=3)
        elif "违约金" in bt or "租金总额的" in bt:
            set_field("违约金比例(%)", allowed_chars="number", min_chars=1, max_chars=3)
        elif "不超过当期" in bt:
            set_field("退工比例(%)", allowed_chars="number", min_chars=1, max_chars=3)
        else:
            set_field(f"{party}百分比(%)" if party else "百分比(%)", allowed_chars="number", min_chars=1, max_chars=3)
        return R

    # =================================================================
    # SPECIFIC TEXT-BASED LABEL MATCHING (most specific first)
    # =================================================================

    # Party name: exact prefix ending with "甲方/乙方（role）："
    m = re.match(r'^(甲方|乙方)（([^）]*)）[：:]?\s*$', tb)
    if m:
        set_field(f"{m.group(1)}名称（{m.group(2)}）",
                  allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        return R

    # 统一社会信用代码/身份证号 (before plain USCC)
    if re.search(r'统一社会信用代码\s*/\s*身份证号[：:]?\s*$', tb):
        set_field(f"{party}统一社会信用代码/身份证号" if party else "统一社会信用代码/身份证号",
                  allowed_chars="alphanumeric", min_chars=15, max_chars=18)
        return R

    # 统一社会信用代码
    if re.search(r'统一社会信用代码[：:]?\s*$', tb):
        set_field(f"{party}统一社会信用代码" if party else "统一社会信用代码",
                  allowed_chars="alphanumeric", min_chars=18, max_chars=18)
        return R

    # 注册地址
    if re.search(r'注册地址\s*[：:]?\s*$', tb):
        set_field(f"{party}注册地址" if party else "注册地址",
                  allowed_chars="any", min_chars=5, max_chars=100)
        return R

    # 住所
    if re.search(r'住所[：:]?\s*$', tb):
        set_field(f"{party}住所" if party else "住所",
                  allowed_chars="any", min_chars=5, max_chars=100)
        return R

    # 地址
    if re.search(r'地址[：:]?\s*$', tb):
        set_field(f"{party}地址" if party else "地址",
                  allowed_chars="any", min_chars=5, max_chars=100)
        return R

    # 法定代表人/负责人
    if re.search(r'法定代表人\s*/\s*负责人[：:]?\s*$', tb):
        set_field(f"{party}法定代表人/负责人" if party else "法定代表人/负责人",
                  allowed_chars="chinese", min_chars=2, max_chars=20)
        return R

    # 法定代表人 (standalone, NOT followed by /负责人 or /授权代表)
    if re.search(r'法定代表人[：:]?\s*$', tb):
        set_field(f"{party}法定代表人" if party else "法定代表人",
                  allowed_chars="chinese", min_chars=2, max_chars=20)
        return R

    # 联系人
    if re.search(r'联系人[：:]?\s*$', tb):
        set_field(f"{party}联系人" if party else "联系人",
                  allowed_chars="chinese", min_chars=2, max_chars=10)
        return R

    # 协调人-姓名 (must come before 联系电话)
    if re.search(r'协调人[：:]\s*姓名[：:]\s*$', tb):
        set_field(f"{party}协调人姓名" if party else "协调人姓名",
                  allowed_chars="chinese", min_chars=2, max_chars=10)
        return R

    # 协调人-电话 (after 联系电话 in a coordinator line)
    if re.search(r'协调人.*联系电话[：:]\s*$', tb):
        role = f"{party}协调人电话" if party else "协调人电话"
        set_field(role, allowed_chars="number", min_chars=7, max_chars=13)
        return R

    # 协调人-邮箱
    if re.search(r'协调人.*电子邮箱[：:]\s*$', tb):
        role = f"{party}协调人邮箱" if party else "协调人邮箱"
        set_field(role, allowed_chars="any", min_chars=6, max_chars=50)
        return R

    # Generic coordinator pattern in combined line like "甲方协调人：姓名：___ 联系电话：___ 电子邮箱：___"
    # after 姓名 in coordinator line
    if "协调人" in tb and "姓名" in tb[-20:]:
        set_field(f"{party}协调人姓名" if party else "协调人姓名",
                  allowed_chars="chinese", min_chars=2, max_chars=10)
        return R
    # after 联系电话 in coordinator line
    if "协调人" in tb and "联系电话" in tb[-20:]:
        role = f"{party}协调人电话" if party else "协调人电话"
        set_field(role, allowed_chars="number", min_chars=7, max_chars=13)
        return R
    # after 电子邮箱 in coordinator line
    if "协调人" in tb and "电子邮箱" in tb[-20:]:
        role = f"{party}协调人邮箱" if party else "协调人邮箱"
        set_field(role, allowed_chars="any", min_chars=6, max_chars=50)
        return R

    # 联系电话
    if re.search(r'联系电话[：:]\s*$', tb):
        set_field(f"{party}联系电话" if party else "联系电话",
                  allowed_chars="number", min_chars=7, max_chars=13)
        return R

    # 电子邮箱 / 邮箱
    if re.search(r'(电子)?邮箱[：:]\s*$', tb):
        set_field(f"{party}电子邮箱" if party else "电子邮箱",
                  allowed_chars="any", min_chars=6, max_chars=50)
        return R

    # 项目负责人 (with or without colon)
    if re.search(r'项目负责人[：:]?\s*$', tb):
        set_field("项目负责人姓名", allowed_chars="chinese", min_chars=2, max_chars=10)
        return R

    # 项目负责人联系方式
    if re.search(r'项目负责人.*联系方式[：:]?\s*$', tb):
        set_field("项目负责人电话", allowed_chars="number", min_chars=7, max_chars=13)
        return R

    # 联系方式 (standalone, after project manager name fillable)
    if re.search(r'联系方式[：:]?\s*$', tb):
        set_field("项目负责人电话", allowed_chars="number", min_chars=7, max_chars=13)
        return R

    # 指定专人/项目对接人
    if re.search(r'(指定专人|项目对接人)[：:]?\s*$', tb):
        set_field("项目对接人姓名", allowed_chars="chinese", min_chars=2, max_chars=10)
        return R

    # 资质证明
    if re.search(r'资质证明[：:]?\s*$', tb):
        set_field(f"{party}资质证明" if party else "资质证明",
                  allowed_chars="any", min_chars=2, max_chars=100)
        return R

    # 开户名称 / 账户名称 / 开户单位 / 户名
    if re.search(r'(开户名称|账户名称|开户单位|户名)[：:]\s*$', tb):
        set_field(f"{party}开户名称" if party else "开户名称",
                  allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        return R

    # 开户银行 / 开户行
    if re.search(r'(开户银行|开户行)[：:]\s*$', tb):
        set_field(f"{party}开户银行" if party else "开户银行",
                  allowed_chars="alphanumeric", min_chars=4, max_chars=30)
        return R

    # 银行账号 (before generic 账号)
    if re.search(r'银行账号[：:]\s*$', tb):
        set_field(f"{party}银行账号" if party else "银行账号",
                  allowed_chars="number", min_chars=8, max_chars=30)
        return R

    # 账号 (standalone, for 咨询服务 and similar)
    if re.search(r'(?<!信用)账号[：:]\s*$', tb):
        set_field(f"{party}银行账号" if party else "银行账号",
                  allowed_chars="number", min_chars=8, max_chars=30)
        return R

    # 税号
    if re.search(r'税号[：:]\s*$', tb):
        set_field(f"{party}税号" if party else "税号",
                  allowed_chars="alphanumeric", min_chars=15, max_chars=20)
        return R

    # 理赔款专用账户
    if "理赔款专用账户" in tb:
        set_field("理赔款专用账户信息", allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        return R

    # 保险产品类型 (check BEFORE 合作范围 since both can appear in same paragraph)
    if "保险产品类型包括" in tb:
        set_field("保险产品类型", allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        return R

    # 合作范围 (first blank in that paragraph)
    if "合作范围为" in tb:
        set_field("合作范围", allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        return R

    # 委托咨询事宜
    if re.search(r'甲方委托乙方就\s*$', tb):
        set_field("咨询服务事项", allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        return R

    # 服务区域
    if re.search(r'服务区域[为：:]\s*$', tb):
        set_field("服务区域", allowed_chars="alphanumeric", min_chars=2, max_chars=20)
        return R

    # 车辆使用范围
    if re.search(r'(车辆)?使用范围[：:]\s*$', tb):
        set_field("车辆使用范围", allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        return R

    # =================================================================
    # MONEY / FEE FIELDS
    # =================================================================

    # 服务单价：____元/辆 (before generic "元" check)
    if re.search(r'服务单价[：:]?\s*$', tb):
        if "元 / 辆" in ta[:10] or "元/辆" in ta[:10]:
            set_field("单价（元/辆）", allowed_chars="number", min_chars=1, max_chars=10)
        elif "元 / 次" in ta[:10] or "元/次" in ta[:10]:
            set_field("单价（元/次）", allowed_chars="number", min_chars=1, max_chars=10)
        else:
            set_field("单价（元）", allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # Generic 单价 without colon (table rows)
    if re.search(r'单价[）)]?\s*[：:]?\s*$', tb[-10:]):
        set_field("单价（元）", allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # 每笔____元 (承保/未承保)
    m = re.search(r'(承保|未承保)业务每笔\s*$', tb)
    if m:
        label = f"{m.group(1)}业务单价（元）"
        set_field(label, allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # 每件案件____元
    if re.search(r'每件案件\s*$', tb):
        set_field("案件单价（元）", allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # 每户____元
    if re.search(r'每户\s*$', tb):
        set_field("客户单价（元）", allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # 6年内车辆 vs 6年以上车辆 ____元/次
    if "6 年内车辆" in tb[-20:] or "6年内车辆" in tb[-20:]:
        set_field("6年内车辆单价（元/次）", allowed_chars="number", min_chars=1, max_chars=10)
        return R
    if "6 年以上车辆" in tb[-20:] or "6年以上车辆" in tb[-20:]:
        set_field("6年以上车辆单价（元/次）", allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # 元/人/月 patterns
    if "管理人员坐席" in tb[-20:]:
        set_field("管理人员坐席单价（元/人/月）", allowed_chars="number", min_chars=1, max_chars=10)
        return R
    if "一线服务坐席" in tb[-20:] or "一线坐席" in tb[-15:]:
        set_field("一线坐席单价（元/人/月）", allowed_chars="number", min_chars=1, max_chars=10)
        return R
    if re.search(r'(管理服务费|按服务人员数量).*标准为\s*$', tb[-30:]):
        set_field("管理服务费（元/人/月）", allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # 元/人/天
    if re.search(r'(培训补贴|岗前培训).*标准为\s*$', tb[-30:]):
        set_field("培训补贴标准（元/人/天）", allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # 元/人/工作日
    if re.search(r'元\s*/\s*人\s*/\s*工作日', tb[-20:]):
        set_field("人天单价（元）", allowed_chars="number", min_chars=1, max_chars=10)
        return R
    if re.search(r'元\s*/\s*人\s*/\s*工作日', ta[:20]):
        set_field("人天单价（元）", allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # 夜班补贴
    if "夜班补贴标准为" in tb[-20:] or "夜班补贴" in tb[-15:]:
        set_field("夜班补贴（元/人次）", allowed_chars="number", min_chars=1, max_chars=6)
        return R

    # 人民币______万元
    if re.search(r'人民币\s*$', tb[-10:]):
        if "万元" in ta[:5]:
            set_field("年费金额（万元）", allowed_chars="number", min_chars=1, max_chars=10)
        elif "元" in ta[:1]:
            if "固定总价" in tb:
                set_field("固定总价（元）", allowed_chars="number", min_chars=1, max_chars=12)
            elif "月租金" in tb:
                set_field("月租金（元）", allowed_chars="number", min_chars=1, max_chars=12)
            else:
                set_field("金额（元）", allowed_chars="number", min_chars=1, max_chars=12)
        else:
            set_field("金额（元）", allowed_chars="number", min_chars=1, max_chars=12)
        return R

    # Generic: ____元 followed by 元 or 万元
    if re.search(r'[元]\s*$', tb[-5:]) and "人民币" not in tb[-10:]:
        if "万元" in ta[:3]:
            set_field("金额（万元）", allowed_chars="number", min_chars=1, max_chars=10)
        else:
            set_field("金额（元）", allowed_chars="number", min_chars=1, max_chars=12)
        return R

    # 大写
    if re.search(r'大写[）)]?\s*[：:]?\s*$', tb[-10:]):
        set_field("金额大写", allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        return R

    # 小写 or ¥
    if re.search(r'(小写|¥)\s*[：:]?\s*$', tb[-10:]):
        set_field("金额小写", allowed_chars="number", min_chars=1, max_chars=12)
        return R

    # 合计大写/小写
    if "人民币（大写）" in tb[-20:]:
        set_field("合计金额（大写）", allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        return R
    if "（小写）" in tb[-20:] and "¥" in tb:
        set_field("合计金额（小写）", allowed_chars="number", min_chars=1, max_chars=12)
        return R

    # =================================================================
    # VEHICLE FIELDS
    # =================================================================
    if re.search(r'车辆品牌[：:]\s*$', tb):
        set_field("车辆品牌", allowed_chars="alphanumeric", min_chars=1, max_chars=20)
        return R
    if re.search(r'车型规格[：:]\s*$', tb):
        set_field("车型规格", allowed_chars="alphanumeric", min_chars=1, max_chars=30)
        return R
    if re.search(r'车牌号[码]?[：:]\s*$', tb):
        set_field("车牌号码", allowed_chars="alphanumeric", min_chars=7, max_chars=10)
        return R
    if re.search(r'车架号[码]?[：:]\s*$', tb):
        set_field("车架号码", allowed_chars="alphanumeric", min_chars=17, max_chars=17)
        return R
    if re.search(r'车辆颜色[：:]\s*$', tb):
        set_field("车辆颜色", allowed_chars="chinese", min_chars=1, max_chars=10)
        return R
    if re.search(r'车辆状况[：:]\s*$', tb):
        set_field("车辆状况", allowed_chars="alphanumeric", min_chars=1, max_chars=20)
        return R

    # =================================================================
    # SERVICE ITEM TABLE FIELDS (网络推广 / 汽车 / 咨询)
    # =================================================================
    if re.search(r'服务项目[：:]\s*$', tb) or re.search(r'服务项目_*$', tb):
        set_field("服务项目名称", allowed_chars="alphanumeric", min_chars=1, max_chars=30)
        return R
    if re.search(r'服务类别[：:]\s*$', tb):
        set_field("服务类别", allowed_chars="alphanumeric", min_chars=1, max_chars=20)
        return R
    if re.search(r'服务内容说明[：:]\s*$', tb):
        set_field("服务内容说明", allowed_chars="any", min_chars=1, max_chars=100)
        return R
    if re.search(r'计价单位[：:]\s*$', tb):
        set_field("计价单位", allowed_chars="chinese", min_chars=1, max_chars=10)
        return R
    if re.search(r'备注[：:]\s*$', tb):
        set_field("备注", allowed_chars="any", min_chars=0, max_chars=100, required=False)
        return R

    # 计费单位
    if re.search(r'计费单位[：:]\s*$', tb):
        set_field("计费单位", allowed_chars="chinese", min_chars=1, max_chars=10)
        return R

    # 服务内容及标准
    if re.search(r'服务内容及标准[：:]\s*$', tb):
        set_field("服务内容及标准", allowed_chars="any", min_chars=2, max_chars=100)
        return R

    # 服务范围 (generic, after service content)
    if re.search(r'服务范围[：:]\s*$', tb):
        set_field("服务范围", allowed_chars="alphanumeric", min_chars=2, max_chars=30)
        return R

    # 服务效果考核指标
    if re.search(r'(考核指标|具体服务效果考核)', tb[-20:]):
        set_field("服务效果考核指标", allowed_chars="any", min_chars=2, max_chars=200)
        return R

    # 服务验收标准
    if re.search(r'(服务)?验收标准[：:]?\s*$', tb[-20:]):
        set_field("服务验收标准", allowed_chars="any", min_chars=2, max_chars=200)
        return R

    # =================================================================
    # NUMBER-ONLY FIELDS (days, count, etc.)
    # =================================================================

    # 个工作日内 (days)
    if ta.startswith("个工作日内") or ta.startswith("个工作日"):
        if "预付款" in tb:
            set_field("预付款支付期限（工作日）", allowed_chars="number", min_chars=1, max_chars=3)
        elif "进度款" in tb:
            set_field("进度款支付期限（工作日）", allowed_chars="number", min_chars=1, max_chars=3)
        elif "尾款" in tb:
            set_field("尾款支付期限（工作日）", allowed_chars="number", min_chars=1, max_chars=3)
        elif "核对确认" in tb:
            set_field("核对确认期限（工作日）", allowed_chars="number", min_chars=1, max_chars=3)
        elif "核实" in tb:
            set_field("核实回复期限（工作日）", allowed_chars="number", min_chars=1, max_chars=3)
        elif "开具" in tb or "开票" in tb:
            set_field("开票期限（工作日）", allowed_chars="number", min_chars=1, max_chars=3)
        elif "费用结算确认" in tb or "结算确认" in tb:
            set_field("开票期限（工作日）", allowed_chars="number", min_chars=1, max_chars=3)
        elif "提前" in tb:
            set_field("提前通知工作日数", allowed_chars="number", min_chars=1, max_chars=3)
        else:
            set_field("工作日数", allowed_chars="number", min_chars=1, max_chars=3)
        return R

    # 提前N日/工作日
    if re.search(r'提前\s*$', tb[-10:]):
        if "工作日" in ta:
            set_field("提前通知工作日数", allowed_chars="number", min_chars=1, max_chars=3)
        else:
            set_field("提前通知天数", allowed_chars="number", min_chars=1, max_chars=3)
        return R

    # 连续工作满N个月
    if re.search(r'连续工作满\s*$', tb[-10:]):
        set_field("连续工作月数", allowed_chars="number", min_chars=1, max_chars=2)
        return R

    # 共计N个月 (total duration)
    if re.search(r'共计\s*$', tb[-10:]):
        set_field("租赁期限（月）", allowed_chars="number", min_chars=1, max_chars=2)
        return R

    # /___8__小时 (daily standard hours)
    if re.search(r'/\s*$', tb[-5:]) and "排班工时" in tb:
        set_field("日标准工时（小时）", allowed_chars="number", min_chars=1, max_chars=2)
        return R

    # 服务公里范围 (市区指定____公里内)
    if "公里" in ta[:10] or re.search(r'指定\s*$', tb[-10:]):
        set_field("服务公里范围", allowed_chars="number", min_chars=1, max_chars=5)
        return R

    # 纸质版/电子版份数
    if "纸质版" in tb[-10:] and ta.startswith("份"):
        set_field("纸质报告份数", allowed_chars="number", min_chars=1, max_chars=2)
        return R
    if "电子版" in tb[-10:] and ta.startswith("份"):
        set_field("电子报告份数", allowed_chars="number", min_chars=1, max_chars=2)
        return R

    # 费用计算方式编号 (第____种)
    if re.search(r'第\s*$', tb[-5:]):
        set_field("费用计算方式编号", allowed_chars="number", min_chars=1, max_chars=1,
                  allowed_values=["1", "2", "3"])
        return R

    # 增值税税率 (6% but split across zones)
    if re.search(r'增值税税率为\s*$', tb[-15:]):
        set_field("增值税税率(%)", allowed_chars="number", min_chars=1, max_chars=2)
        return R

    # 税金承担方 (由__乙_方承担)
    if re.search(r'由\s*$', tb[-5:]) and "承担" in ta[:10]:
        set_field("税金承担方", allowed_chars="chinese", min_chars=1, max_chars=10,
                  allowed_values=["甲方", "乙方"])
        return R

    # =================================================================
    # OUTSOURCING-SPECIFIC (Template 11)
    # =================================================================

    # 外包: 承接甲方_____人力___业务
    if "承接甲方" in tb[-15:]:
        if "人力" in ta[:10]:
            set_field("外包人员数量", allowed_chars="number", min_chars=1, max_chars=5)
        else:
            set_field("外包业务类型", allowed_chars="chinese", min_chars=1, max_chars=10)
        return R

    # KPI indicators
    if "接通率" in tb[-20:]:
        set_field("接通率指标(%)", allowed_chars="number", min_chars=1, max_chars=3)
        return R
    if "质检平均分" in tb[-20:]:
        set_field("质检平均分指标", allowed_chars="number", min_chars=1, max_chars=3)
        return R
    if "满意度" in tb[-20:]:
        set_field("客户满意度指标(%)", allowed_chars="number", min_chars=1, max_chars=3)
        return R
    if "CPD" in tb[-20:] or "人均产能" in tb[-20:]:
        set_field("CPD（人均产能）指标", allowed_chars="number", min_chars=1, max_chars=5)
        return R
    if "流失率" in tb[-20:]:
        set_field("人员流失率指标(%)", allowed_chars="number", min_chars=1, max_chars=3)
        return R

    # 违约金金额
    if "违约金人民币" in tb[-15:]:
        set_field("违约金金额（元）", allowed_chars="number", min_chars=1, max_chars=10)
        return R

    # 具体标准为
    if "具体标准为" in tb[-15:]:
        set_field("其他服务费用标准", allowed_chars="any", min_chars=2, max_chars=100)
        return R

    # 绩效挂钩计费
    if "绩效挂钩" in tb[-20:] or "服务效果按如下标准" in tb[-20:]:
        set_field("绩效计费标准", allowed_chars="any", min_chars=2, max_chars=100)
        return R

    # 其他计价方式
    if "其他计价方式" in tb[-20:]:
        set_field("其他计价方式说明", allowed_chars="any", min_chars=2, max_chars=100)
        return R

    # 进度款阶段名称
    if "进度款" in tb[-20:] and re.search(r'[：:]\s*$', tb[-3:]):
        set_field("进度款阶段名称", allowed_chars="alphanumeric", min_chars=2, max_chars=30)
        return R

    # 预付款金额
    if "预付款" in tb and "即人民币" in tb[-15:]:
        set_field("预付款金额（元）", allowed_chars="number", min_chars=1, max_chars=12)
        return R
    # 进度款金额
    if "进度款" in tb and "即人民币" in tb[-15:]:
        set_field("进度款金额（元）", allowed_chars="number", min_chars=1, max_chars=12)
        return R
    # 尾款金额
    if "尾款" in tb and "即人民币" in tb[-15:]:
        set_field("尾款金额（元）", allowed_chars="number", min_chars=1, max_chars=12)
        return R
    # 支付剩余费用即人民币
    if "剩余费用" in tb and "即人民币" in tb[-15:]:
        set_field("尾款金额（元）", allowed_chars="number", min_chars=1, max_chars=12)
        return R

    # =================================================================
    # CONTENT / DESCRIPTION FIELDS
    # =================================================================

    # All-underscore paragraph (standalone service content description)
    if re.match(r'^_+\s*[；;]?\s*$', full_text.strip()):
        set_field("服务内容描述", allowed_chars="any", min_chars=2, max_chars=200)
        return R

    if re.match(r'^_+$', full_text.strip()):
        set_field("服务内容描述", allowed_chars="any", min_chars=2, max_chars=200)
        return R

    # Other services paragraph: starts with underscores, has parenthetical hint
    if re.match(r'^_+$', tb) and "（" in ta:
        set_field("其他约定服务内容", allowed_chars="any", min_chars=2, max_chars=100)
        return R

    # =================================================================
    # FALLBACK
    # =================================================================
    # Try to derive field_name from the last label-like segment in text_before
    # Look for the last "XXX：" pattern
    labels = re.findall(r'([^\s：:]{2,12})[：:]\s*$', tb)
    if labels:
        clean = labels[-1].strip().rstrip(",，;；")
        # Apply basic rules based on the label
        if "名称" in clean:
            set_field(clean, allowed_chars="alphanumeric", min_chars=2, max_chars=50)
        elif "电话" in clean:
            set_field(clean, allowed_chars="number", min_chars=7, max_chars=13)
        elif "金额" in clean or "单价" in clean or "费用" in clean:
            set_field(clean, allowed_chars="number", min_chars=1, max_chars=12)
        elif "份数" in clean or "数量" in clean:
            set_field(clean, allowed_chars="number", min_chars=1, max_chars=3)
        else:
            set_field(clean)
        return R

    # Last resort
    set_field(f"段落{paragraph_index}")
    return R


def main():
    conn = get_connection()
    templates = conn.execute('SELECT id, name, file_path FROM templates ORDER BY id').fetchall()

    total_updated = 0
    for tpl in templates:
        tid = tpl['id']
        anns = conn.execute(
            "SELECT paragraph_index, start_char, end_char, zone_type, rules FROM annotations WHERE template_id = ? AND zone_type = 'fillable' ORDER BY paragraph_index, start_char",
            (tid,)
        ).fetchall()

        if not anns:
            continue

        paras = DocxParser.parse(tpl['file_path'])
        print(f"\n{'='*60}")
        print(f"Template ID={tid}: {tpl['name']} ({len(anns)} fillable zones)")
        print(f"{'='*60}")

        for a in anns:
            pi = a['paragraph_index']
            s = a['start_char']
            e = a['end_char']
            if pi >= len(paras):
                continue

            full_text = paras[pi]['text']
            text_before = full_text[:s]
            text_after = full_text[e:]
            is_table_cell = paras[pi].get('is_table_cell', False)
            is_zero_width = (s == e)

            R = classify(text_before, text_after, full_text, pi, is_table_cell, is_zero_width)

            zone_label = full_text[s:e] if s < e else "(zero-width)"
            print(f"  [{pi}:{s}:{e}] field={R['field_name']} "
                  f"chars={R['allowed_chars']} "
                  f"len=[{R['min_chars']},{R['max_chars']}] "
                  f"req={R['required']} "
                  f"val={R.get('allowed_values',[])} "
                  f"regex={R.get('regex','')[:30]} "
                  f"zone='{zone_label[:20]}'")

            conn.execute(
                "UPDATE annotations SET rules = ? WHERE template_id = ? AND paragraph_index = ? AND start_char = ? AND end_char = ?",
                (json.dumps(R, ensure_ascii=False), tid, pi, s, e)
            )
            total_updated += 1

        conn.commit()
        print(f"  -> Updated {len(anns)} annotations")

    conn.close()
    print(f"\n{'='*60}")
    print(f"Total annotations updated: {total_updated}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
