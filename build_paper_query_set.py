#!/usr/bin/env python3
"""Build the preregistered 100-query bilingual video retrieval set."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIELDS = [
    "query_id", "query_text", "language", "product_class", "query_type",
    "split", "query_status", "expected_visual_evidence", "source_leakage_guard",
]


def q(query_type: str, zh: str, en: str, evidence: str) -> tuple[str, str, str, str]:
    return query_type, zh, en, evidence


QUERY_SPECS = {
    "Air Fryer": [
        q("operation", "空气炸锅怎样设置烹饪温度和时间？", "How do I set the cooking temperature and time on an air fryer?", "control-panel input followed by a cooking state"),
        q("operation", "食材应该怎样放进空气炸锅炸篮？", "How should food be loaded into an air-fryer basket?", "food placement in the removable basket"),
        q("operation", "怎样插回炸篮并启动空气炸锅？", "How do I reinsert the basket and start the air fryer?", "basket insertion and start control"),
        q("state", "空气炸锅正在预热时画面是什么状态？", "What visible state shows that an air fryer is preheating?", "preheat indicator, display, or heating transition"),
        q("state", "怎样看出空气炸锅正在烹饪？", "How can I tell that the air fryer is actively cooking?", "active timer, fan, heat, or cooking display"),
        q("state", "空气炸锅完成烹饪后会显示什么？", "What does an air fryer show when cooking is complete?", "completion indicator and finished food"),
        q("component", "空气炸锅的炸篮和接油盘在哪里？", "Where are the basket and crisper or drip tray in an air fryer?", "basket removal exposing tray parts"),
        q("component", "空气炸锅控制面板上的主要按键怎样使用？", "How are the main controls on an air-fryer panel used?", "close view of buttons or touch controls"),
        q("component", "空气炸锅内腔和加热部件位于哪里？", "Where are the cooking chamber and heating element located?", "open chamber or upper heating area"),
        q("maintenance", "使用后怎样清洗空气炸锅炸篮？", "How do I clean the air-fryer basket after use?", "basket removal and washing or wiping"),
        q("maintenance", "怎样清除空气炸锅中的油脂和食物残渣？", "How can grease and food residue be removed from an air fryer?", "wiping or washing greasy interior parts"),
        q("maintenance", "怎样清洁空气炸锅内腔或加热区域？", "How should the air-fryer chamber or heating area be cleaned?", "safe interior cleaning with appliance inactive"),
        q("troubleshooting", "炸篮没有装到位导致空气炸锅不启动时怎么办？", "What should I do if the air fryer will not start because the basket is not seated?", "basket reseating followed by successful start"),
        q("troubleshooting", "空气炸锅食物受热不均时怎样处理？", "How can uneven air-fryer cooking be corrected?", "shaking, turning, or redistributing food"),
        q("troubleshooting", "空气炸锅冒烟或有明显油烟时怎样处理？", "What should I do when an air fryer produces excessive smoke?", "stop, inspect grease or residue, and clean"),
        q("safety", "怎样安全取出高温的空气炸锅炸篮？", "How can a hot air-fryer basket be removed safely?", "handle use and heat-safe placement"),
        q("safety", "使用空气炸锅时怎样避免堵住进出风口？", "How should air-fryer vents be kept clear during use?", "unobstructed appliance placement and visible vents"),
    ],
    "Espresso Machine": [
        q("operation", "怎样给意式咖啡机加水并准备萃取？", "How do I fill an espresso machine with water and prepare it for extraction?", "water reservoir filling and machine preparation"),
        q("operation", "咖啡粉怎样装入并压实在手柄中？", "How is coffee dosed and tamped in a portafilter?", "grounds placed and tamped in portafilter"),
        q("operation", "怎样锁紧手柄并开始萃取浓缩咖啡？", "How do I lock in the portafilter and start an espresso shot?", "portafilter locking and extraction control"),
        q("state", "咖啡机预热完成可以萃取时是什么状态？", "What indicates that an espresso machine is heated and ready?", "ready light, display, or stable boiler state"),
        q("state", "怎样从画面判断浓缩咖啡正在正常流出？", "What does a normal espresso extraction look like?", "espresso stream entering a cup"),
        q("state", "一杯浓缩咖啡萃取结束时有什么可见信号？", "What visible cue shows that an espresso shot has finished?", "flow stopping, timer ending, or cup removal"),
        q("component", "意式咖啡机的手柄和粉碗在哪里？", "Where are the portafilter and filter basket on an espresso machine?", "portafilter and basket shown separately or installed"),
        q("component", "咖啡机蒸汽棒怎样打开并用于打奶泡？", "How is the steam wand activated and used to texture milk?", "steam control and wand in milk pitcher"),
        q("component", "冲煮头和接水盘分别位于哪里？", "Where are the group head and drip tray on an espresso machine?", "front machine view identifying both components"),
        q("maintenance", "萃取后怎样冲洗咖啡机冲煮头？", "How do I flush the group head after extraction?", "water flush without coffee or cleaning cycle"),
        q("maintenance", "打奶后怎样清洁和排空蒸汽棒？", "How should an espresso-machine steam wand be wiped and purged after steaming milk?", "wand wiping and brief steam purge"),
        q("maintenance", "怎样取出并清空意式咖啡机接水盘？", "How do I remove and empty an espresso-machine drip tray?", "tray removal, emptying, and reinsertion"),
        q("troubleshooting", "咖啡机不出水时应检查哪些可见步骤？", "What visible checks help when an espresso machine produces no water?", "reservoir, controls, group head, or blockage checks"),
        q("troubleshooting", "浓缩咖啡流速过快或过慢时怎样调整？", "How can an espresso shot that runs too fast or too slowly be corrected?", "dose, grind, tamp, or extraction adjustment"),
        q("troubleshooting", "蒸汽棒不出蒸汽或堵塞时怎样处理？", "How do I address an espresso-machine steam wand that is blocked or produces no steam?", "purging, wiping, or clearing the wand tip"),
        q("safety", "使用咖啡机蒸汽棒时怎样避免被高温蒸汽烫伤？", "How can burns be avoided while using an espresso steam wand?", "hand placement away from steam and hot metal"),
        q("safety", "拆卸手柄前怎样确认萃取压力已经释放？", "How should espresso-machine pressure be allowed to release before removing the portafilter?", "extraction stop and delayed safe removal"),
    ],
    "Pressure Cooker": [
        q("operation", "怎样把内胆和食材正确放入电压力锅？", "How are the inner pot and ingredients placed in an electric pressure cooker?", "inner-pot insertion and ingredient loading"),
        q("operation", "压力锅锅盖怎样对准并锁定？", "How do I align and lock a pressure-cooker lid?", "lid alignment and locking motion"),
        q("operation", "怎样选择压力烹饪程序并设置时间？", "How do I select a pressure-cooking program and set its time?", "control-panel program and time selection"),
        q("state", "压力锅开始升压时有哪些可见状态？", "What visible signs show that a pressure cooker is building pressure?", "display state, valve position, or steam transition"),
        q("state", "压力锅达到压力并开始计时时怎样显示？", "How does a pressure cooker indicate that timed cooking has begun?", "timer countdown or pressure indicator"),
        q("state", "烹饪完成进入保温时是什么状态？", "What indicates that pressure-cooker cooking is complete and keep-warm has started?", "completion or keep-warm display"),
        q("component", "压力锅密封圈怎样安装在锅盖上？", "How is the sealing ring fitted into a pressure-cooker lid?", "ring seated around lid retainer"),
        q("component", "排气阀或浮子阀位于锅盖什么位置？", "Where are the steam-release and float valves on a pressure-cooker lid?", "close view of lid valves"),
        q("component", "压力锅内胆和控制面板怎样配合使用？", "How are the inner pot and control panel used together?", "loaded inner pot followed by panel operation"),
        q("maintenance", "使用后怎样清洗压力锅锅盖和密封圈？", "How should the pressure-cooker lid and sealing ring be cleaned?", "ring removal and lid cleaning"),
        q("maintenance", "怎样清理压力锅的排气阀和防堵部件？", "How do I clean a pressure-cooker steam valve and anti-block parts?", "valve removal, inspection, or rinsing"),
        q("maintenance", "怎样清洗并重新放回压力锅内胆？", "How is the pressure-cooker inner pot cleaned and reinstalled?", "inner-pot washing and reinsertion"),
        q("troubleshooting", "压力锅不能密封或一直漏气时怎样检查？", "What should I check if a pressure cooker will not seal or keeps leaking steam?", "ring, valve, lid, and seating checks"),
        q("troubleshooting", "电压力锅显示烧焦提示时怎样处理？", "What should I do when an electric pressure cooker shows a burn warning?", "stop, depressurize, inspect liquid or stuck food"),
        q("troubleshooting", "压力锅释放压力后锅盖仍打不开时怎么办？", "What should I do if the pressure-cooker lid will not open after release?", "float-valve and residual-pressure checks"),
        q("safety", "怎样进行自然排气并确认可以开盖？", "How is natural pressure release performed on a pressure cooker before opening the lid?", "waiting for pressure indicator to drop"),
        q("safety", "压力锅快速排气时手和脸应该避开什么位置？", "Where should hands and face be kept during quick pressure release?", "safe position away from steam outlet"),
    ],
    "Printer": [
        q("operation", "怎样在打印机纸盒中正确装入纸张？", "How do I load paper correctly into a printer tray?", "paper loading and guide adjustment"),
        q("operation", "怎样安装墨盒或硒鼓并关闭打印机？", "How do I install an ink cartridge or toner cartridge?", "cartridge insertion and access-door closure"),
        q("operation", "怎样从控制面板打印测试页？", "How do I print a test page from the printer controls?", "control selection followed by printed output"),
        q("state", "打印机已就绪时控制面板显示什么？", "What does the printer show when it is ready?", "ready light or home display"),
        q("state", "纸张正在通过打印机时是什么画面？", "What does active paper feeding and printing look like?", "paper moving through printer and output appearing"),
        q("state", "打印机发生错误或缺纸时怎样显示？", "How does a printer indicate an error or out-of-paper state?", "error light, code, or screen message"),
        q("component", "打印机进纸盒和纸张导轨在哪里？", "Where are the input tray and paper guides on a printer?", "tray opened with guides visible"),
        q("component", "打印机墨盒舱或硒鼓舱怎样打开？", "How is the ink or toner compartment opened?", "access panel opening and cartridge area exposed"),
        q("component", "打印机后部卡纸检修口在哪里？", "Where is the rear paper-jam access area on a printer?", "rear door or duplexer removal"),
        q("maintenance", "喷墨打印机怎样执行打印头清洗？", "How do I run a printhead-cleaning cycle on an inkjet printer?", "maintenance menu or manual cleaning sequence"),
        q("maintenance", "打印质量变差时怎样进行打印头校准？", "How is printhead alignment performed when print quality degrades?", "alignment menu and printed alignment page"),
        q("maintenance", "怎样更换打印机已用尽的墨盒或硒鼓？", "How do I replace an empty ink or toner cartridge?", "old cartridge removal and new cartridge insertion"),
        q("troubleshooting", "打印机卡纸时怎样安全取出纸张？", "How do I remove jammed paper from a printer safely?", "power-safe access and paper removal without tearing"),
        q("troubleshooting", "打印机显示离线时怎样恢复连接？", "How can a printer showing offline be brought back online?", "network, cable, or settings check followed by ready state"),
        q("troubleshooting", "打印机报告墨盒故障时怎样重新安装墨盒？", "How do I reseat a cartridge after a printer cartridge error?", "cartridge removal, contact check, and reinsertion"),
        q("safety", "检查打印机内部前为什么要先断电？", "Why and how should a printer be powered off before internal inspection?", "power-off or unplug step before opening"),
        q("safety", "从打印机内部取纸时怎样避开高温部件？", "How should hot internal printer components be avoided during jam removal?", "caution around fuser or hot labeled area"),
    ],
    "Vacuum": [
        q("operation", "怎样组装吸尘器延长杆和地刷？", "How do I attach the wand and floor head to a vacuum cleaner?", "wand and nozzle connection"),
        q("operation", "怎样用吸尘器清洁地毯或硬地面？", "How is a vacuum cleaner used on carpet or hard flooring?", "active passes over a floor surface"),
        q("operation", "吸尘器怎样切换并使用缝隙吸头或小刷头？", "How do I attach and use a crevice or brush tool?", "accessory change and targeted cleaning"),
        q("state", "吸尘器正常吸尘时有哪些可见状态？", "What visible signs show that a vacuum is operating normally?", "powered brush, debris pickup, or active display"),
        q("state", "无线吸尘器充电时怎样显示？", "How does a cordless vacuum indicate that it is charging?", "charging dock or battery indicator"),
        q("state", "集尘盒装满或需要清空时怎样看出来？", "How can I tell that a vacuum dust bin is full?", "visible fill line, full bin, or warning"),
        q("component", "吸尘器集尘盒怎样拆下和装回？", "How is a vacuum dust bin removed and reinstalled?", "bin release and reseating"),
        q("component", "吸尘器滤网位于哪里并怎样取出？", "Where is the vacuum filter and how is it removed?", "filter compartment opening and removal"),
        q("component", "吸尘器地刷中的滚刷怎样拆卸？", "How is the brush roll removed from a vacuum floor head?", "floor-head latch and brush-roll extraction"),
        q("maintenance", "怎样清空吸尘器集尘盒？", "How do I empty a vacuum cleaner dust bin?", "bin opening over waste container"),
        q("maintenance", "怎样清洗或拍净吸尘器滤网？", "How should a vacuum filter be washed or cleaned?", "filter cleaning and drying indication"),
        q("maintenance", "怎样清除滚刷上缠绕的毛发？", "How do I remove tangled hair from a vacuum brush roll?", "hair cutting or pulling from inactive brush"),
        q("troubleshooting", "吸尘器吸力下降时应检查哪些部件？", "What should I inspect when a vacuum loses suction?", "bin, filter, hose, or blockage checks"),
        q("troubleshooting", "吸尘器滚刷不转时怎样排查？", "How do I troubleshoot a vacuum brush roll that will not spin?", "power, belt, obstruction, or brush inspection"),
        q("safety", "清理滚刷前怎样确保吸尘器不会启动？", "How should a vacuum be made safe before cleaning its brush roll?", "unplugging or battery removal"),
        q("safety", "吸尘时怎样避免吸入液体或危险碎片？", "How can liquids or hazardous debris be avoided when vacuuming?", "dry-area inspection or unsuitable debris avoidance"),
    ],
    "Washing Machine": [
        q("operation", "怎样把衣物放入洗衣机并避免过载？", "How should laundry be loaded without overfilling a washing machine?", "clothes distributed inside drum"),
        q("operation", "洗衣液或洗衣粉应该放入哪个格子？", "Which washing-machine detergent-drawer compartment should receive detergent?", "drawer compartments and detergent placement"),
        q("operation", "怎样选择洗涤程序并启动洗衣机？", "How do I select a wash program and start the washing machine?", "dial or panel selection followed by start"),
        q("state", "洗衣机进水和洗涤时分别是什么状态？", "What do washing-machine filling and washing states look like?", "water entry and drum agitation"),
        q("state", "洗衣机正在脱水时怎样判断？", "How can I tell that a washing machine is in the spin cycle?", "high-speed drum rotation or spin indicator"),
        q("state", "洗涤结束后怎样看出门锁已经解除？", "What shows that a washing-machine cycle has ended and the door is unlocked?", "completion display and lock indicator off"),
        q("component", "洗衣机洗涤剂抽屉怎样拉出？", "How is the detergent drawer removed from a washing machine?", "drawer release and removal"),
        q("component", "滚筒洗衣机排水过滤器位于哪里？", "Where is the drain-pump filter on a front-loading washer?", "lower service flap and filter cap"),
        q("component", "洗衣机门封胶圈应该检查哪些位置？", "Which parts of a washing-machine door seal should be inspected?", "seal folds exposed and checked"),
        q("maintenance", "怎样清理洗衣机排水过滤器？", "How do I clean a washing-machine drain filter?", "controlled draining, filter removal, and cleaning"),
        q("maintenance", "怎样擦洗滚筒洗衣机门封胶圈？", "How should a front-loader door gasket be cleaned?", "gasket folds wiped and debris removed"),
        q("maintenance", "怎样运行洗衣机筒清洁程序？", "How do I run a washing-machine drum-clean cycle?", "clean-cycle selection and empty drum"),
        q("troubleshooting", "洗衣机不排水时怎样检查过滤器和排水管？", "What should I check when a washing machine will not drain?", "filter and drain-hose inspection"),
        q("troubleshooting", "脱水时机器剧烈晃动怎样重新摆放衣物？", "How can an unbalanced washing-machine load causing violent movement be corrected?", "cycle stop and laundry redistribution"),
        q("safety", "洗衣机运行时为什么不能强行开门？", "Why should the washer door not be forced open during a cycle?", "locked door and active water or drum state"),
        q("safety", "清理排水过滤器前怎样断电并防止热水流出？", "How should washing-machine power and hot residual water be handled before cleaning the drain filter?", "unplugging, cooling, and controlled draining"),
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "paper_video_queries_v1.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows: list[dict[str, str]] = []
    global_index = 0
    for product_class, specs in QUERY_SPECS.items():
        for class_index, (query_type, zh, en, evidence) in enumerate(specs, start=1):
            global_index += 1
            language = "zh-CN" if global_index % 2 else "en"
            rows.append(
                {
                    "query_id": f"VQ-{global_index:03d}",
                    "query_text": zh if language == "zh-CN" else en,
                    "language": language,
                    "product_class": product_class,
                    "query_type": query_type,
                    "split": "development" if class_index <= 10 else "source_disjoint_test",
                    "query_status": "design_frozen_pending_index_validation",
                    "expected_visual_evidence": evidence,
                    "source_leakage_guard": "no source title, creator, model number, or transcript quotation in query",
                }
            )
    if len(rows) != 100:
        raise ValueError(f"Expected 100 queries, got {len(rows)}")
    languages = {language: sum(row["language"] == language for row in rows) for language in ("zh-CN", "en")}
    splits = {split: sum(row["split"] == split for row in rows) for split in ("development", "source_disjoint_test")}
    if languages != {"zh-CN": 50, "en": 50}:
        raise ValueError(f"Language imbalance: {languages}")
    if splits != {"development": 60, "source_disjoint_test": 40}:
        raise ValueError(f"Split imbalance: {splits}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, args.output)
    print(f"output={args.output} rows={len(rows)} languages={languages} splits={splits}")


if __name__ == "__main__":
    main()
