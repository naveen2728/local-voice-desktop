import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPath = process.argv[2];
if (!inputPath) {
  throw new Error("Usage: node prepare_hr_campaign.mjs <contacts.xlsx> [output-directory]");
}
const outputDir = path.resolve(process.argv[3] ?? "outputs/hr_campaign");
const outputXlsx = path.join(outputDir, "HR Outreach - Cleaned Compliant Import.xlsx");
const outputCsv = path.join(outputDir, "hr_outreach_cleaned_import.csv");

function normHeader(v) {
  return String(v ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function titleCase(s) {
  return String(s ?? "")
    .trim()
    .toLowerCase()
    .replace(/\b[a-z]/g, (m) => m.toUpperCase());
}

function isEmail(s) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i.test(String(s ?? "").trim());
}

function csvEscape(v) {
  const s = String(v ?? "");
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

await fs.mkdir(outputDir, { recursive: true });

const sourceBlob = await FileBlob.load(inputPath);
const source = await SpreadsheetFile.importXlsx(sourceBlob);
const overview = await source.inspect({
  kind: "workbook,sheet,table",
  tableMaxRows: 10,
  tableMaxCols: 20,
  tableMaxCellChars: 120,
  maxChars: 20000,
});

const ws = source.worksheets.getItemAt(0);
const used = ws.getUsedRange(true);
const values = used.values ?? [];
if (values.length < 2) throw new Error("The workbook does not appear to contain data rows.");

let headerRowIndex = 0;
let bestEmailHits = -1;
for (let r = 0; r < Math.min(values.length, 10); r++) {
  const hits = values[r].filter((v) => isEmail(v)).length;
  if (hits > bestEmailHits) {
    bestEmailHits = hits;
    headerRowIndex = Math.max(0, r - 1);
  }
}

const rawHeaders = values[headerRowIndex].map((v, i) => String(v ?? "").trim() || `Column ${i + 1}`);
const headers = rawHeaders.map(normHeader);
const rows = values.slice(headerRowIndex + 1).filter((row) => row.some((v) => String(v ?? "").trim() !== ""));

let emailIdx = headers.findIndex((h) => ["email", "email_id", "mail", "mail_id", "e_mail"].includes(h));
if (emailIdx < 0) {
  const counts = rawHeaders.map((_, c) => rows.reduce((n, row) => n + (isEmail(row[c]) ? 1 : 0), 0));
  emailIdx = counts.indexOf(Math.max(...counts));
}

const firstIdx = headers.findIndex((h) => ["first_name", "firstname", "name", "contact_name", "hr_name"].includes(h));
const companyIdx = headers.findIndex((h) => ["company", "company_name", "organization", "organisation", "firm"].includes(h));
const roleIdx = headers.findIndex((h) => ["role", "title", "designation", "job_title", "position"].includes(h));
const sourceIdx = headers.findIndex((h) => ["source", "lead_source"].includes(h));

const seen = new Set();
const cleaned = [];
const rejected = [];
for (const row of rows) {
  const email = String(row[emailIdx] ?? "").trim().toLowerCase();
  const record = {
    first_name: firstIdx >= 0 ? titleCase(row[firstIdx]) : "",
    company: companyIdx >= 0 ? String(row[companyIdx] ?? "").trim() : "",
    role: roleIdx >= 0 ? String(row[roleIdx] ?? "").trim() : "",
    email,
    source: sourceIdx >= 0 ? String(row[sourceIdx] ?? "").trim() : "Provided list",
    lawful_basis_or_consent: "",
    segment: "HR",
    send_status: "Review before sending",
    opt_out: "",
    notes: "",
  };
  if (!isEmail(email)) {
    rejected.push([...Object.values(record), "Invalid or missing email"]);
    continue;
  }
  if (seen.has(email)) {
    rejected.push([...Object.values(record), "Duplicate email"]);
    continue;
  }
  seen.add(email);
  cleaned.push(Object.values(record));
}

const out = Workbook.create();
const summary = out.worksheets.add("Summary");
const cleanSheet = out.worksheets.add("Clean Import");
const rejectSheet = out.worksheets.add("Removed Rows");
const template = out.worksheets.add("Email Template");

summary.showGridLines = false;
summary.getRange("A1:D1").merge();
summary.getRange("A1").values = [["HR Outreach Compliance Summary"]];
summary.getRange("A3:B9").values = [
  ["Source file", path.basename(inputPath)],
  ["Source sheet", ws.name],
  ["Raw data rows", rows.length],
  ["Clean unique emails", cleaned.length],
  ["Removed rows", rejected.length],
  ["Required before sending", "Fill lawful basis/consent and honor opt-outs"],
  ["Recommended first batch", Math.min(50, cleaned.length)],
];
summary.getRange("A11:D15").values = [
  ["Before import checklist", "", "", ""],
  ["1", "Confirm the contacts are relevant and legally contactable.", "", ""],
  ["2", "Use a platform that supports unsubscribe/suppression lists.", "", ""],
  ["3", "Configure SPF, DKIM, and DMARC for the sending domain.", "", ""],
  ["4", "Send a small test batch first and remove bounces/opt-outs.", "", ""],
];

const cleanHeaders = [
  "first_name",
  "company",
  "role",
  "email",
  "source",
  "lawful_basis_or_consent",
  "segment",
  "send_status",
  "opt_out",
  "notes",
];
cleanSheet.getRangeByIndexes(0, 0, 1, cleanHeaders.length).values = [cleanHeaders];
if (cleaned.length) cleanSheet.getRangeByIndexes(1, 0, cleaned.length, cleanHeaders.length).values = cleaned;
cleanSheet.tables.add(`A1:J${Math.max(2, cleaned.length + 1)}`, true, "CleanImportTable");

const rejectHeaders = [...cleanHeaders, "removal_reason"];
rejectSheet.getRangeByIndexes(0, 0, 1, rejectHeaders.length).values = [rejectHeaders];
if (rejected.length) rejectSheet.getRangeByIndexes(1, 0, rejected.length, rejectHeaders.length).values = rejected;
rejectSheet.tables.add(`A1:K${Math.max(2, rejected.length + 1)}`, true, "RemovedRowsTable");

template.showGridLines = false;
template.getRange("A1:D1").merge();
template.getRange("A1").values = [["Compliant Outreach Draft"]];
template.getRange("A3:B12").values = [
  ["Subject", "Quick question about {{company}}"],
  ["Preview", "Short, relevant, and easy to opt out of."],
  ["Body", "Hi {{first_name}},"],
  ["", "I am {{your_name}} from {{your_company}}. I am reaching out because {{relevant_context}} and thought {{specific_offer}} may be useful for {{company}}."],
  ["", "We help HR teams with {{main_outcome}} without {{common_pain}}."],
  ["", "Would it be worth a quick conversation next week?"],
  ["", "Best,"],
  ["", "{{your_name}}"],
  ["Opt-out", "If this is not relevant, reply unsubscribe and I will not contact you again."],
  ["Compliance note", "Do not send until lawful_basis_or_consent is completed and opt-outs are suppressed."],
];

for (const sheet of [summary, cleanSheet, rejectSheet, template]) {
  const usedRange = sheet.getUsedRange(true);
  usedRange.format.font = { name: "Aptos", size: 10 };
  usedRange.format.wrapText = true;
  usedRange.format.borders = { preset: "all", style: "thin", color: "#D9E2EC" };
}

for (const sheet of [cleanSheet, rejectSheet]) {
  sheet.freezePanes.freezeRows(1);
  sheet.getRange("A1:K1").format = {
    fill: "#174A7C",
    font: { bold: true, color: "#FFFFFF" },
  };
  sheet.getRange("A:J").format.columnWidthPx = 145;
  sheet.getRange("D:D").format.columnWidthPx = 240;
  sheet.getRange("F:F").format.columnWidthPx = 220;
}

summary.getRange("A1:D1").format = { fill: "#174A7C", font: { bold: true, color: "#FFFFFF", size: 14 } };
summary.getRange("A3:A9").format.font = { bold: true };
summary.getRange("A11:D11").format = { fill: "#E6F0F8", font: { bold: true } };
summary.getRange("A:D").format.columnWidthPx = 210;
template.getRange("A1:D1").format = { fill: "#174A7C", font: { bold: true, color: "#FFFFFF", size: 14 } };
template.getRange("A3:A12").format.font = { bold: true };
template.getRange("B:B").format.columnWidthPx = 620;
template.getRange("A:A").format.columnWidthPx = 140;

const csvRows = [cleanHeaders, ...cleaned].map((row) => row.map(csvEscape).join(",")).join("\r\n");
await fs.writeFile(outputCsv, csvRows, "utf8");

const summaryCheck = await out.inspect({
  kind: "table",
  range: "Summary!A1:D15",
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 6,
  maxChars: 5000,
});
const errorScan = await out.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
const preview = await out.render({ sheetName: "Summary", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "summary_preview.png"), new Uint8Array(await preview.arrayBuffer()));

const exported = await SpreadsheetFile.exportXlsx(out);
await exported.save(outputXlsx);

console.log(JSON.stringify({
  sourceOverview: overview.ndjson.slice(0, 1200),
  outputXlsx,
  outputCsv,
  rawRows: rows.length,
  cleanedRows: cleaned.length,
  removedRows: rejected.length,
  summaryCheck: summaryCheck.ndjson,
  errorScan: errorScan.ndjson,
}, null, 2));
