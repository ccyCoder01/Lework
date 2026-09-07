import { fireEvent, render, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { PdfPreview } from "./PdfPreview";

const pdfMocks = vi.hoisted(() => ({
	destroy: vi.fn(async () => undefined),
}));

vi.mock("pdfjs-dist/legacy/build/pdf.mjs", () => ({
	GlobalWorkerOptions: { workerSrc: "" },
	getDocument: () => ({
		destroy: pdfMocks.destroy,
		promise: Promise.resolve({
			fingerprints: ["pdf-fingerprint", null],
			numPages: 1,
			getPage: async () => ({
				getTextContent: async () => ({
					items: [
						{
							dir: "ltr",
							fontName: "sans",
							hasEOL: true,
							height: 12,
							str: "Selectable PDF text",
							transform: [1, 0, 0, 1, 0, 0],
							width: 100,
						},
					],
					lang: null,
					styles: {},
				}),
				getViewport: ({ scale }: { scale: number }) => ({
					convertToPdfPoint: (x: number, y: number) => [x / scale, y / scale],
					height: 800 * scale,
					rotation: 0,
					scale,
					width: 600 * scale,
				}),
				render: () => ({
					cancel: vi.fn(),
					promise: Promise.resolve(),
				}),
			}),
		}),
	}),
	TextLayer: class TextLayer {
		textDivs: HTMLElement[];

		constructor({
			container,
			textContentSource,
		}: {
			container: HTMLElement;
			textContentSource: { items: Array<{ str: string }> };
		}) {
			this.textDivs = textContentSource.items.map((item) => {
				const span = document.createElement("span");
				span.textContent = item.str;
				span.style.setProperty("--font-height", "12px");
				container.appendChild(span);
				return span;
			});
		}

		async render() {
			return undefined;
		}

		cancel() {
			return undefined;
		}
	},
}));

beforeAll(() => {
	vi.stubGlobal(
		"ResizeObserver",
		class ResizeObserver {
			observe() {
				return undefined;
			}
			disconnect() {
				return undefined;
			}
		},
	);
});

describe("PdfPreview", () => {
	it("renders a canvas-backed page and maps PDF.js text divs to source items", async () => {
		const view = render(
			createElement(PdfPreview, {
				buffer: new ArrayBuffer(8),
				fileName: "sample.pdf",
				onTextSelectionChange: vi.fn(),
			}),
		);

		const textItem = await waitFor(() => {
			const element = view.container.querySelector<HTMLElement>("[data-pdf-item-index='0']");
			expect(element).not.toBeNull();
			return element as HTMLElement;
		});

		expect(textItem.textContent).toBe("Selectable PDF text");
		expect(textItem.dataset.pdfPageIndex).toBe("0");
		expect(textItem.dataset.pdfHasEol).toBe("true");
		expect(view.container.querySelector("canvas")?.getAttribute("aria-label")).toBe(
			"sample.pdf 第 1 页",
		);
		expect(view.queryByRole("button", { name: "顺时针旋转" })).toBeNull();
		expect(
			view.container.querySelector("[data-pdf-page-index='0']")?.nextElementSibling,
		).toBeNull();

		const zoomLabel = view.getByText("131%");
		fireEvent.click(view.getByRole("button", { name: "放大" }));
		await waitFor(() => expect(zoomLabel.textContent).toBe("150%"));
	});
});
