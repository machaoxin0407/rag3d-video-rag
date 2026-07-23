import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const input = path.join(root, "data_video", "manifests", "paper_video_queries_v1.csv");
const outputDir = path.join(root, "outputs", "20260723-video-expansion");
const output = path.join(outputDir, "paper_video_query_design_v1.xlsx");

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
      } else {
        value += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(value);
      value = "";
    } else if (char === "\n") {
      row.push(value.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      value = "";
    } else {
      value += char;
    }
  }
  if (value.length || row.length) {
    row.push(value.replace(/\r$/, ""));
    rows.push(row);
  }
  return rows;
}

function styleHeader(range, fill = "#17365D") {
  range.format = {
    fill,
    font: { bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#B8C4CE" },
  };
}

function styleBody(range) {
  range.format = {
    verticalAlignment: "top",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#D9E2F3" },
  };
}

await fs.mkdir(outputDir, { recursive: true });
const csvRows = parseCsv(await fs.readFile(input, "utf8"));
if (csvRows.length !== 101) throw new Error(`Expected header + 100 rows, got ${csvRows.length}`);

const workbook = Workbook.create();

const readme = workbook.worksheets.add("README");
readme.mergeCells("A1:D1");
readme.getRange("A1").values = [["RAG3D 论文视频检索：100 问题设计册 v1"]];
readme.getRange("A1:D1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
readme.getRange("A1:D1").format.rowHeight = 32;
readme.getRange("A3:B14").values = [
  ["字段", "说明"],
  ["状态", "问题设计已在项目内冻结；待新增视频完成、切分冻结和最终索引重建后进行可回答性验证。尚未声称已在外部平台注册。"],
  ["规模", "100 个问题；Air Fryer / Espresso Machine / Pressure Cooker / Printer 各 17，Vacuum / Washing Machine 各 16。"],
  ["语言", "中文 50，英文 50；不是逐句翻译对，避免同义问题跨切分泄漏。"],
  ["切分", "development 60，source_disjoint_test 40。测试问题不得用于提示词、阈值、融合权重或候选数调优。"],
  ["类型", "operation、state、component、maintenance、troubleshooting、safety。"],
  ["候选池", "最终视频场景索引冻结后，由稀疏、稠密、视觉和融合检索器分别取候选，合并去重后再交给 AI 预标注。"],
  ["人工复核", "R1 对全部 100 个问题的所有合并候选进行 0–3 级相关性、时间边界和来源泄漏复核。"],
  ["相关性 0", "不相关。"],
  ["相关性 1", "仅同产品或背景相关，不能直接回答。"],
  ["相关性 2", "部分回答或展示相邻步骤。"],
  ["相关性 3", "直接回答，并有有效视觉、ASR 或 OCR 证据。"],
];
styleHeader(readme.getRange("A3:B3"), "#1F4E78");
styleBody(readme.getRange("A4:B14"));
readme.getRange("A3:A14").format.columnWidth = 22;
readme.getRange("B3:B14").format.columnWidth = 92;
readme.getRange("A3:B14").format.autofitRows();
readme.freezePanes.freezeRows(3);

const queries = workbook.worksheets.add("Queries");
queries.getRange("A1:I101").values = csvRows;
styleHeader(queries.getRange("A1:I1"), "#1F4E78");
styleBody(queries.getRange("A2:I101"));
queries.freezePanes.freezeRows(1);
queries.freezePanes.freezeColumns(2);
queries.getRange("A:A").format.columnWidth = 12;
queries.getRange("B:B").format.columnWidth = 48;
queries.getRange("C:C").format.columnWidth = 11;
queries.getRange("D:D").format.columnWidth = 22;
queries.getRange("E:E").format.columnWidth = 20;
queries.getRange("F:F").format.columnWidth = 24;
queries.getRange("G:G").format.columnWidth = 34;
queries.getRange("H:H").format.columnWidth = 50;
queries.getRange("I:I").format.columnWidth = 54;
queries.getRange("A1:I101").format.autofitRows();
queries.getRange("G2:G101").format.fill = "#FFF2CC";
queries.getRange("F2:F101").conditionalFormats.add("containsText", {
  text: "source_disjoint_test",
  format: { fill: "#FCE4D6", font: { color: "#9C0006" } },
});

const coverage = workbook.worksheets.add("Coverage_QA");
coverage.getRange("A1:D1").values = [["检查项", "实际值（公式）", "预期值", "结果"]];
styleHeader(coverage.getRange("A1:D1"), "#548235");
coverage.getRange("A2:A18").values = [
  ["问题总数"], ["中文"], ["英文"], ["development"], ["source_disjoint_test"],
  ["Air Fryer"], ["Espresso Machine"], ["Pressure Cooker"], ["Printer"], ["Vacuum"], ["Washing Machine"],
  ["operation"], ["state"], ["component"], ["maintenance"], ["troubleshooting"], ["safety"],
];
coverage.getRange("B2:B18").formulas = [
  ["=COUNTA(Queries!A2:A101)"],
  ['=COUNTIF(Queries!C2:C101,"zh-CN")'],
  ['=COUNTIF(Queries!C2:C101,"en")'],
  ['=COUNTIF(Queries!F2:F101,"development")'],
  ['=COUNTIF(Queries!F2:F101,"source_disjoint_test")'],
  ['=COUNTIF(Queries!D2:D101,"Air Fryer")'],
  ['=COUNTIF(Queries!D2:D101,"Espresso Machine")'],
  ['=COUNTIF(Queries!D2:D101,"Pressure Cooker")'],
  ['=COUNTIF(Queries!D2:D101,"Printer")'],
  ['=COUNTIF(Queries!D2:D101,"Vacuum")'],
  ['=COUNTIF(Queries!D2:D101,"Washing Machine")'],
  ['=COUNTIF(Queries!E2:E101,"operation")'],
  ['=COUNTIF(Queries!E2:E101,"state")'],
  ['=COUNTIF(Queries!E2:E101,"component")'],
  ['=COUNTIF(Queries!E2:E101,"maintenance")'],
  ['=COUNTIF(Queries!E2:E101,"troubleshooting")'],
  ['=COUNTIF(Queries!E2:E101,"safety")'],
];
coverage.getRange("C2:C18").values = [[100], [50], [50], [60], [40], [17], [17], [17], [17], [16], [16], [18], [18], [18], [18], [16], [12]];
coverage.getRange("D2").formulas = [['=IF(B2=C2,"PASS","CHECK")']];
coverage.getRange("D2:D18").fillDown();
styleBody(coverage.getRange("A2:D18"));
coverage.getRange("A:A").format.columnWidth = 28;
coverage.getRange("B:C").format.columnWidth = 19;
coverage.getRange("D:D").format.columnWidth = 14;
coverage.getRange("D2:D18").conditionalFormats.add("containsText", {
  text: "PASS",
  format: { fill: "#E2F0D9", font: { bold: true, color: "#375623" } },
});
coverage.getRange("D2:D18").conditionalFormats.add("containsText", {
  text: "CHECK",
  format: { fill: "#F4CCCC", font: { bold: true, color: "#9C0006" } },
});
coverage.freezePanes.freezeRows(1);

const schema = workbook.worksheets.add("Judgment_Schema");
schema.getRange("A1:Q1").values = [[
  "query_id", "query_text", "product_class", "query_type", "split",
  "candidate_scene_id", "ai_relevance_grade", "ai_start_time", "ai_end_time",
  "ai_evidence", "ai_uncertainty", "r1_relevance_grade", "r1_start_time",
  "r1_end_time", "r1_source_leakage", "correction_reason", "review_status",
]];
styleHeader(schema.getRange("A1:Q1"), "#7F6000");
schema.getRange("A2:Q6").values = [
  ["说明", "本表当前只固定字段结构；最终索引建立后由候选池生成器写入行。", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
  ["取值", "", "", "", "", "scene id", "0|1|2|3", "seconds", "seconds", "visible/ASR/OCR evidence", "text", "0|1|2|3", "seconds", "seconds", "yes|no|uncertain", "text", "pending|completed"],
  ["原则", "R1 复核前不得看到被比较检索方法的排名或分数。", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
  ["原则", "测试集不得用于提示词、阈值、融合权重或候选数调优。", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
  ["状态", "等待 44 条视频复核接受、场景索引重建和 pooled retrieval。", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
];
styleBody(schema.getRange("A2:Q6"));
schema.getRange("A:Q").format.columnWidth = 18;
schema.getRange("B:B").format.columnWidth = 55;
schema.getRange("J:K").format.columnWidth = 36;
schema.getRange("P:P").format.columnWidth = 36;
schema.getRange("A1:Q6").format.autofitRows();
schema.freezePanes.freezeRows(1);

for (const sheetName of ["README", "Queries", "Coverage_QA", "Judgment_Schema"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 0.8, format: "png" });
  const pngPath = path.join(outputDir, `${sheetName}.png`);
  await fs.writeFile(pngPath, new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(output);
console.log(JSON.stringify({ output, sheets: ["README", "Queries", "Coverage_QA", "Judgment_Schema"] }));
