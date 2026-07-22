"""Create deterministic, synthetic development data for the purchasing workflow.

The equipment patterns are derived from the supplied historical whitelist workbook,
but employees, telephone numbers, suppliers, locations, reasons, timestamps, and
workflow events are synthetic. The script never deletes existing business data.
"""

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text

from app.config import Settings
from app.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    transaction_scope,
)

SEED_PREFIX = "dev-seed-v1"
REQUIREMENT_COUNT = 500
CURATED_COUNT = 240
BASE_TIME = datetime(2026, 7, 1, 1, 0)
MONEY = Decimal("0.01")

PRODUCTS = (
    (
        "机房环境",
        "精密空调",
        "空调主板",
        "佳力图",
        "DEV-AC-CTRL-050",
        "控制板组件",
        "块",
        "1725",
    ),
    (
        "机房环境",
        "精密空调",
        "空调电源模块",
        "英维克",
        "DEV-AC-PWR-048",
        "48V 电源模块",
        "个",
        "1580",
    ),
    (
        "电气",
        "UPS",
        "UPS功率模块",
        "科士达",
        "DEV-UPS-MOD-200K",
        "模块化 UPS 功率单元",
        "台",
        "17800",
    ),
    (
        "机房环境",
        "暖通系统",
        "阀门执行器控制板",
        "博雷",
        "DEV-ACT-230V",
        "电动执行器控制板",
        "块",
        "1020",
    ),
    (
        "机房环境",
        "暖通系统",
        "冷却塔轴承",
        "SKF",
        "DEV-BRG-6312-C3",
        "高温高速轴承",
        "个",
        "215",
    ),
    (
        "电气",
        "电源及配电",
        "保险丝",
        "HOLLY",
        "DEV-FUSE-4A",
        "低压快速熔断器",
        "只",
        "16",
    ),
    (
        "电气",
        "高压直流",
        "整流模块",
        "动力源",
        "DEV-RECT-240-15K",
        "高压直流整流单元",
        "个",
        "7100",
    ),
    (
        "电气",
        "蓄电池",
        "阀控式铅酸蓄电池",
        "GNB",
        "DEV-BAT-12V200",
        "12V 200Ah",
        "节",
        "2050",
    ),
    (
        "机房环境",
        "暖通系统",
        "压缩机",
        "日立",
        "DEV-COMP-440",
        "空调压缩机组件",
        "台",
        "4550",
    ),
    (
        "机房环境",
        "冷却塔",
        "冷却塔电机",
        "西门子",
        "DEV-MOTOR-55KW",
        "三相异步电机 55kW",
        "台",
        "23800",
    ),
    (
        "工器具",
        "维修工器具",
        "游标卡尺",
        "得力",
        "DEV-CALIPER-200",
        "0-200mm 数显",
        "把",
        "216",
    ),
    (
        "工器具",
        "维修工器具",
        "绝缘电工工具套装",
        "世达",
        "DEV-TOOLSET-1000V",
        "耐压 1000V",
        "套",
        "735",
    ),
    (
        "电气",
        "电源及配电",
        "服务器电源模块",
        "华为",
        "DEV-SRV-PWR-750W",
        "热插拔电源",
        "个",
        "315",
    ),
    (
        "机房环境",
        "冷水机组",
        "冷机膨胀阀",
        "约克",
        "DEV-TXV-075-11T",
        "制冷剂流量调节阀",
        "个",
        "4350",
    ),
    (
        "电气",
        "防雷系统",
        "后备防雷保护器",
        "施耐德",
        "DEV-SPD-65H",
        "浪涌后备保护",
        "个",
        "625",
    ),
    (
        "机房环境",
        "精密空调",
        "空调过滤网",
        "英维克",
        "DEV-FILTER-920-530",
        "G4 初效过滤",
        "片",
        "31",
    ),
    (
        "机房环境",
        "暖通系统",
        "空调风机",
        "ebmpapst",
        "DEV-FAN-355-EC",
        "EC 离心风机",
        "台",
        "1640",
    ),
    (
        "机房环境",
        "暖通系统",
        "冷却塔皮带",
        "Gates",
        "DEV-BELT-B155",
        "耐磨三角带",
        "根",
        "112",
    ),
    (
        "机房环境",
        "板式换热器",
        "板换密封条",
        "Alfa Laval",
        "DEV-GASKET-AR8",
        "耐高温密封胶条",
        "条",
        "118",
    ),
    (
        "弱电",
        "动环监控",
        "压力传感器",
        "西门子",
        "DEV-PRESS-16BAR",
        "0-16bar 变送器",
        "个",
        "645",
    ),
    (
        "弱电",
        "动环监控",
        "温湿度传感器",
        "霍尼韦尔",
        "DEV-TH-7080",
        "机房温湿度采集",
        "个",
        "930",
    ),
    (
        "弱电",
        "动环监控",
        "漏水检测绳",
        "祥为",
        "DEV-LEAK-20M",
        "20 米定位式检测",
        "根",
        "780",
    ),
    (
        "电气",
        "机柜配电",
        "智能PDU",
        "突破",
        "DEV-PDU-32A-24C",
        "32A 24 位远程计量",
        "根",
        "1980",
    ),
    (
        "电气",
        "蓄电池",
        "蓄电池监测模块",
        "华塑",
        "DEV-BMS-CELL",
        "单体电压内阻采集",
        "个",
        "348",
    ),
    (
        "网络",
        "核心网络",
        "万兆交换机",
        "华为",
        "DEV-SW-10G-24X",
        "24 口万兆光口",
        "台",
        "30900",
    ),
    (
        "网络",
        "接入网络",
        "千兆接入交换机",
        "新华三",
        "DEV-SW-GE-48P",
        "48 电口 4 光口",
        "台",
        "7350",
    ),
    (
        "网络",
        "光传输",
        "万兆光模块",
        "华为",
        "DEV-SFP-10G-LR",
        "单模 10km",
        "个",
        "925",
    ),
    (
        "网络",
        "综合布线",
        "LC-LC光纤跳线",
        "长飞",
        "DEV-OM4-LCLC-10M",
        "双芯多模 10 米",
        "根",
        "92",
    ),
    (
        "算力设备",
        "服务器",
        "机架式服务器",
        "浪潮",
        "DEV-SRV-2U-DUAL",
        "2U 双路机架服务器",
        "台",
        "72800",
    ),
    (
        "算力设备",
        "服务器",
        "服务器内存",
        "三星",
        "DEV-MEM-64G-3200",
        "64GB ECC RDIMM",
        "条",
        "1580",
    ),
    (
        "算力设备",
        "存储",
        "企业级固态硬盘",
        "英特尔",
        "DEV-NVME-3T84",
        "U.2 NVMe 3.84TB",
        "块",
        "6680",
    ),
    (
        "算力设备",
        "存储",
        "企业级机械硬盘",
        "希捷",
        "DEV-HDD-16T-72K",
        "SATA 16TB 7200rpm",
        "块",
        "2520",
    ),
    (
        "算力设备",
        "机柜",
        "标准服务器机柜",
        "图腾",
        "DEV-RACK-42U",
        "600x1200 42U",
        "台",
        "4580",
    ),
    (
        "弱电",
        "门禁系统",
        "门禁控制器",
        "海康威视",
        "DEV-ACS-4DOOR",
        "四门网络控制器",
        "台",
        "1960",
    ),
    (
        "弱电",
        "视频监控",
        "网络摄像机",
        "大华",
        "DEV-CAM-4MP-POE",
        "400 万像素 PoE",
        "台",
        "745",
    ),
    (
        "消防",
        "火灾报警",
        "点型感烟探测器",
        "海湾",
        "DEV-SMOKE-CODED",
        "智能编码型",
        "只",
        "108",
    ),
    (
        "消防",
        "气体灭火",
        "气体释放指示灯",
        "海湾",
        "DEV-GAS-LAMP-24V",
        "DC24V 壁挂式",
        "个",
        "182",
    ),
    (
        "机房环境",
        "环境监测",
        "精密空调温控器",
        "佳力图",
        "DEV-AC-TEMP-MODBUS",
        "Modbus 通讯",
        "个",
        "1490",
    ),
    (
        "电气",
        "电能监测",
        "智能电表",
        "施耐德",
        "DEV-METER-3P-MF",
        "三相多功能计量",
        "只",
        "2810",
    ),
    (
        "工器具",
        "测试仪表",
        "红外热像仪",
        "福禄克",
        "DEV-THERMAL-HAND",
        "便携式点检热像仪",
        "台",
        "18100",
    ),
)

