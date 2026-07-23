import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const bundleDir = process.argv[2];
const output = process.argv[3];
if (!bundleDir || !output) {
  throw new Error("Usage: node build_r1_micro_review_workbook.mjs <bundle-dir> <output.xlsx>");
}
const input = path.join(bundleDir, "review_form.csv");
const bundleOutput = path.join(bundleDir, "R1_video_review_workbook.xlsx");
const previewDir = path.join(path.dirname(output), "r1-espresso-gap-previews");

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
      } else if (char === '"') quoted = false;
      else value += char;
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

function styleHeader(range, fill = "#1F4E78") {
  range.format = {
    fill,
    font: { bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#A6B4C2" },
  };
}

function styleBody(range) {
  range.format = {
    verticalAlignment: "top",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#D9E2F3" },
  };
}

await fs.mkdir(path.dirname(output), { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
const rows = parseCsv(await fs.readFile(input, "utf8"));
if (rows.length < 2 || rows[0].length !== 30) {
  throw new Error(`Expected 30 columns and at least one review row, got ${rows[0]?.length ?? 0} columns and ${rows.length - 1} rows`);
}
const total = rows.length - 1;
const lastRow = total + 1;
const workbook = Workbook.create();

const progress = workbook.worksheets.add("Progress");
progress.mergeCells("A1:D1");
progress.getRange("A1").values = [[`R1 Espresso 缺口补充复核 · ${total} 条`]];
progress.getRange("A1:D1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
progress.getRange("A1:D1").format.rowHeight = 32;
progress.getRange("A3:D3").values = [["指标", "实际值", "要求", "状态"]];
styleHeader(progress.getRange("A3:D3"), "#548235");
progress.getRange("A4:A10").values = [
  ["总任务"], ["已完成"], ["剩余"], ["接受"], ["拒绝"], ["待定"], ["许可已核验"],
];
progress.getRange("B4:B10").formulas = [
  [`=COUNTA(Review_Form!A2:A${lastRow})`],
  [`=COUNTIF(Review_Form!T2:T${lastRow},"completed")`],
  ["=B4-B5"],
  [`=COUNTIF(Review_Form!AB2:AB${lastRow},"accept")`],
  [`=COUNTIF(Review_Form!AB2:AB${lastRow},"reject")`],
  [`=COUNTIF(Review_Form!AB2:AB${lastRow},"hold")`],
  [`=COUNTIF(Review_Form!U2:U${lastRow},"verified")`],
];
progress.getRange("C4:C10").values = [
  [String(total)], ["review_status=completed"], ["完成后应为 0"], ["final_decision=accept"],
  ["final_decision=reject"], ["final_decision=hold"], ["license_evidence_status=verified"],
];
progress.getRange("D4:D6").formulas = [
  [`=IF(B4=${total},"PASS","CHECK")`],
  [`=IF(B5=${total},"PASS","CHECK")`],
  ['=IF(B6=0,"PASS","CHECK")'],
];
styleBody(progress.getRange("A4:D10"));
progress.getRange("A12").values = [["完成率"]];
progress.getRange("B12").formulas = [["=IF(B4=0,0,B5/B4)"]];
progress.getRange("B12").format.numberFormat = "0.0%";
progress.getRange("A:A").format.columnWidth = 24;
progress.getRange("B:B").format.columnWidth = 16;
progress.getRange("C:C").format.columnWidth = 38;
progress.getRange("D:D").format.columnWidth = 14;
progress.getRange("D4:D6").conditionalFormats.add("containsText", {
  text: "PASS",
  format: { fill: "#E2F0D9", font: { bold: true, color: "#375623" } },
});
progress.getRange("D4:D6").conditionalFormats.add("containsText", {
  text: "CHECK",
  format: { fill: "#F4CCCC", font: { bold: true, color: "#9C0006" } },
});
progress.freezePanes.freezeRows(3);

const instructions = workbook.worksheets.add("Instructions");
instructions.mergeCells("A1:C1");
instructions.getRange("A1").values = [["R1 填写说明（仅 1 条 Espresso 候选）"]];
instructions.getRange("A1:C1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
};
instructions.getRange("A3:C3").values = [["顺序", "操作", "要求"]];
styleHeader(instructions.getRange("A3:C3"));
instructions.getRange("A4:C11").values = [
  [1, "打开同目录 index.html", "完整播放 espresso-040；采样帧只能辅助定位，不能代替完整视频。"],
  [2, "打开来源页", "核对 Pexels 作者、来源和许可；许可无疑问时填 verified。"],
  [3, "只填写黄色 S–AD 列", "不要修改 record_id、AI 原始字段、视频路径或采样帧路径。"],
  [4, "确认产品类别", "整台 Espresso Machine 应真实可见；有疑问可改为 Other 或 hold。"],
  [5, "确认功能步骤", "判断是否可见装卸手柄、按键、萃取等可检索操作步骤。"],
  [6, "检查隐私与安全", "分别填写 privacy_risk 和 safety_risk；本表不预设人工结论。"],
  [7, "给出最终决定与切分", "accept 时选 development 或 source_disjoint_test；拒绝时选 excluded。"],
  [8, "完成并保存", "review_status=completed；reviewed_at 使用带时区 ISO-8601，例如 2026-07-23T16:30:00+08:00。"],
];
styleBody(instructions.getRange("A4:C11"));
instructions.getRange("A:A").format.columnWidth = 10;
instructions.getRange("B:B").format.columnWidth = 34;
instructions.getRange("C:C").format.columnWidth = 86;
instructions.getRange("A3:C11").format.autofitRows();
instructions.freezePanes.freezeRows(3);

const validation = workbook.worksheets.add("Validation_Lists");
validation.getRange("A1:H1").values = [[
  "reviewer_id", "review_status", "license_evidence_status", "corrected_product",
  "yes_no_uncertain", "risk", "final_decision", "dataset_split",
]];
validation.getRange("A2:H5").values = [
  ["R1", "pending", "pending", "Espresso Machine", "yes", "none", "pending", "pending"],
  ["", "in_progress", "verified", "Other", "no", "low", "accept", "development"],
  ["", "completed", "failed", "", "uncertain", "high", "reject", "source_disjoint_test"],
  ["", "", "unclear", "", "", "uncertain", "hold", "excluded"],
];
styleHeader(validation.getRange("A1:H1"), "#7F6000");
styleBody(validation.getRange("A2:H5"));
validation.getRange("A:H").format.columnWidth = 24;
validation.freezePanes.freezeRows(1);

const review = workbook.worksheets.add("Review_Form");
review.getRange(`A1:AD${lastRow}`).values = rows;
styleHeader(review.getRange("A1:AD1"));
styleBody(review.getRange(`A2:AD${lastRow}`));
review.getRange(`A2:R${lastRow}`).format.fill = "#F2F2F2";
review.getRange(`S2:AD${lastRow}`).format.fill = "#FFF2CC";
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
review.getRange(`A1:AD${lastRow}`).format.autofitRows();
review.getRange(`S2:S${lastRow}`).dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$A$2:$A$2" } };
review.getRange(`T2:T${lastRow}`).dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$B$2:$B$4" } };
review.getRange(`U2:U${lastRow}`).dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$C$2:$C$5" } };
review.getRange(`V2:V${lastRow}`).dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$D$2:$D$3" } };
review.getRange(`W2:X${lastRow}`).dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$E$2:$E$4" } };
review.getRange(`Y2:Z${lastRow}`).dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$F$2:$F$5" } };
review.getRange(`AB2:AB${lastRow}`).dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$G$2:$G$5" } };
review.getRange(`AC2:AC${lastRow}`).dataValidation = { rule: { type: "list", formula1: "Validation_Lists!$H$2:$H$5" } };
review.getRange(`T2:T${lastRow}`).conditionalFormats.add("containsText", {
  text: "completed", format: { fill: "#E2F0D9", font: { color: "#375623" } },
});
review.getRange(`AB2:AB${lastRow}`).conditionalFormats.add("containsText", {
  text: "reject", format: { fill: "#F4CCCC", font: { color: "#9C0006" } },
});

const reference = workbook.worksheets.add("Field_Reference");
reference.getRange("A1:C1").values = [["字段", "允许值", "含义"]];
styleHeader(reference.getRange("A1:C1"), "#7F6000");
reference.getRange("A2:C14").values = [
  ["review_status", "pending | in_progress | completed", "人工复核进度"],
  ["license_evidence_status", "pending | verified | failed | unclear", "来源和许可证据状态"],
  ["corrected_product_class", "Espresso Machine | Other", "人工确认后的产品类别"],
  ["corrected_procedure_relevance", "yes | no | uncertain", "是否包含可用于检索的过程"],
  ["corrected_functional_step_visible", "yes | no | uncertain", "是否有可见功能步骤"],
  ["privacy_risk", "none | low | high | uncertain", "隐私风险"],
  ["safety_risk", "none | low | high | uncertain", "危险、误用或不安全操作风险"],
  ["correction_reason", "自由文本", "人工值与 AI 不同或拒绝/待定时说明原因"],
  ["final_decision", "accept | reject | hold", "最终纳入决定"],
  ["dataset_split", "development", "开发与阈值选择"],
  ["dataset_split", "source_disjoint_test", "来源隔离测试集"],
  ["dataset_split", "excluded", "不进入数据集"],
  ["reviewed_at", "ISO-8601", "带时区时间戳"],
];
styleBody(reference.getRange("A2:C14"));
reference.getRange("A:A").format.columnWidth = 38;
reference.getRange("B:B").format.columnWidth = 48;
reference.getRange("C:C").format.columnWidth = 62;
reference.getRange("A1:C14").format.autofitRows();
reference.freezePanes.freezeRows(1);

for (const sheetName of ["Progress", "Instructions", "Validation_Lists", "Review_Form", "Field_Reference"]) {
  const preview = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: sheetName === "Review_Form" ? 0.7 : 0.9,
    format: "png",
  });
  await fs.writeFile(
    path.join(previewDir, `${sheetName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(output);
await fs.copyFile(output, bundleOutput);
const imported = await SpreadsheetFile.importXlsx(await FileBlob.load(output));
const sheets = await imported.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 4000,
});
const errors = await imported.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "R1 Espresso gap workbook formula error scan",
  maxChars: 5000,
});
for (const sheetName of ["Progress", "Instructions", "Validation_Lists", "Review_Form", "Field_Reference"]) {
  const preview = await imported.render({
    sheetName,
    autoCrop: "all",
    scale: sheetName === "Review_Form" ? 0.7 : 0.9,
    format: "png",
  });
  await fs.writeFile(
    path.join(previewDir, `imported_${sheetName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}
console.log(JSON.stringify({
  output,
  bundleOutput,
  rows: total,
  previewDir,
  sheets: sheets.ndjson,
  errors: errors.ndjson,
}));
