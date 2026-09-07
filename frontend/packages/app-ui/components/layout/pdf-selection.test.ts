import { afterEach, describe, expect, it, vi } from "vitest";
import {
	clearPdfBrowserSelection,
	observePdfTextSelection,
	type PdfPageViewport,
	readPdfTextSelection,
} from "./pdf-selection";

afterEach(() => {
	window.getSelection()?.removeAllRanges();
	document.body.replaceChildren();
});

describe("PDF text selection", () => {
	it("returns text item offsets, responsive page coordinates, and PDF coordinates", () => {
		const host = document.createElement("div");
		const page = document.createElement("section");
		page.dataset.pdfPageIndex = "1";
		const first = createTextItem("Hello", 1, 4, true);
		const second = createTextItem("World", 1, 5, false);
		page.append(first, second);
		host.appendChild(page);
		document.body.appendChild(host);

		Object.defineProperty(page, "getBoundingClientRect", {
			value: () => new DOMRect(100, 200, 400, 600),
		});

		const range = document.createRange();
		range.setStart(first.firstChild as Text, 1);
		range.setEnd(second.firstChild as Text, 3);
		Object.defineProperty(range, "getClientRects", {
			value: () => [new DOMRect(120, 240, 80, 20)],
		});
		window.getSelection()?.addRange(range);

		const viewport: PdfPageViewport = {
			width: 400,
			height: 600,
			convertToPdfPoint: (x, y) => [x / 2, 300 - y / 2],
		};
		const result = readPdfTextSelection({
			host,
			pageViewports: new Map([[1, viewport]]),
			sourceIdentity: {
				contentHash: "sha256",
				documentFingerprint: "fingerprint",
			},
		});

		expect(result).toMatchObject({
			format: "pdf",
			text: "ello\nWor",
			surfaceKind: "page",
			surfaceIndex: 1,
			boundingRect: { x: 120, y: 240, width: 80, height: 20 },
			segments: [
				{
					pageIndex: 1,
					pageNumber: 2,
					itemIndex: 4,
					startOffset: 1,
					endOffset: 5,
					text: "ello",
					hasEOL: true,
					sourceRef: {
						contentHash: "sha256",
						documentFingerprint: "fingerprint",
						exactText: "ello",
						prefix: "H",
					},
				},
				{
					itemIndex: 5,
					startOffset: 0,
					endOffset: 3,
					text: "Wor",
				},
			],
		});
		expect(result?.rects[0]).toEqual({
			pageIndex: 1,
			pageNumber: 2,
			viewport: { x: 120, y: 240, width: 80, height: 20 },
			page: { x: 20, y: 40, width: 80, height: 20 },
			normalized: {
				x: 0.05,
				y: 40 / 600,
				width: 0.2,
				height: 20 / 600,
			},
			pdfQuad: [
				{ x: 10, y: 280 },
				{ x: 50, y: 280 },
				{ x: 50, y: 270 },
				{ x: 10, y: 270 },
			],
		});
	});

	it("clears a browser selection owned by the PDF preview", () => {
		const host = document.createElement("div");
		const item = createTextItem("Selected", 0, 0, false);
		host.appendChild(item);
		document.body.appendChild(host);
		const range = document.createRange();
		range.selectNodeContents(item);
		window.getSelection()?.addRange(range);

		clearPdfBrowserSelection(host);

		expect(window.getSelection()?.rangeCount).toBe(0);
	});

	it("copies deterministic text reconstructed from PDF text items", () => {
		const host = document.createElement("div");
		const first = createTextItem("First", 0, 0, true);
		const second = createTextItem("Second", 0, 1, false);
		host.append(first, second);
		document.body.appendChild(host);
		const range = document.createRange();
		range.setStart(first.firstChild as Text, 0);
		range.setEnd(second.firstChild as Text, 6);
		window.getSelection()?.addRange(range);

		const onCopy = vi.fn();
		const stopObserving = observePdfTextSelection({
			host,
			getPageViewports: () => new Map(),
			getSourceIdentity: () => ({ contentHash: null, documentFingerprint: null }),
			onChange: vi.fn(),
			onCopy,
		});
		const setData = vi.fn();
		const copyEvent = new Event("copy", { bubbles: true, cancelable: true });
		Object.defineProperty(copyEvent, "clipboardData", { value: { setData } });
		first.dispatchEvent(copyEvent);

		expect(copyEvent.defaultPrevented).toBe(true);
		expect(setData).toHaveBeenCalledWith("text/plain", "First\nSecond");
		expect(onCopy).toHaveBeenCalledWith("First\nSecond");
		stopObserving();
	});
});

function createTextItem(
	text: string,
	pageIndex: number,
	itemIndex: number,
	hasEOL: boolean,
): HTMLSpanElement {
	const span = document.createElement("span");
	span.textContent = text;
	span.dataset.pdfPageIndex = String(pageIndex);
	span.dataset.pdfItemIndex = String(itemIndex);
	span.dataset.pdfHasEol = String(hasEOL);
	return span;
}
