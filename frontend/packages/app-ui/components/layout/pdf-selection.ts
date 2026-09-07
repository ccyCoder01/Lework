export type PdfRect = {
	x: number;
	y: number;
	width: number;
	height: number;
};

export type PdfPoint = {
	x: number;
	y: number;
};

export type PdfQuad = [PdfPoint, PdfPoint, PdfPoint, PdfPoint];

export type PdfSourceIdentity = {
	contentHash: string | null;
	documentFingerprint: string | null;
};

export type PdfSourceRef = PdfSourceIdentity & {
	kind: "pdf-text-item";
	pageIndex: number;
	pageNumber: number;
	itemIndex: number;
	startOffset: number;
	endOffset: number;
	offsetEncoding: "utf16";
	exactText: string;
	prefix: string;
	suffix: string;
};

export type PdfSelectionSegment = {
	format: "pdf";
	pageIndex: number;
	pageNumber: number;
	itemIndex: number;
	startOffset: number;
	endOffset: number;
	text: string;
	hasEOL: boolean;
	offsetEncoding: "utf16";
	sourceRef: PdfSourceRef;
};

export type PdfSelectionRect = {
	pageIndex: number;
	pageNumber: number;
	viewport: PdfRect;
	page: PdfRect;
	normalized: PdfRect;
	pdfQuad: PdfQuad;
};

export type PdfTextSelection = {
	format: "pdf";
	text: string;
	surfaceKind: "page";
	surfaceIndex: number;
	boundingRect: PdfRect | null;
	rects: PdfSelectionRect[];
	segments: PdfSelectionSegment[];
};

export type PdfPageViewport = {
	width: number;
	height: number;
	convertToPdfPoint(x: number, y: number): number[];
};

export type PdfPageViewportRegistry = ReadonlyMap<number, PdfPageViewport>;

const PDF_PAGE_SELECTOR = "[data-pdf-page-index]";
const PDF_TEXT_ITEM_SELECTOR = "[data-pdf-item-index]";