LOCATIONS = tuple(
    f"{building}号楼{room}数据机房" for building in range(1, 10) for room in (101, 202, 303, 404)
)

REASONS = (
    "设备运行告警，经现场复核需更换故障部件",
    "月度巡检发现性能衰减，申请预防性更换",
    "备品备件低于安全库存，申请补充库存",
    "现有设备达到建议使用年限，申请计划性更新",
    "新增机柜上线，需要补充配套设备",
    "维保排查确认部件损坏，重启后故障仍存在",
    "为降低单点故障风险，申请配置现场备用件",
    "客户业务扩容，现有设备容量不足",
    "年度检修需要更换易损件并恢复冗余能力",
    "监控数据持续异常，申请更换并安排复测",
)

SUPPLIER_PREFIXES = (
    "华东智联",
    "金陵机电",
    "宁远数字",
    "启辰能源",
    "恒信暖通",
    "安澜科技",
    "云枢设备",
    "瑞达工程",
    "中科维保",
    "长江自动化",
    "星港网络",
    "联创机房",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate generation rules and print counts without connecting to MySQL.",
    )
    return parser.parse_args()


def build_employees() -> list[dict[str, object]]:
    employees: list[dict[str, object]] = []
    given_names = (
        "林晨",
        "周宁",
        "陈曦",
        "吴越",
        "赵清",
        "孙嘉",
        "徐舟",
        "高远",
        "郭一",
        "何安",
        "罗成",
        "郑言",
        "梁川",
        "宋乔",
        "唐睿",
        "许诺",
        "韩松",
        "冯启",
        "邓宇",
        "曹禾",
    )
    roles = (("REQUESTER", 60, "E"), ("APPROVER", 8, "A"), ("PURCHASER", 12, "P"))
    serial = 1
    for role, count, code in roles:
        for index in range(count):
            display_name = given_names[index % len(given_names)]
            display_suffix = index // len(given_names) + 1
            employees.append(
                {
                    "employee_no": f"DEV-{code}{index + 1:04d}",
                    "name": f"{display_name}{display_suffix}（测试）",
                    "phone": f"1300000{serial:04d}",
                    "role": role,
                }
            )
            serial += 1
    return employees


