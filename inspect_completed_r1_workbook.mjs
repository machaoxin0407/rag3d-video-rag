import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input =
  process.argv[2] ??
  "C:\\Users\\MAXS\\Desktop\\single_reviewer_bundle_expansion_20260723\\R1_video_review_workbook.xlsx";
const outputDir = path.join(
  process.cwd(),
  "outputs",
  "20260723-video-expansion",
  "completed-r1-inspection",
);
await fs.mkdir(outputDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const sheets = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 4000,
});
const progress = await workbook.inspect({
  kind: "table",
  range: "Progress!A1:D22",
  include: "values,formulas",
  tableMaxRows: 30,
  tableMaxCols: 6,
  maxChars: 9000,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "completed R1 workbook formula error scan",
  maxChars: 5000,
});

const review = workbook.worksheets.getItem("Review_Form");
const values = review.getRange("A1:AD122").values;
const cellString = (value) =>
  value instanceof Date ? value.toISOString() : String(value ?? "");
const headers = values[0].map(cellString);
const index = Object.fromEntries(headers.map((header, column) => [header, column]));
const rows = values.slice(1).map((row) =>
  Object.fromEntries(headers.map((header, column) => [header, cellString(row[column])])),
);
const csvEscape = (value) => {
  const text = cellString(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const reviewCsv = values
  .map((row) => row.map(csvEscape).join(","))
  .join("\r\n");
await fs.writeFile(
  path.join(outputDir, "completed_r1_review_form.csv"),
  `${reviewCsv}\r\n`,
  "utf8",
);
const count = (field, value) => rows.filter((row) => row[field] === value).length;
const byClass = {};
for (const row of rows) {
  const key = row.ai_expected_product_class;
  if (!byClass[key]) byClass[key] = { total: 0, completed: 0, accept: 0, reject: 0, hold: 0 };
  byClass[key].total += 1;
  if (row.review_status === "completed") byClass[key].completed += 1;
  if (["accept", "reject", "hold"].includes(row.final_decision)) {
    byClass[key][row.final_decision] += 1;
  }
}
const summary = {
  input,
  rowCount: rows.length,
  headerCount: headers.length,
  missingHeaders: [
    "record_id",
    "review_status",
    "license_evidence_status",
    "final_decision",
    "dataset_split",
    "reviewed_at",
  ].filter((header) => !(header in index)),
  reviewStatus: {
    pending: count("review_status", "pending"),
    inProgress: count("review_status", "in_progress"),
    completed: count("review_status", "completed"),
  },
  license: {
    pending: count("license_evidence_status", "pending"),
    verified: count("license_evidence_status", "verified"),
    failed: count("license_evidence_status", "failed"),
    unclear: count("license_evidence_status", "unclear"),
  },
  decisions: {
    pending: count("final_decision", "pending"),
    accept: count("final_decision", "accept"),
    reject: count("final_decision", "reject"),
    hold: count("final_decision", "hold"),
  },
  splits: {
    pending: count("dataset_split", "pending"),
    development: count("dataset_split", "development"),
    sourceDisjointTest: count("dataset_split", "source_disjoint_test"),
    excluded: count("dataset_split", "excluded"),
  },
  byClass,
};
await fs.writeFile(
  path.join(outputDir, "completed_r1_summary.json"),
  JSON.stringify(summary, null, 2),
  "utf8",
);
for (const sheetName of [
  "Progress",
  "Instructions",
  "Validation_Lists",
  "Review_Form",
  "Field_Reference",
]) {
  const preview = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: sheetName === "Review_Form" ? 0.45 : 0.9,
    format: "png",
  });
  await fs.writeFile(
    path.join(outputDir, `${sheetName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}
console.log(
  JSON.stringify(
    {
      summary,
      sheets: sheets.ndjson,
      progress: progress.ndjson,
      errors: errors.ndjson,
    },
    null,
    2,
  ),
);
