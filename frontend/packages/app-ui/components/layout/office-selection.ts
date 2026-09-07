export type OfficeSelectionFormat = "docx" | "pptx" | "xlsx";

export type OfficeSurfaceKind = "page" | "slide" | "sheet";

export type OfficeRect = {
	x: number;
	y: number;
	width: number;
	height: number;
};

export type OfficeSurfaceRect = {
	surfaceIndex: number;
	viewport: OfficeRect;
	surface: OfficeRect;
	normalized: OfficeRect;
};

export type OfficeRenderSelectionSegment = {
	format: "docx" | "pptx";
	surfaceIndex: number;
	runIndex: number;
	startOffset: number;
	endOffset: number;
	text: string;
	offsetEncoding: "utf16";
};

export type OfficeSheetSelectionSegment = {
	format: "xlsx";
	surfaceIndex: number;
	sheetName: string;
	startCell: string;
	endCell: string;
	mode: "cells" | "rows" | "cols" | "all";
};

export type OfficeTextSelection = {
	format: OfficeSelectionFormat;
	text: string;
	contextBefore: string;
	contextAfter: string;
	surfaceKind: OfficeSurfaceKind;
	surfaceIndex: number;
	boundingRect: OfficeRect | null;
	rects: OfficeSurfaceRect[];
	segments: Array<OfficeRenderSelectionSegment | OfficeSheetSelectionSegment>;
};

export type XlsxCellAddress = {
	row: number;
	col: number;
};

export type XlsxCellSelection = {
	anchor: XlsxCellAddress;
	active: XlsxCellAddress;
	mode: "cells" | "rows" | "cols" | "all";
};

export type XlsxOneBasedRange = {
	startRow: number;
	endRow: number;
	startCol: number;
	endCol: number;
};

const OFFICE_SURFACE_SELECTOR = "[data-office-surface-index]";
const OFFICE_RUN_SELECTOR = "[data-office-run-index]";

export function observeOfficeTextSelection({
	host,
	format,
	onChange,
}: {
	host: HTMLElement;
	format: "docx" | "pptx";
	onChange: (selection: OfficeTextSelection | null) => void;
}): () => void {
	let frame = 0;
	let hadSelection = false;

	const emitSelection = () => {
		frame = 0;
		const selection = readOfficeTextSelection(host, format);
		if (selection) {
			hadSelection = true;
			onChange(selection);
			return;
		}
		if (hadSelection) {
			hadSelection = false;
			onChange(null);
		}
	};

	const schedule = () => {
		cancelAnimationFrame(frame);
		frame = requestAnimationFrame(emitSelection);
	};

	document.addEventListener("selectionchange", schedule);
	host.addEventListener("pointerup", schedule);
	host.addEventListener("keyup", schedule);
	window.addEventListener("resize", schedule);

	return () => {
		cancelAnimationFrame(frame);
		document.removeEventListener("selectionchange", schedule);
		host.removeEventListener("pointerup", schedule);
		host.removeEventListener("keyup", schedule);
		window.removeEventListener("resize", schedule);
	};
}

export function readOfficeTextSelection(
	host: HTMLElement,
	format: "docx" | "pptx",
	selection: Selection | null = window.getSelection(),
): OfficeTextSelection | null {
	if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
	if (!isNodeWithin(host, selection.anchorNode) || !isNodeWithin(host, selection.focusNode)) {
		return null;
	}

	const range = selection.getRangeAt(0);
	const spans = Array.from(host.querySelectorAll<HTMLElement>(OFFICE_RUN_SELECTOR));
	const segments = spans
		.filter((span) => rangeIntersectsNode(range, span))
		.map((span) => createRenderSegment(range, span, format))
		.filter((segment): segment is OfficeRenderSelectionSegment => segment !== null);

	const firstSegment = segments[0];
	if (!firstSegment) return null;
	const text = segments.map((segment) => segment.text).join("");
	if (text.trim().length === 0) return null;
	const { contextBefore, contextAfter } = readRenderSelectionContext(spans, segments);

	const surfaces = Array.from(host.querySelectorAll<HTMLElement>(OFFICE_SURFACE_SELECTOR));
	const clientRects = getRangeClientRects(range);
	const rects = clientRects
		.map((rect) => mapClientRectToSurface(rect, surfaces))
		.filter((rect): rect is OfficeSurfaceRect => rect !== null);
	const boundingRect = unionRects(clientRects.map(toOfficeRect));

	return {
		format,
		text,
		contextBefore,
		contextAfter,
		surfaceKind: format === "docx" ? "page" : "slide",
		surfaceIndex: firstSegment.surfaceIndex,
		boundingRect,
		rects,
		segments,
	};
}