def build_suppliers() -> list[dict[str, str]]:
    return [
        {
            "supplier_name": f"{prefix}测试供应商{index + 1:02d}有限公司",
            "contact": f"测试联系人{index + 1:02d}",
            "phone": f"025-0000{index + 1:04d}",
            "level": ("A", "B", "C")[index % 3],
        }
        for index, prefix in enumerate(SUPPLIER_PREFIXES * 2)
    ]


def status_for(index: int) -> str:
    if index < 30:
        return "REJECTED"
    if index < 60:
        return "DRAFT"
    if index < 115:
        return "PENDING_APPROVAL"
    if index < 145:
        return "REJECTED"
    if index < 195:
        return "APPROVED"
    if index < 265:
        return "PURCHASING"
    if index < 320:
        return "QUOTED"
    if index < 385:
        return "CONTRACTED"
    return "COMPLETED"


def quantity_for(product: tuple[str, ...], index: int) -> Decimal:
    unit = product[6]
    product_name = product[2]
    if "蓄电池" in product_name:
        values = (Decimal("24"), Decimal("40"), Decimal("80"), Decimal("100"))
    elif unit in {"根", "条", "片", "只"}:
        values = (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("50"))
    elif "服务器" in product_name or "交换机" in product_name:
        values = (Decimal("1"), Decimal("2"), Decimal("4"), Decimal("6"))
    else:
        values = (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("5"), Decimal("8"))
    return values[index % len(values)]


def price_for(base_price: str, index: int) -> Decimal:
    factors = ("0.94", "0.97", "1.00", "1.03", "1.06")
    return (Decimal(base_price) * Decimal(factors[index % len(factors)])).quantize(
        MONEY, rounding=ROUND_HALF_UP
    )


