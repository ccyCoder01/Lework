/// <reference path="./xlsx-calc.d.ts" />

import JSZip from "jszip";
import type { WorkBook } from "xlsx";

const SPREADSHEET_REL_TYPE =
	"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet";
const OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

type FormulaCalculator = (
	workbook: WorkBook,
	options?: { continue_after_error?: boolean; log_error?: boolean },
) => void;

type CachedValue = { text: string; type: "n" | "str" | "b" | "e" };

type FormulaCell = {
	f?: string;
	v?: string | number | boolean;
	t?: string;
};

type FormulaCellRef = {
	sheetName: string;
	address: string;
	formula: string;
};

/**
 * 预览器只绘制单元格里的缓存值。公式格没有 `<v>` 时先按已有缓存当输入试算，
 * 再把结果写回原始 xlsx，避免 SheetJS 整本另存丢失样式。
 * 必须从 worksheet XML 收集公式：SheetJS 读入时会丢掉没有缓存值的公式格。
 */
export async function hydrateXlsxFormulaCache(buffer: ArrayBuffer): Promise<ArrayBuffer> {
	try {
		const zip = await JSZip.loadAsync(buffer);
		const workbook = await workbookFromZip(zip);
		if (!workbook) return buffer;
		const uncached = collectUncachedFormulaCells(workbook);
		if (uncached.length === 0) return buffer;

		await fillUncachedFormulaValues(workbook);
		return await patchWorkbookZip(buffer, workbook, uncached);
	} catch {
		return buffer;
	}
}

export async function fillUncachedFormulaValues(workbook: WorkBook): Promise<void> {
	const uncached = collectUncachedFormulaCells(workbook);
	if (uncached.length === 0) return;

	const frozen = freezeCachedFormulas(workbook);
	try {
		const calculate = await loadFormulaCalculator();
		calculate(workbook, { continue_after_error: true, log_error: false });
	} catch {
		// 试算失败时仍用公式原文兜底，至少不会是空白格。
	} finally {
		restoreCachedFormulas(frozen);
	}

	for (const item of uncached) {
		const cell = workbook.Sheets[item.sheetName]?.[item.address];
		if (!cell || !isBlankValue(cell.v)) continue;
		cell.v = `=${item.formula}`;
	}
}

export function collectUncachedFormulaCells(workbook: WorkBook): FormulaCellRef[] {
	const refs: FormulaCellRef[] = [];
	for (const sheetName of workbook.SheetNames) {
		const sheet = workbook.Sheets[sheetName];
		if (!sheet) continue;
		forEachSheetCell(sheet, (address, cell) => {
			if (!cell.f || !isBlankValue(cell.v)) return;
			refs.push({ sheetName, address, formula: cell.f });
		});
	}
	return refs;
}

async function loadFormulaCalculator(): Promise<FormulaCalculator> {
	const mod = (await import("xlsx-calc")) as { default?: FormulaCalculator } & FormulaCalculator;
	const calculate = typeof mod.default === "function" ? mod.default : mod;
	if (typeof calculate !== "function") {
		throw new Error("xlsx-calc 未提供计算公式入口");
	}
	return calculate;
}

function freezeCachedFormulas(workbook: WorkBook): Array<{ cell: FormulaCell; formula: string }> {
	const frozen: Array<{ cell: FormulaCell; formula: string }> = [];
	for (const sheetName of workbook.SheetNames) {
		const sheet = workbook.Sheets[sheetName];
		if (!sheet) continue;
		forEachSheetCell(sheet, (_address, cell) => {
			if (!cell.f || isBlankValue(cell.v)) return;
			frozen.push({ cell, formula: cell.f });
			delete cell.f;
		});
	}
	return frozen;
}

function restoreCachedFormulas(frozen: Array<{ cell: FormulaCell; formula: string }>): void {
	for (const item of frozen) {
		item.cell.f = item.formula;
	}
}