const SELECTION_CONTEXT_LIMIT = 160;

function readRenderSelectionContext(
	spans: HTMLElement[],
	segments: OfficeRenderSelectionSegment[],
): { contextBefore: string; contextAfter: string } {
	const first = segments[0];
	const last = segments[segments.length - 1];
	if (!first || !last) return { contextBefore: "", contextAfter: "" };

	const firstIndex = spans.findIndex((span) => matchesRenderSegment(span, first));
	const lastIndex = spans.findLastIndex((span) => matchesRenderSegment(span, last));
	if (firstIndex < 0 || lastIndex < 0) return { contextBefore: "", contextAfter: "" };

	const contextBefore = [
		...spans.slice(0, firstIndex).map((span) => span.textContent ?? ""),
		(spans[firstIndex]?.textContent ?? "").slice(0, first.startOffset),
	]
		.join("")
		.slice(-SELECTION_CONTEXT_LIMIT);
	const contextAfter = [
		(spans[lastIndex]?.textContent ?? "").slice(last.endOffset),
		...spans.slice(lastIndex + 1).map((span) => span.textContent ?? ""),
	]
		.join("")
		.slice(0, SELECTION_CONTEXT_LIMIT);

	return { contextBefore, contextAfter };
}

function matchesRenderSegment(span: HTMLElement, segment: OfficeRenderSelectionSegment): boolean {
	return (
		Number(span.dataset.officeSurfaceIndex) === segment.surfaceIndex &&
		Number(span.dataset.officeRunIndex) === segment.runIndex
	);
}

export function clearOfficeBrowserSelection(host: HTMLElement): void {
	const selection = window.getSelection();
	if (!selection) return;
	if (isNodeWithin(host, selection.anchorNode) || isNodeWithin(host, selection.focusNode)) {
		selection.removeAllRanges();
	}
}

export function normalizeXlsxSelectionRange(
	selection: XlsxCellSelection,
	usedRange: XlsxOneBasedRange,
): XlsxOneBasedRange {
	if (selection.mode === "all") return usedRange;
	if (selection.mode === "rows") {
		return {
			startRow: Math.min(selection.anchor.row, selection.active.row),
			endRow: Math.max(selection.anchor.row, selection.active.row),
			startCol: usedRange.startCol,
			endCol: usedRange.endCol,
		};
	}
	if (selection.mode === "cols") {
		return {
			startRow: usedRange.startRow,
			endRow: usedRange.endRow,
			startCol: Math.min(selection.anchor.col, selection.active.col),
			endCol: Math.max(selection.anchor.col, selection.active.col),
		};
	}
	return {
		startRow: Math.min(selection.anchor.row, selection.active.row),
		endRow: Math.max(selection.anchor.row, selection.active.row),
		startCol: Math.min(selection.anchor.col, selection.active.col),
		endCol: Math.max(selection.anchor.col, selection.active.col),
	};
}

export function buildXlsxSelectionText(
	range: XlsxOneBasedRange,
	getCellText: (row: number, col: number) => string,
): string {
	const rows: string[] = [];
	for (let row = range.startRow; row <= range.endRow; row += 1) {
		const cells: string[] = [];
		for (let col = range.startCol; col <= range.endCol; col += 1) {
			cells.push(getCellText(row, col));
		}
		rows.push(cells.join("\t"));
	}
	return rows.join("\n");
}