def build_requirement_specs() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(REQUIREMENT_COUNT):
        if 145 <= index < 175:
            template_index = index - 145
            requester_index = template_index % 60
            revision_no = 2
            previous_index = template_index
        else:
            template_index = (
                index % len(PRODUCTS) if index < CURATED_COUNT else (index * 7 + 3) % len(PRODUCTS)
            )
            requester_index = index % 60
            revision_no = 1
            previous_index = None

        product = PRODUCTS[template_index]
        status = status_for(index)
        requested_at = BASE_TIME - timedelta(days=(REQUIREMENT_COUNT - index) * 2)
        submitted_at = None if status == "DRAFT" else requested_at + timedelta(hours=4)
        quantity = quantity_for(product, index)
        unit_price = price_for(product[7], index)
        source_kind = "curated" if index < CURATED_COUNT else "simulated"
        rows.append(
            {
                "index": index,
                "source_kind": source_kind,
                "source_reference": f"{SEED_PREFIX}:{source_kind}:{index + 1:04d}",
                "requester_index": requester_index,
                "approver_index": index % 8,
                "purchaser_index": index % 12,
                "template_index": template_index,
                "supplier_index": (template_index * 3 + (0 if index % 2 == 0 else 5)) % 24,
                "status": status,
                "requested_at": requested_at,
                "submitted_at": submitted_at,
                "revision_no": revision_no,
                "previous_index": previous_index,
                "reason": REASONS[(template_index + index) % len(REASONS)],
                "location": LOCATIONS[(index * 5 + template_index) % len(LOCATIONS)],
                "quantity": quantity,
                "unit_price": unit_price,
                "total_amount": (quantity * unit_price).quantize(MONEY),
            }
        )
    return rows


def generation_summary() -> dict[str, object]:
    requirements = build_requirement_specs()
    statuses = Counter(str(row["status"]) for row in requirements)
    order_count = sum(
        status in {"APPROVED", "PURCHASING", "QUOTED", "CONTRACTED", "COMPLETED"}
        for status in statuses.elements()
    )
    return {
        "employees": len(build_employees()),
        "categories": len({product[0] for product in PRODUCTS}),
        "products": len(PRODUCTS),
        "suppliers": len(build_suppliers()),
        "requirements": len(requirements),
        "curated_requirements": CURATED_COUNT,
        "simulated_requirements": REQUIREMENT_COUNT - CURATED_COUNT,
        "orders": order_count,
        "status_counts": dict(statuses),
    }


async def insert_returning_id(session, statement: str, parameters: dict[str, object]) -> int:
    result = await session.execute(text(statement), parameters)
    return int(result.lastrowid)


