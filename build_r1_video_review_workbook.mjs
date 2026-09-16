import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const bundleDir = "C:\\Users\\MAXS\\Desktop\\single_reviewer_bundle_expansion_20260723";
const input = path.join(bundleDir, "review_form.csv");
const outputDir = path.join(root, "outputs", "20260723-video-expansion");
const output = path.join(outputDir, "R1_video_review_workbook_expansion_20260723.xlsx");
const bundleOutput = path.join(bundleDir, "R1_video_review_workbook.xlsx");

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        value += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else value += char;
    } else if (char === '"') quoted = true;
    else if (char === ",") {
      row.push(value);
      value = "";
    } else if (char === "\n") {
      row.push(value.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      value = "";
    } else value += char;
  }
  if (value.length || row.length) {
    row.push(value.replace(/\r$/, ""));
    rows.push(row);
  }
  return rows;
}

function header(range, fill = "#1F4E78") {
  range.format = {
    fill,
    font: { bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#A6B4C2" },
  };
}

function body(range) {
  range.format = {
    verticalAlignment: "top",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#D9E2F3" },
  };
}

await fs.mkdir(outputDir, { recursive: true });
const rows = parseCsv(await fs.readFile(input, "utf8"));
if (rows.length !== 122 || rows[0].length !== 30) {
  throw new Error(`Expected 30 columns and 121 review rows, got ${rows[0].length} columns and ${rows.length - 1} rows`);
}

const workbook = Workbook.create();

const summary = workbook.worksheets.add("Progress");
summary.mergeCells("A1:D1");
summary.getRange("A1").values = [["R1 视频复核进度 · 44 条扩展批次"]];
summary.getRange("A1:D1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
summary.getRange("A1:D1").format.rowHeight = 32;
summary.getRange("A3:D3").values = [["指标", "实际值", "说明", "检查"]];
header(summary.getRange("A3:D3"), "#548235");
summary.getRange("A4:A12").values = [["总任务"], ["AI 保留全量复核"], ["AI 拒绝抽查"], ["已完成"], ["剩余"], ["接受"], ["拒绝"], ["待定"], ["许可证已核验"]];
summary.getRange("B4:B12").formulas = [
  ["=COUNTA(Review_Form!A2:A122)"],
  ['=COUNTIF(Review_Form!B2:B122,"full_positive_review")'],
  ['=COUNTIF(Review_Form!B2:B122,"rejected_audit_sample")'],
  ['=COUNTIF(Review_Form!T2:T122,"completed")'],
  ["=B4-B7"],
  ['=COUNTIF(Review_Form!AB2:AB122,"accept")'],
  ['=COUNTIF(Review_Form!AB2:AB122,"reject")'],
  ['=COUNTIF(Review_Form!AB2:AB122,"hold")'],
  ['=COUNTIF(Review_Form!U2:U122,"verified")'],
];
summary.getRange("C4:C12").values = [
  ["121"], ["115"], ["6；六类各 1 条"], ["review_status=completed"], ["总任务减已完成"],
  ["final_decision=accept"], ["final_decision=reject"], ["final_decision=hold"], ["license_evidence_status=verified"],
];
summary.getRange("D4:D6").formulas = [["=IF(B4=121,\"PASS\",\"CHECK\")"], ["=IF(B5=115,\"PASS\",\"CHECK\")"], ["=IF(B6=6,\"PASS\",\"CHECK\")"]];
body(summary.getRange("A4:D12"));
summary.getRange("A14").values = [["总体完成率"]];
summary.getRange("B14").formulas = [["=IF(B4=0,0,B7/B4)"]];
summary.getRange("B14").format.numberFormat = "0.0%";
summary.getRange("A16:D16").values = [["产品类", "全量复核数", "已完成", "已接受"]];
header(summary.getRange("A16:D16"), "#7F6000");
summary.getRange("A17:A22").values = [["Air Fryer"], ["Espresso Machine"], ["Pressure Cooker"], ["Printer"], ["Vacuum"], ["Washing Machine"]];
summary.getRange("B17").formulas = [['=COUNTIFS(Review_Form!D$2:D$122,A17,Review_Form!B$2:B$122,"full_positive_review")']];
summary.getRange("B17:B22").fillDown();
summary.getRange("C17").formulas = [['=COUNTIFS(Review_Form!D$2:D$122,A17,Review_Form!T$2:T$122,"completed")']];
summary.getRange("C17:C22").fillDown();
summary.getRange("D17").formulas = [['=COUNTIFS(Review_Form!D$2:D$122,A17,Review_Form!AB$2:AB$122,"accept")']];
summary.getRange("D17:D22").fillDown();
body(summary.getRange("A17:D22"));
summary.getRange("A:A").format.columnWidth = 28;
summary.getRange("B:B").format.columnWidth = 18;
summary.getRange("C:C").format.columnWidth = 34;
summary.getRange("D:D").format.columnWidth = 14;
summary.getRange("D4:D6").conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#E2F0D9", font: { bold: true, color: "#375623" } } });
summary.getRange("D4:D6").conditionalFormats.add("containsText", { text: "CHECK", format: { fill: "#F4CCCC", font: { bold: true, color: "#9C0006" } } });
summary.freezePanes.freezeRows(3);

const instructions = workbook.worksheets.add("Instructions");
instructions.mergeCells("A1:C1");
instructions.getRange("A1").values = [["R1 填写说明"]];
instructions.getRange("A1:C1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
};
instructions.getRange("A3:C3").values = [["顺序", "操作", "要求"]];
header(instructions.getRange("A3:C3"));
instructions.getRange("A4:C12").values = [
  [1, "先打开同目录 index.html", "按 high、normal、audit 顺序逐条播放完整视频；采样帧不能代替完整视频。"],
  [2, "核对来源页和许可证", "license_evidence_status 必须填写 verified、failed 或 unclear。"],
  [3, "只填写黄色列 S–AD", "不要改动 record_id、AI 原始字段、视频路径和采样帧路径。"],
  [4, "修正产品和过程标签", "目标产品必须真实可见；至少有操作、维护、故障或明确部件步骤。"],
  [5, "检查隐私和安全", "privacy_risk 与 safety_risk 均必须填写；高风险条目原则上拒绝或 hold。"],
  [6, "给出最终决定", "accept / reject / hold；接受项必须选择 development 或 source_disjoint_test。"],
  [7, "写明修改理由", "如果任何人工值不同于 AI，correction_reason 不能为空。"],
  [8, "完成一条即更新状态", "review_status=completed，reviewed_at 使用 ISO-8601，例如 2026-07-23T14:30:00+08:00。"],
  [9, "完成后保留原文件名", "不要另存成旧版 .xls；通知项目维护者进行自动校验和导入。"],
];
body(instructions.getRange("A4:C12"));
instructions.getRange("A:A").format.columnWidth = 10;
instructions.getRange("B:B").format.columnWidth = 34;
instructions.getRange("C:C").format.columnWidth = 86;
instructions.getRange("A3:C12").format.autofitRows();
instructions.freezePanes.freezeRows(3);

// Keep dropdown sources in workbook cells so Excel receives durable list
// validations instead of exporter-managed inline value lists.
const validationLists = workbook.worksheets.add("Validation_Lists");
validationLists.getRange("A1:H1").values = [[
  "reviewer_id", "review_status", "license_evidence_status", "corrected_product",
  "yes_no_uncertain", "risk", "final_decision", "dataset_split",
]];
validationLists.getRange("A2:H5").values = [
  ["R1", "pending", "pending", "Air Fryer", "yes", "none", "pending", "pending"],
  ["", "in_progress", "verified", "Espresso Machine", "no", "low", "accept", "development"],
  ["", "completed", "failed", "Pressure Cooker", "uncertain", "high", "reject", "source_disjoint_test"],
  ["", "", "unclear", "Printer", "", "uncertain", "hold", "excluded"],
];
validationLists.getRange("D6:D8").values = [["Vacuum"], ["Washing Machine"], ["Other"]];
header(validationLists.getRange("A1:H1"), "#7F6000");
body(validationLists.getRange("A2:H8"));
validationLists.getRange("A:H").format.columnWidth = 24;
validationLists.freezePanes.freezeRows(1);

const review = workbook.worksheets.add("Review_Form");
review.getRange("A1:AD122").values = rows;
header(review.getRange("A1:AD1"));
body(review.getRange("A2:AD122"));
review.getRange("S2:AD122").format.fill = "#FFF2CC";
review.getRange("A2:R122").format.fill = "#F2F2F2";
review.freezePanes.freezeRows(1);
review.freezePanes.freezeColumns(5);
review.getRange("A:A").format.columnWidth = 15;
review.getRange("B:C").format.columnWidth = 20;
review.getRange("D:E").format.columnWidth = 22;
review.getRange("F:F").format.columnWidth = 42;
review.getRange("G:G").format.columnWidth = 48;
review.getRange("H:J").format.columnWidth = 20;
review.getRange("K:M").format.columnWidth = 22;
review.getRange("N:P").format.columnWidth = 48;
review.getRange("Q:R").format.columnWidth = 42;
review.getRange("S:Z").format.columnWidth = 22;
review.getRange("AA:AA").format.columnWidth = 48;
review.getRange("AB:AD").format.columnWidth = 24;
review.getRange("A1:AD122").format.autofitRows();
review.getRange("S2:S122").dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$A$2:$A$2" } };
review.getRange("T2:T122").dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$B$2:$B$4" } };
review.getRange("U2:U122").dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$C$2:$C$5" } };
review.getRange("V2:V122").dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$D$2:$D$8" } };
review.getRange("W2:X122").dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$E$2:$E$4" } };
review.getRange("Y2:Z122").dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$F$2:$F$5" } };
review.getRange("AB2:AB122").dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$G$2:$G$5" } };
review.getRange("AC2:AC122").dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$H$2:$H$5" } };
review.getRange("T2:T122").conditionalFormats.add("containsText", { text: "completed", format: { fill: "#E2F0D9", font: { color: "#375623" } } });
review.getRange("AB2:AB122").conditionalFormats.add("containsText", { text: "reject", format: { fill: "#F4CCCC", font: { color: "#9C0006" } } });
review.getRange("AB2:AB122").conditionalFormats.add("containsText", { text: "hold", format: { fill: "#FCE4D6", font: { color: "#9C6500" } } });

const lists = workbook.worksheets.add("Field_Reference");
lists.getRange("A1:C1").values = [["字段", "允许值", "含义"]];
header(lists.getRange("A1:C1"), "#7F6000");
lists.getRange("A2:C14").values = [
  ["review_status", "pending | in_progress | completed", "人工复核进度"],
  ["license_evidence_status", "pending | verified | failed | unclear", "来源和授权证据状态"],
  ["corrected_procedure_relevance", "yes | no | uncertain", "是否包含可用于检索的过程"],
  ["corrected_functional_step_visible", "yes | no | uncertain", "是否有可见功能步骤"],
  ["privacy_risk", "none | low | high | uncertain", "隐私风险"],
  ["safety_risk", "none | low | high | uncertain", "危险、误用或不安全操作"],
  ["final_decision", "accept", "满足质量、许可、隐私和安全门槛"],
  ["final_decision", "reject", "不进入正式或备用数据集"],
  ["final_decision", "hold", "证据不足，需要项目负责人处理"],
  ["dataset_split", "development", "可用于开发和阈值选择"],
  ["dataset_split", "source_disjoint_test", "冻结测试来源；不可调参"],
  ["dataset_split", "excluded", "不进入数据集"],
  ["reviewed_at", "ISO-8601", "带时区时间戳"],
];
body(lists.getRange("A2:C14"));
lists.getRange("A:A").format.columnWidth = 38;
lists.getRange("B:B").format.columnWidth = 48;
lists.getRange("C:C").format.columnWidth = 62;
lists.getRange("A1:C14").format.autofitRows();
lists.freezePanes.freezeRows(1);

for (const sheetName of ["Progress", "Instructions", "Validation_Lists", "Review_Form", "Field_Reference"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: sheetName === "Review_Form" ? 0.45 : 0.9, format: "png" });
  await fs.writeFile(path.join(outputDir, `R1_${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(output);
await fs.copyFile(output, bundleOutput);
console.log(JSON.stringify({ output, bundleOutput, rows: rows.length - 1 }));
