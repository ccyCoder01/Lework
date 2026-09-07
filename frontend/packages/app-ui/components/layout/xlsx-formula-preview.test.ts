import JSZip from "jszip";
import { describe, expect, it } from "vitest";
import {
	collectUncachedFormulaCells,
	fillUncachedFormulaValues,
	hydrateXlsxFormulaCache,
	patchSheetXml,
} from "./xlsx-formula-preview";

describe("xlsx formula preview", () => {
	it("calculates formula cells that have no cached value", async () => {
		const xlsx = await import("xlsx");
		const workbook = xlsx.utils.book_new();
		xlsx.utils.book_append_sheet(
			workbook,
			{
				A1: { t: "n", v: 2 },
				A2: { t: "n", v: 3 },
				A3: { f: "A1+A2" },
				"!ref": "A1:A3",
			},
			"Data",
		);

		expect(collectUncachedFormulaCells(workbook)).toEqual([
			{ sheetName: "Data", address: "A3", formula: "A1+A2" },
		]);

		await fillUncachedFormulaValues(workbook);
		expect(workbook.Sheets.Data?.A3?.v).toBe(5);
		expect(workbook.Sheets.Data?.A3?.f).toBe("A1+A2");
	});

	it("keeps Excel cached formula results instead of recalculating them", async () => {
		const xlsx = await import("xlsx");
		const workbook = xlsx.utils.book_new();
		xlsx.utils.book_append_sheet(
			workbook,
			{
				A1: { t: "n", v: 10, f: "1+2" },
				B1: { f: "A1*2" },
				"!ref": "A1:B1",
			},
			"Data",
		);

		await fillUncachedFormulaValues(workbook);
		expect(workbook.Sheets.Data?.A1?.v).toBe(10);
		expect(workbook.Sheets.Data?.A1?.f).toBe("1+2");
		expect(workbook.Sheets.Data?.B1?.v).toBe(20);
	});

	it("falls back to the formula text when the engine cannot evaluate it", async () => {
		const xlsx = await import("xlsx");
		const workbook = xlsx.utils.book_new();
		xlsx.utils.book_append_sheet(
			workbook,
			{
				A1: { f: "NOT_A_REAL_FUNCTION(1)" },
				"!ref": "A1",
			},
			"Data",
		);

		await fillUncachedFormulaValues(workbook);
		expect(workbook.Sheets.Data?.A1?.v).toBe("=NOT_A_REAL_FUNCTION(1)");
	});

	it("writes calculated values into the original worksheet xml", async () => {
		const xlsx = await import("xlsx");
		const workbook = xlsx.utils.book_new();
		xlsx.utils.book_append_sheet(
			workbook,
			{
				A1: { t: "n", v: 2 },
				A2: { t: "n", v: 3 },
				A3: { f: "A1+A2" },
				"!ref": "A1:A3",
			},
			"Data",
		);
		const buffer = xlsx.write(workbook, { type: "array", bookType: "xlsx" }) as ArrayBuffer;
		const parsed = xlsx.read(buffer, { type: "array" });
		expect(parsed.Sheets[parsed.SheetNames[0] ?? ""]?.A3 ?? parsed.Sheets.Data?.A3).toBeUndefined();
		const hydrated = await hydrateXlsxFormulaCache(buffer);
		const zip = await JSZip.loadAsync(hydrated);
		const sheetXml = await zip.file("xl/worksheets/sheet1.xml")?.async("string");
		expect(sheetXml).toContain('r="A3"');
		expect(sheetXml).toMatch(/<f[^>]*>A1\+A2<\/f><v>5<\/v>/);
	});

	it("does not overwrite a cell that already has a cached value", () => {
		const xml = `<c r="A3"><f>A1+A2</f><v>9</v></c>`;
		const patched = patchSheetXml(xml, new Map([["A3", { text: "5", type: "n" }]]));
		expect(patched).toBe(xml);
	});
});