async def seed_database() -> dict[str, int]:
    settings = Settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    counts: Counter[str] = Counter()
    try:
        async with transaction_scope(session_factory) as session:
            database_name = await session.scalar(text("SELECT DATABASE()"))
            if database_name != "purchasing_agent":
                raise RuntimeError(
                    "Refusing to seed a database other than the local purchasing_agent database"
                )
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != "0005_auth_rbac_foundation":
                raise RuntimeError(
                    "Database must be upgraded to 0005_auth_rbac_foundation before seeding"
                )
            existing_seed_rows = await session.scalar(
                text(
                    "SELECT COUNT(*) FROM purchase_requirement WHERE source_reference LIKE :prefix"
                ),
                {"prefix": f"{SEED_PREFIX}:%"},
            )
            if existing_seed_rows == REQUIREMENT_COUNT:
                return {"already_seeded": REQUIREMENT_COUNT}
            if existing_seed_rows:
                raise RuntimeError(
                    f"Found a partial seed ({existing_seed_rows} requirements); "
                    "refusing to add duplicates"
                )

            employee_ids: dict[str, list[tuple[int, dict[str, object]]]] = defaultdict(list)
            for employee in build_employees():
                employee_id = await insert_returning_id(
                    session,
                    "INSERT INTO employee "
                    "(employee_no, name, phone, role, status) "
                    "VALUES (:employee_no, :name, :phone, :role, 'ACTIVE')",
                    employee,
                )
                employee_ids[str(employee["role"])].append((employee_id, employee))
                counts["employee"] += 1

            category_ids: dict[str, int] = {}
            for category in sorted({product[0] for product in PRODUCTS}):
                category_ids[category] = await insert_returning_id(
                    session,
                    "INSERT INTO product_category (name, description) VALUES (:name, :description)",
                    {"name": category, "description": f"{category}类开发测试数据"},
                )
                counts["product_category"] += 1

            supplier_ids: list[int] = []
            suppliers = build_suppliers()
            for supplier in suppliers:
                supplier_ids.append(
                    await insert_returning_id(
                        session,
                        "INSERT INTO supplier "
                        "(supplier_name, contact, phone, level, status) "
                        "VALUES (:supplier_name, :contact, :phone, :level, 'ACTIVE')",
                        supplier,
                    )
                )
                counts["supplier"] += 1

            product_ids: list[int] = []
            for template_index, product in enumerate(PRODUCTS):
                (
                    category,
                    device_type,
                    name,
                    brand,
                    model,
                    specification,
                    unit,
                    base_price,
                ) = product
                product_id = await insert_returning_id(
                    session,
                    "INSERT INTO product_whitelist "
                    "(category_id, product_name, brand, model, specification, unit, status) "
                    "VALUES (:category_id, :product_name, :brand, :model, :specification, "
                    ":unit, 'ACTIVE')",
                    {
                        "category_id": category_ids[category],
                        "product_name": name,
                        "brand": brand,
                        "model": model,
                        "specification": specification,
                        "unit": unit,
                    },
                )
                product_ids.append(product_id)
                counts["product_whitelist"] += 1
                for offset in (0, 5):
                    supplier_index = (template_index * 3 + offset) % len(supplier_ids)
                    await insert_returning_id(
                        session,
                        "INSERT INTO product_supplier "
                        "(product_id, supplier_id, price, delivery_days) "
                        "VALUES (:product_id, :supplier_id, :price, :delivery_days)",
                        {
                            "product_id": product_id,
                            "supplier_id": supplier_ids[supplier_index],
                            "price": Decimal(base_price),
                            "delivery_days": 3 + (template_index + offset) % 28,
                        },
                    )
                    counts["product_supplier"] += 1

            requesters = employee_ids["REQUESTER"]
            approvers = employee_ids["APPROVER"]
            purchasers = employee_ids["PURCHASER"]
            requirements = build_requirement_specs()
            requirement_ids: list[int] = []
            status_history: list[dict[str, object]] = []
            operation_logs: list[dict[str, object]] = []

            for spec in requirements:
                index = int(spec["index"])
                product = PRODUCTS[int(spec["template_index"])]
                category, device_type, name, brand, model, specification, unit, _ = product
                employee_id, employee = requesters[int(spec["requester_index"])]
                supplier_index = int(spec["supplier_index"])
                supplier_id = supplier_ids[supplier_index]
                supplier = suppliers[supplier_index]
                session_id = f"DEV-SESSION-{index + 1:04d}"

                await session.execute(
                    text(
                        "INSERT INTO agent_session (session_id, user_id, status, created_at) "
                        "VALUES (:session_id, :user_id, :status, :created_at)"
                    ),
                    {
                        "session_id": session_id,
                        "user_id": employee_id,
                        "status": "COMPLETED" if spec["status"] != "DRAFT" else "ACTIVE",
                        "created_at": spec["requested_at"],
                    },
                )
                counts["agent_session"] += 1
                user_content = f"申请采购{spec['quantity']}{unit}{name}，用于{spec['reason']}"
                assistant_content = f"已整理采购需求：{brand}{model}，申请地点{spec['location']}。"
                await session.execute(
                    text(
                        "INSERT INTO agent_message (session_id, role, content, created_at) VALUES "
                        "(:session_id, 'user', :user_content, :requested_at), "
                        "(:session_id, 'assistant', :assistant_content, :assistant_at)"
                    ),
                    {
                        "session_id": session_id,
                        "user_content": user_content,
                        "assistant_content": assistant_content,
                        "requested_at": spec["requested_at"],
                        "assistant_at": spec["requested_at"] + timedelta(minutes=2),
                    },
                )
                counts["agent_message"] += 2

                previous_requirement_id = (
                    requirement_ids[int(spec["previous_index"])]
                    if spec["previous_index"] is not None
                    else None
                )
                requirement_id = await insert_returning_id(
                    session,
                    "INSERT INTO purchase_requirement "
                    "(requirement_no, session_id, employee_id, applicant_employee_no, "
                    "applicant_name, applicant_phone, requested_at, submitted_at, revision_no, "
                    "previous_requirement_id, category_id, category_name, application_reason, "
                    "application_location, device_type, product_id, product_name, "
                    "product_full_name, "
                    "brand, model, specification, quantity, unit, supplier_id, supplier_name, "
                    "unit_price, total_amount, currency, status, source_reference, created_at) "
                    "VALUES (:requirement_no, :session_id, :employee_id, :employee_no, :name, "
                    ":phone, :requested_at, :submitted_at, :revision_no, :previous_requirement_id, "
                    ":category_id, :category_name, :application_reason, :application_location, "
                    ":device_type, :product_id, :product_name, :product_full_name, :brand, :model, "
                    ":specification, :quantity, :unit, :supplier_id, :supplier_name, :unit_price, "
                    ":total_amount, 'CNY', :status, :source_reference, :created_at)",
                    {
                        "requirement_no": f"DEV-REQ-{index + 1:05d}",
                        "session_id": session_id,
                        "employee_id": employee_id,
                        "employee_no": employee["employee_no"],
                        "name": employee["name"],
                        "phone": employee["phone"],
                        "requested_at": spec["requested_at"],
                        "submitted_at": spec["submitted_at"],
                        "revision_no": spec["revision_no"],
                        "previous_requirement_id": previous_requirement_id,
                        "category_id": category_ids[category],
                        "category_name": category,
                        "application_reason": spec["reason"],
                        "application_location": spec["location"],
                        "device_type": device_type,
                        "product_id": product_ids[int(spec["template_index"])],
                        "product_name": name,
                        "product_full_name": f"{brand} {name} {model} {specification}",
                        "brand": brand,
                        "model": model,
                        "specification": specification,
                        "quantity": spec["quantity"],
                        "unit": unit,
                        "supplier_id": supplier_id,
                        "supplier_name": supplier["supplier_name"],
                        "unit_price": spec["unit_price"],
                        "total_amount": spec["total_amount"],
                        "status": spec["status"],
                        "source_reference": spec["source_reference"],
                        "created_at": spec["requested_at"],
                    },
                )
                requirement_ids.append(requirement_id)
                counts["purchase_requirement"] += 1

                alternative_index = (int(spec["template_index"]) + 1) % len(PRODUCTS)
                alternative_supplier_index = (
                    alternative_index * 3 + (0 if index % 2 == 0 else 5)
                ) % len(supplier_ids)
                await session.execute(
                    text(
                        "INSERT INTO recommendation "
                        "(requirement_id, product_id, supplier_id, score, reason, selected, "
                        "created_at) VALUES "
                        "(:requirement_id, :product_id, :supplier_id, 92.50, :reason, 1, "
                        ":created_at), "
                        "(:requirement_id, :alternative_product_id, :alternative_supplier_id, "
                        "84.00, :alternative_reason, 0, :created_at)"
                    ),
                    {
                        "requirement_id": requirement_id,
                        "product_id": product_ids[int(spec["template_index"])],
                        "supplier_id": supplier_id,
                        "reason": "规格匹配、白名单有效且具有历史采购参考",
                        "alternative_product_id": product_ids[alternative_index],
                        "alternative_supplier_id": supplier_ids[alternative_supplier_index],
                        "alternative_reason": "作为同类备选方案供测试比价与审批展示",
                        "created_at": spec["requested_at"] + timedelta(minutes=3),
                    },
                )
                counts["recommendation"] += 2

                requested_at = spec["requested_at"]
                submitted_at = spec["submitted_at"]
                status_history.append(
                    {
                        "requirement_id": requirement_id,
                        "order_id": None,
                        "from_status": None,
                        "to_status": "DRAFT",
                        "operator_id": employee_id,
                        "operator_employee_no": employee["employee_no"],
                        "operator_name": employee["name"],
                        "operator_phone": employee["phone"],
                        "remark": "创建采购申请草稿",
                        "changed_at": requested_at,
                        "request_id": f"DEV-TRACE-{index + 1:05d}-01",
                    }
                )
                if submitted_at is not None:
                    status_history.append(
                        {
                            "requirement_id": requirement_id,
                            "order_id": None,
                            "from_status": "DRAFT",
                            "to_status": "PENDING_APPROVAL",
                            "operator_id": employee_id,
                            "operator_employee_no": employee["employee_no"],
                            "operator_name": employee["name"],
                            "operator_phone": employee["phone"],
                            "remark": "员工提交楼长审批",
                            "changed_at": submitted_at,
                            "request_id": f"DEV-TRACE-{index + 1:05d}-02",
                        }
                    )

                operation_logs.append(
                    {
                        "action": "CREATE_REQUIREMENT",
                        "operator": str(employee["employee_no"]),
                        "content": f"创建开发测试采购申请 DEV-REQ-{index + 1:05d}",
                        "created_at": requested_at,
                    }
                )

                if spec["status"] not in {"DRAFT", "PENDING_APPROVAL"}:
                    approver_id, approver = approvers[int(spec["approver_index"])]
                    approved = spec["status"] != "REJECTED"
                    action = "APPROVED" if approved else "REJECTED"
                    acted_at = submitted_at + timedelta(hours=20)
                    await session.execute(
                        text(
                            "INSERT INTO purchase_approval "
                            "(requirement_id, revision_no, approver_id, approver_employee_no, "
                            "approver_name, approver_phone, action, comment, submitted_at, "
                            "acted_at, "
                            "idempotency_key, created_at) VALUES (:requirement_id, :revision_no, "
                            ":approver_id, "
                            ":employee_no, :name, :phone, :action, :comment, :submitted_at, "
                            ":acted_at, :idempotency_key, :created_at)"
                        ),
                        {
                            "requirement_id": requirement_id,
                            "revision_no": spec["revision_no"],
                            "approver_id": approver_id,
                            "employee_no": approver["employee_no"],
                            "name": approver["name"],
                            "phone": approver["phone"],
                            "action": action,
                            "comment": (
                                "需求明确、规格合理，同意进入采购流程"
                                if approved
                                else "请补充设备故障检测结果和现场照片后重新提交"
                            ),
                            "submitted_at": submitted_at,
                            "acted_at": acted_at,
                            "idempotency_key": f"{SEED_PREFIX}:approval:{index + 1:04d}",
                            "created_at": acted_at,
                        },
                    )
                    counts["purchase_approval"] += 1
                    status_history.append(
                        {
                            "requirement_id": requirement_id,
                            "order_id": None,
                            "from_status": "PENDING_APPROVAL",
                            "to_status": "APPROVED" if approved else "REJECTED",
                            "operator_id": approver_id,
                            "operator_employee_no": approver["employee_no"],
                            "operator_name": approver["name"],
                            "operator_phone": approver["phone"],
                            "remark": (
                                "楼长审批通过"
                                if approved
                                else "审批未通过，已反馈员工修改或重新提交"
                            ),
                            "changed_at": acted_at,
                            "request_id": f"DEV-TRACE-{index + 1:05d}-03",
                        }
                    )
                    operation_logs.append(
                        {
                            "action": "APPROVE_REQUIREMENT" if approved else "REJECT_REQUIREMENT",
                            "operator": str(approver["employee_no"]),
                            "content": f"审批开发测试采购申请 DEV-REQ-{index + 1:05d}",
                            "created_at": acted_at,
                        }
                    )

                if spec["status"] in {
                    "APPROVED",
                    "PURCHASING",
                    "QUOTED",
                    "CONTRACTED",
                    "COMPLETED",
                }:
                    purchaser_id, purchaser = purchasers[int(spec["purchaser_index"])]
                    acted_at = submitted_at + timedelta(hours=20)
                    status = str(spec["status"])
                    started_at = None if status == "APPROVED" else acted_at + timedelta(hours=4)
                    quoted_at = (
                        started_at + timedelta(days=2)
                        if status in {"QUOTED", "CONTRACTED", "COMPLETED"}
                        else None
                    )
                    contracted_at = (
                        quoted_at + timedelta(days=3)
                        if status in {"CONTRACTED", "COMPLETED"}
                        else None
                    )
                    received_at = (
                        contracted_at + timedelta(days=10 + index % 10)
                        if status == "COMPLETED"
                        else None
                    )
                    completed_at = received_at + timedelta(hours=2) if received_at else None
                    order_status = "CREATED" if status == "APPROVED" else status
                    order_id = await insert_returning_id(
                        session,
                        "INSERT INTO purchase_order "
                        "(order_no, requirement_id, product_id, supplier_id, supplier_name, "
                        "quantity, unit_price, amount, status, purchaser_id, "
                        "purchaser_employee_no, "
                        "purchaser_name, purchaser_phone, purchasing_started_at, quoted_at, "
                        "contracted_at, received_at, completed_at, created_at) VALUES (:order_no, "
                        ":requirement_id, :product_id, :supplier_id, :supplier_name, :quantity, "
                        ":unit_price, :amount, :status, :purchaser_id, :employee_no, :name, "
                        ":phone, "
                        ":started_at, :quoted_at, :contracted_at, :received_at, :completed_at, "
                        ":created_at)",
                        {
                            "order_no": f"DEV-PO-{index + 1:05d}",
                            "requirement_id": requirement_id,
                            "product_id": product_ids[int(spec["template_index"])],
                            "supplier_id": supplier_id,
                            "supplier_name": supplier["supplier_name"],
                            "quantity": spec["quantity"],
                            "unit_price": spec["unit_price"],
                            "amount": spec["total_amount"],
                            "status": order_status,
                            "purchaser_id": purchaser_id,
                            "employee_no": purchaser["employee_no"],
                            "name": purchaser["name"],
                            "phone": purchaser["phone"],
                            "started_at": started_at,
                            "quoted_at": quoted_at,
                            "contracted_at": contracted_at,
                            "received_at": received_at,
                            "completed_at": completed_at,
                            "created_at": acted_at,
                        },
                    )
                    counts["purchase_order"] += 1
                    order_events = [(None, "CREATED", acted_at, "审批通过后生成采购单")]
                    if started_at:
                        order_events.append(
                            ("CREATED", "PURCHASING", started_at, "采购人员开始处理")
                        )
                    if quoted_at:
                        order_events.append(("PURCHASING", "QUOTED", quoted_at, "询价核价完成"))
                    if contracted_at:
                        order_events.append(("QUOTED", "CONTRACTED", contracted_at, "合同签订完成"))
                    if received_at:
                        order_events.append(("CONTRACTED", "RECEIVED", received_at, "设备验收入库"))
                        order_events.append(("RECEIVED", "COMPLETED", completed_at, "采购单完成"))
                    for event_no, (
                        from_status,
                        to_status,
                        changed_at,
                        remark,
                    ) in enumerate(order_events, start=4):
                        status_history.append(
                            {
                                "requirement_id": requirement_id,
                                "order_id": order_id,
                                "from_status": from_status,
                                "to_status": to_status,
                                "operator_id": purchaser_id,
                                "operator_employee_no": purchaser["employee_no"],
                                "operator_name": purchaser["name"],
                                "operator_phone": purchaser["phone"],
                                "remark": remark,
                                "changed_at": changed_at,
                                "request_id": f"DEV-TRACE-{index + 1:05d}-{event_no:02d}",
                            }
                        )
                    if completed_at:
                        operation_logs.append(
                            {
                                "action": "COMPLETE_PURCHASE",
                                "operator": str(purchaser["employee_no"]),
                                "content": f"完成采购单 DEV-PO-{index + 1:05d} 并验收入库",
                                "created_at": completed_at,
                            }
                        )

            await session.execute(
                text(
                    "INSERT INTO purchase_status_history "
                    "(requirement_id, order_id, from_status, to_status, operator_id, "
                    "operator_employee_no, operator_name, operator_phone, remark, changed_at, "
                    "request_id) VALUES (:requirement_id, :order_id, :from_status, :to_status, "
                    ":operator_id, :operator_employee_no, :operator_name, :operator_phone, "
                    ":remark, "
                    ":changed_at, :request_id)"
                ),
                status_history,
            )
            counts["purchase_status_history"] += len(status_history)
            await session.execute(
                text(
                    "INSERT INTO operation_log (action, operator, content, created_at) "
                    "VALUES (:action, :operator, :content, :created_at)"
                ),
                operation_logs,
            )
            counts["operation_log"] += len(operation_logs)
    finally:
        await engine.dispose()
    return dict(counts)


def main() -> None:
    args = parse_args()
    summary = generation_summary()
    if args.dry_run:
        print(summary)
        return
    result = asyncio.run(seed_database())
    print({"generation": summary, "inserted": result})


if __name__ == "__main__":
    main()