function forEachSheetCell(
	sheet: WorkBook["Sheets"][string],
	visit: (address: string, cell: FormulaCell) => void,
): void {
	if (!sheet) return;
	for (const [address, cell] of Object.entries(sheet)) {
		if (address.startsWith("!")) continue;
		if (!cell || typeof cell !== "object") continue;
		visit(address, cell as FormulaCell);
	}
}

function isBlankValue(value: FormulaCell["v"]): boolean {
	return value === undefined || value === null || value === "";
}

async function workbookFromZip(zip: JSZip): Promise<WorkBook | null> {
	if (!zip.file("xl/workbook.xml")) return null;
	const sharedStrings = await readSharedStrings(zip);
	const sheetNames = await readSheetNames(zip);
	const sheetFiles = await resolveWorksheetPaths(zip, sheetNames);
	if (sheetFiles.size === 0) return null;

	const sheets: WorkBook["Sheets"] = {};
	for (const [sheetName, path] of sheetFiles) {
		const file = zip.file(path);
		if (!file) continue;
		sheets[sheetName] = worksheetFromXml(await file.async("string"), sharedStrings);
	}

	return {
		SheetNames: [...sheetFiles.keys()],
		Sheets: sheets,
	};
}

async function readSheetNames(zip: JSZip): Promise<string[]> {
	const workbookXml = await zip.file("xl/workbook.xml")?.async("string");
	if (!workbookXml) return [];
	const doc = new DOMParser().parseFromString(workbookXml, "application/xml");
	return elementsByLocalName(doc, "sheet")
		.map((sheet) => sheet.getAttribute("name"))
		.filter((name): name is string => Boolean(name));
}

async function readSharedStrings(zip: JSZip): Promise<string[]> {
	const xml = await zip.file("xl/sharedStrings.xml")?.async("string");
	if (!xml) return [];
	const doc = new DOMParser().parseFromString(xml, "application/xml");
	return elementsByLocalName(doc, "si").map((item) => item.textContent ?? "");
}

function worksheetFromXml(xml: string, sharedStrings: string[]): WorkBook["Sheets"][string] {
	const doc = new DOMParser().parseFromString(xml, "application/xml");
	const sheet: NonNullable<WorkBook["Sheets"][string]> = {};
	const sharedMasters = new Map<string, { formula: string; row: number; col: number }>();
	const pendingShared: Array<{
		address: string;
		cell: FormulaCell;
		si: string;
		row: number;
		col: number;
	}> = [];

	for (const node of elementsByLocalName(doc, "c")) {
		const address = node.getAttribute("r");
		if (!address) continue;
		const parsed = parseCellAddress(address);
		if (!parsed) continue;
		const type = node.getAttribute("t") ?? "";
		const formulaNode = childByLocalName(node, "f");
		const valueText = childByLocalName(node, "v")?.textContent ?? "";
		const cell: FormulaCell = {};
		if (formulaNode) {
			const formula = (formulaNode.textContent ?? "").trim();
			const si = formulaNode.getAttribute("si");
			if (formula) {
				cell.f = formula;
				if (si) sharedMasters.set(si, { formula, row: parsed.row, col: parsed.col });
			} else if (si) {
				pendingShared.push({ address, cell, si, row: parsed.row, col: parsed.col });
			}
		}
		if (valueText.length > 0) {
			assignCellValue(cell, type, valueText, sharedStrings);
		}
		if (cell.f || !isBlankValue(cell.v)) {
			sheet[address] = cell;
		}
	}

	for (const item of pendingShared) {
		const master = sharedMasters.get(item.si);
		if (!master) continue;
		item.cell.f = shiftFormula(master.formula, item.col - master.col, item.row - master.row);
		sheet[item.address] = item.cell;
	}

	return sheet;
}

function childByLocalName(parent: Element, localName: string): Element | undefined {
	return Array.from(parent.children).find((child) => child.localName === localName);
}