export function mapViewportRectToSurface(
	viewportRect: OfficeRect,
	surfaceIndex: number,
	surfaceRect: OfficeRect,
): OfficeSurfaceRect {
	const relative = {
		x: viewportRect.x - surfaceRect.x,
		y: viewportRect.y - surfaceRect.y,
		width: viewportRect.width,
		height: viewportRect.height,
	};
	return {
		surfaceIndex,
		viewport: viewportRect,
		surface: relative,
		normalized: {
			x: surfaceRect.width > 0 ? relative.x / surfaceRect.width : 0,
			y: surfaceRect.height > 0 ? relative.y / surfaceRect.height : 0,
			width: surfaceRect.width > 0 ? relative.width / surfaceRect.width : 0,
			height: surfaceRect.height > 0 ? relative.height / surfaceRect.height : 0,
		},
	};
}

function createRenderSegment(
	range: Range,
	span: HTMLElement,
	format: "docx" | "pptx",
): OfficeRenderSelectionSegment | null {
	const text = span.textContent ?? "";
	const surfaceIndex = Number(span.dataset.officeSurfaceIndex);
	const runIndex = Number(span.dataset.officeRunIndex);
	if (!Number.isInteger(surfaceIndex) || !Number.isInteger(runIndex)) return null;

	const startOffset = span.contains(range.startContainer)
		? getTextOffset(span, range.startContainer, range.startOffset)
		: 0;
	const endOffset = span.contains(range.endContainer)
		? getTextOffset(span, range.endContainer, range.endOffset)
		: text.length;
	const normalizedStart = Math.max(0, Math.min(text.length, startOffset));
	const normalizedEnd = Math.max(normalizedStart, Math.min(text.length, endOffset));

	return {
		format,
		surfaceIndex,
		runIndex,
		startOffset: normalizedStart,
		endOffset: normalizedEnd,
		text: text.slice(normalizedStart, normalizedEnd),
		offsetEncoding: "utf16",
	};
}

function getTextOffset(root: HTMLElement, node: Node, offset: number): number {
	try {
		const probe = document.createRange();
		probe.selectNodeContents(root);
		probe.setEnd(node, offset);
		return probe.toString().length;
	} catch {
		return 0;
	}
}

function rangeIntersectsNode(range: Range, node: Node): boolean {
	try {
		return range.intersectsNode(node);
	} catch {
		return false;
	}
}

function getRangeClientRects(range: Range): DOMRect[] {
	if (typeof range.getClientRects !== "function") return [];
	return Array.from(range.getClientRects()).filter((rect) => rect.width > 0 && rect.height > 0);
}

function mapClientRectToSurface(rect: DOMRect, surfaces: HTMLElement[]): OfficeSurfaceRect | null {
	let bestSurface: HTMLElement | null = null;
	let bestArea = 0;
	for (const surface of surfaces) {
		const surfaceRect = surface.getBoundingClientRect();
		const area = intersectionArea(rect, surfaceRect);
		if (area > bestArea) {
			bestArea = area;
			bestSurface = surface;
		}
	}
	if (!bestSurface) return null;
	const surfaceIndex = Number(bestSurface.dataset.officeSurfaceIndex);
	if (!Number.isInteger(surfaceIndex)) return null;
	return mapViewportRectToSurface(
		toOfficeRect(rect),
		surfaceIndex,
		toOfficeRect(bestSurface.getBoundingClientRect()),
	);
}

function intersectionArea(left: DOMRect, right: DOMRect): number {
	const width = Math.max(0, Math.min(left.right, right.right) - Math.max(left.left, right.left));
	const height = Math.max(0, Math.min(left.bottom, right.bottom) - Math.max(left.top, right.top));
	return width * height;
}

function unionRects(rects: OfficeRect[]): OfficeRect | null {
	if (rects.length === 0) return null;
	const left = Math.min(...rects.map((rect) => rect.x));
	const top = Math.min(...rects.map((rect) => rect.y));
	const right = Math.max(...rects.map((rect) => rect.x + rect.width));
	const bottom = Math.max(...rects.map((rect) => rect.y + rect.height));
	return { x: left, y: top, width: right - left, height: bottom - top };
}

function toOfficeRect(rect: Pick<DOMRect, "x" | "y" | "width" | "height">): OfficeRect {
	return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
}

function isNodeWithin(host: HTMLElement, node: Node | null): boolean {
	return Boolean(node && (node === host || host.contains(node)));
}