export function observePdfTextSelection({
	host,
	getSourceIdentity,
	getPageViewports,
	onChange,
	onCopy,
}: {
	host: HTMLElement;
	getSourceIdentity: () => PdfSourceIdentity;
	getPageViewports: () => PdfPageViewportRegistry;
	onChange: (selection: PdfTextSelection | null) => void;
	onCopy?: (text: string) => void;
}): () => void {
	let frame = 0;
	let hadSelection = false;

	const emitSelection = () => {
		frame = 0;
		const selection = readPdfTextSelection({
			host,
			sourceIdentity: getSourceIdentity(),
			pageViewports: getPageViewports(),
		});
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
	const copySelection = (event: ClipboardEvent) => {
		const selection = readPdfTextSelection({
			host,
			sourceIdentity: getSourceIdentity(),
			pageViewports: getPageViewports(),
		});
		if (!selection || !event.clipboardData) return;
		event.preventDefault();
		event.clipboardData.setData("text/plain", selection.text);
		onCopy?.(selection.text);
	};

	document.addEventListener("selectionchange", schedule);
	host.addEventListener("pointerup", schedule);
	host.addEventListener("keyup", schedule);
	host.addEventListener("scroll", schedule, true);
	host.addEventListener("copy", copySelection);
	window.addEventListener("resize", schedule);

	return () => {
		cancelAnimationFrame(frame);
		document.removeEventListener("selectionchange", schedule);
		host.removeEventListener("pointerup", schedule);
		host.removeEventListener("keyup", schedule);
		host.removeEventListener("scroll", schedule, true);
		host.removeEventListener("copy", copySelection);
		window.removeEventListener("resize", schedule);
	};
}

export function readPdfTextSelection({
	host,
	sourceIdentity,
	pageViewports,
	selection = window.getSelection(),
}: {
	host: HTMLElement;
	sourceIdentity: PdfSourceIdentity;
	pageViewports: PdfPageViewportRegistry;
	selection?: Selection | null;
}): PdfTextSelection | null {
	if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
	if (!isNodeWithin(host, selection.anchorNode) || !isNodeWithin(host, selection.focusNode)) {
		return null;
	}

	const range = selection.getRangeAt(0);
	const segments = Array.from(host.querySelectorAll<HTMLElement>(PDF_TEXT_ITEM_SELECTOR))
		.filter((span) => rangeIntersectsNode(range, span))
		.map((span) => createPdfSelectionSegment(range, span, sourceIdentity))
		.filter((segment): segment is PdfSelectionSegment => segment !== null);
	const firstSegment = segments[0];
	if (!firstSegment) return null;

	const text = buildPdfSelectionText(segments);
	if (text.trim().length === 0) return null;

	const pages = Array.from(host.querySelectorAll<HTMLElement>(PDF_PAGE_SELECTOR));
	const clientRects = getRangeClientRects(range);
	const rects = clientRects
		.map((rect) => mapClientRectToPdfPage(rect, pages, pageViewports))
		.filter((rect): rect is PdfSelectionRect => rect !== null);

	return {
		format: "pdf",
		text,
		surfaceKind: "page",
		surfaceIndex: firstSegment.pageIndex,
		boundingRect: unionRects(clientRects.map(toPdfRect)),
		rects,
		segments,
	};
}

export function buildPdfSelectionText(segments: PdfSelectionSegment[]): string {
	let text = "";
	for (const [index, segment] of segments.entries()) {
		if (index > 0) {
			const previous = segments[index - 1];
			if (previous && (previous.pageIndex !== segment.pageIndex || previous.hasEOL)) {
				text += "\n";
			}
		}
		text += segment.text;
	}
	return text;
}

export function clearPdfBrowserSelection(host: HTMLElement): void {
	const selection = window.getSelection();
	if (!selection) return;
	if (isNodeWithin(host, selection.anchorNode) || isNodeWithin(host, selection.focusNode)) {
		selection.removeAllRanges();
	}
}

function createPdfSelectionSegment(
	range: Range,
	span: HTMLElement,
	sourceIdentity: PdfSourceIdentity,
): PdfSelectionSegment | null {
	const itemText = span.textContent ?? "";
	const pageIndex = Number(span.dataset.pdfPageIndex);
	const itemIndex = Number(span.dataset.pdfItemIndex);
	if (!Number.isInteger(pageIndex) || !Number.isInteger(itemIndex)) return null;

	const startOffset = span.contains(range.startContainer)
		? getTextOffset(span, range.startContainer, range.startOffset)
		: 0;
	const endOffset = span.contains(range.endContainer)
		? getTextOffset(span, range.endContainer, range.endOffset)
		: itemText.length;
	const normalizedStart = Math.max(0, Math.min(itemText.length, startOffset));
	const normalizedEnd = Math.max(normalizedStart, Math.min(itemText.length, endOffset));
	if (normalizedStart === normalizedEnd) return null;

	const text = itemText.slice(normalizedStart, normalizedEnd);
	const hasEOL = span.dataset.pdfHasEol === "true" && normalizedEnd === itemText.length;
	const pageNumber = pageIndex + 1;

	return {
		format: "pdf",
		pageIndex,
		pageNumber,
		itemIndex,
		startOffset: normalizedStart,
		endOffset: normalizedEnd,
		text,
		hasEOL,
		offsetEncoding: "utf16",
		sourceRef: {
			kind: "pdf-text-item",
			...sourceIdentity,
			pageIndex,
			pageNumber,
			itemIndex,
			startOffset: normalizedStart,
			endOffset: normalizedEnd,
			offsetEncoding: "utf16",
			exactText: text,
			prefix: itemText.slice(Math.max(0, normalizedStart - 24), normalizedStart),
			suffix: itemText.slice(normalizedEnd, normalizedEnd + 24),
		},
	};
}

function mapClientRectToPdfPage(
	rect: DOMRect,
	pages: HTMLElement[],
	pageViewports: PdfPageViewportRegistry,
): PdfSelectionRect | null {
	const page = findBestPageForRect(rect, pages);
	if (!page) return null;
	const pageIndex = Number(page.dataset.pdfPageIndex);
	const viewport = pageViewports.get(pageIndex);
	if (!Number.isInteger(pageIndex) || !viewport) return null;

	const pageBounds = page.getBoundingClientRect();
	const pageRect = {
		x: rect.x - pageBounds.x,
		y: rect.y - pageBounds.y,
		width: rect.width,
		height: rect.height,
	};
	const topLeft = toPdfPoint(viewport.convertToPdfPoint(pageRect.x, pageRect.y));
	const topRight = toPdfPoint(viewport.convertToPdfPoint(pageRect.x + pageRect.width, pageRect.y));
	const bottomRight = toPdfPoint(
		viewport.convertToPdfPoint(pageRect.x + pageRect.width, pageRect.y + pageRect.height),
	);
	const bottomLeft = toPdfPoint(
		viewport.convertToPdfPoint(pageRect.x, pageRect.y + pageRect.height),
	);

	return {
		pageIndex,
		pageNumber: pageIndex + 1,
		viewport: toPdfRect(rect),
		page: pageRect,
		normalized: {
			x: pageBounds.width > 0 ? pageRect.x / pageBounds.width : 0,
			y: pageBounds.height > 0 ? pageRect.y / pageBounds.height : 0,
			width: pageBounds.width > 0 ? pageRect.width / pageBounds.width : 0,
			height: pageBounds.height > 0 ? pageRect.height / pageBounds.height : 0,
		},
		pdfQuad: [topLeft, topRight, bottomRight, bottomLeft],
	};
}

function findBestPageForRect(rect: DOMRect, pages: HTMLElement[]): HTMLElement | null {
	let bestPage: HTMLElement | null = null;
	let bestArea = 0;
	for (const page of pages) {
		const pageRect = page.getBoundingClientRect();
		const width = Math.max(
			0,
			Math.min(rect.right, pageRect.right) - Math.max(rect.left, pageRect.left),
		);
		const height = Math.max(
			0,
			Math.min(rect.bottom, pageRect.bottom) - Math.max(rect.top, pageRect.top),
		);
		const area = width * height;
		if (area > bestArea) {
			bestArea = area;
			bestPage = page;
		}
	}
	return bestPage;
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

function toPdfRect(rect: Pick<DOMRect, "x" | "y" | "width" | "height">): PdfRect {
	return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
}

function toPdfPoint(point: number[]): PdfPoint {
	return { x: point[0] ?? 0, y: point[1] ?? 0 };
}

function unionRects(rects: PdfRect[]): PdfRect | null {
	if (rects.length === 0) return null;
	const left = Math.min(...rects.map((rect) => rect.x));
	const top = Math.min(...rects.map((rect) => rect.y));
	const right = Math.max(...rects.map((rect) => rect.x + rect.width));
	const bottom = Math.max(...rects.map((rect) => rect.y + rect.height));
	return { x: left, y: top, width: right - left, height: bottom - top };
}

function isNodeWithin(host: HTMLElement, node: Node | null): boolean {
	return Boolean(node && (node === host || host.contains(node)));
}