function assignCellValue(
	cell: FormulaCell,
	type: string,
	valueText: string,
	sharedStrings: string[],
): void {
	if (type === "s") {
		const index = Number(valueText);
		cell.t = "str";
		cell.v = sharedStrings[index] ?? valueText;
		return;
	}
	if (type === "str" || type === "inlineStr") {
		cell.t = "str";
		cell.v = valueText;
		return;
	}
	if (type === "b") {
		cell.t = "b";
		cell.v = valueText === "1" || valueText === "true";
		return;
	}
	if (type === "e") {
		cell.t = "e";
		cell.v = valueText;
		return;
	}
	const numeric = Number(valueText);
	if (valueText.length > 0 && Number.isFinite(numeric)) {
		cell.t = "n";
		cell.v = numeric;
		return;
	}
	cell.t = "str";
	cell.v = valueText;
}

function parseCellAddress(address: string): { col: number; row: number } | null {
	const match = address.match(/^([A-Z]+)(\d+)$/i);
	if (!match) return null;
	const column = match[1];
	const row = match[2];
	if (!column || !row) return null;
	return { col: columnToIndex(column.toUpperCase()), row: Number(row) };
}

function columnToIndex(column: string): number {
	let value = 0;
	for (const char of column) {
		value = value * 26 + (char.charCodeAt(0) - 64);
	}
	return value;
}

function indexToColumn(index: number): string {
	let value = index;
	let name = "";
	while (value > 0) {
		value -= 1;
		name = String.fromCharCode(65 + (value % 26)) + name;
		value = Math.floor(value / 26);
	}
	return name;
}

function shiftFormula(formula: string, colDelta: number, rowDelta: number): string {
	return formula.replace(
		/(\$?)([A-Z]+)(\$?)(\d+)/gi,
		(token, colAbs: string, column: string, rowAbs: string, row: string) => {
			const nextCol = colAbs
				? column.toUpperCase()
				: indexToColumn(columnToIndex(column.toUpperCase()) + colDelta);
			const nextRow = rowAbs ? row : String(Number(row) + rowDelta);
			if (!nextCol || Number(nextRow) < 1) return token;
			return `${colAbs}${nextCol}${rowAbs}${nextRow}`;
		},
	);
}

async function patchWorkbookZip(
	buffer: ArrayBuffer,
	workbook: WorkBook,
	uncached: FormulaCellRef[],
): Promise<ArrayBuffer> {
	const zip = await JSZip.loadAsync(buffer);
	const sheetFiles = await resolveWorksheetPaths(zip, workbook.SheetNames);
	const updatesBySheet = new Map<string, Map<string, CachedValue>>();

	for (const item of uncached) {
		const cell = workbook.Sheets[item.sheetName]?.[item.address];
		const cached = cell ? serializeFormulaResult(cell as FormulaCell) : null;
		if (!cached) continue;
		const sheetUpdates = updatesBySheet.get(item.sheetName) ?? new Map<string, CachedValue>();
		sheetUpdates.set(item.address, cached);
		updatesBySheet.set(item.sheetName, sheetUpdates);
	}

	if (updatesBySheet.size === 0) return buffer;

	for (const [sheetName, updates] of updatesBySheet) {
		const path = sheetFiles.get(sheetName);
		if (!path) continue;
		const file = zip.file(path);
		if (!file) continue;
		const xml = await file.async("string");
		zip.file(path, patchSheetXml(xml, updates));
	}

	return zip.generateAsync({ type: "arraybuffer", compression: "DEFLATE" });
}

async function resolveWorksheetPaths(
	zip: JSZip,
	sheetNames: string[],
): Promise<Map<string, string>> {
	const workbookXml = await zip.file("xl/workbook.xml")?.async("string");
	const relsXml = await zip.file("xl/_rels/workbook.xml.rels")?.async("string");
	const paths = new Map<string, string>();

	if (workbookXml && relsXml) {
		const workbookDoc = new DOMParser().parseFromString(workbookXml, "application/xml");
		const relsDoc = new DOMParser().parseFromString(relsXml, "application/xml");
		const relTargets = new Map<string, string>();

		for (const rel of elementsByLocalName(relsDoc, "Relationship")) {
			const type = rel.getAttribute("Type") ?? "";
			if (type !== SPREADSHEET_REL_TYPE) continue;
			const id = rel.getAttribute("Id");
			const target = rel.getAttribute("Target");
			if (!id || !target) continue;
			relTargets.set(id, resolveWorksheetTarget(target));
		}

		for (const sheet of elementsByLocalName(workbookDoc, "sheet")) {
			const name = sheet.getAttribute("name");
			const relId =
				sheet.getAttributeNS(OFFICE_REL_NS, "id") ??
				sheet.getAttribute("r:id") ??
				sheet.getAttribute("id");
			if (!name || !relId) continue;
			const path = relTargets.get(relId);
			if (path) paths.set(name, path);
		}
	}

	if (paths.size === sheetNames.length) return paths;

	const worksheetFiles = Object.keys(zip.files)
		.filter((path) => /^xl\/worksheets\/[^/]+\.xml$/i.test(path))
		.sort();
	sheetNames.forEach((name, index) => {
		if (!paths.has(name) && worksheetFiles[index]) {
			paths.set(name, worksheetFiles[index]);
		}
	});
	return paths;
}

function elementsByLocalName(doc: Document, localName: string): Element[] {
	return Array.from(doc.getElementsByTagName("*")).filter(
		(element) => element.localName === localName,
	);
}

function resolveWorksheetTarget(target: string): string {
	const normalized = target.replace(/^\//, "");
	return normalized.startsWith("xl/") ? normalized : `xl/${normalized}`;
}

export function patchSheetXml(xml: string, updates: Map<string, CachedValue>): string {
	let next = xml;
	for (const [address, value] of updates) {
		next = patchSheetCell(next, address, value);
	}
	return next;
}

function patchSheetCell(xml: string, address: string, value: CachedValue): string {
	const cellPattern = new RegExp(
		`<c\\b(?=[^>]*\\br="${escapeRegExp(address)}")([^>]*)>([\\s\\S]*?)</c>`,
	);
	return xml.replace(cellPattern, (full, attrs: string, inner: string) => {
		if (!/<f[\s>/]/.test(inner)) return full;
		if (hasCachedValue(inner)) return full;

		const nextAttrs = applyCellTypeAttr(attrs, value.type);
		const withoutValue = inner.replace(/<v\b[^>]*>[\s\S]*?<\/v>|<v\s*\/>/g, "");
		const valueXml = `<v>${escapeXml(value.text)}</v>`;
		const nextInner = /<\/f>/.test(withoutValue)
			? withoutValue.replace(/<\/f>/, `</f>${valueXml}`)
			: `${valueXml}${withoutValue}`;
		return `<c${nextAttrs}>${nextInner}</c>`;
	});
}

function applyCellTypeAttr(attrs: string, type: CachedValue["type"]): string {
	const withoutType = attrs.replace(/\s+t="[^"]*"/g, "");
	if (type === "n") return withoutType;
	return `${withoutType} t="${type}"`;
}

function hasCachedValue(inner: string): boolean {
	const match = inner.match(/<v\b[^>]*>([\s\S]*?)<\/v>/);
	return Boolean(match?.[1]?.trim());
}

function serializeFormulaResult(cell: FormulaCell): CachedValue | null {
	if (typeof cell.v === "boolean" || cell.t === "b") {
		return { text: cell.v ? "1" : "0", type: "b" };
	}
	if (cell.t === "e" && typeof cell.v === "string") {
		return { text: cell.v, type: "e" };
	}
	if (typeof cell.v === "number" && Number.isFinite(cell.v)) {
		return { text: String(cell.v), type: "n" };
	}
	if (typeof cell.v === "string" && cell.v.length > 0) {
		return { text: cell.v, type: "str" };
	}
	return null;
}

function escapeXml(value: string): string {
	return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeRegExp(value: string): string {
	return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
