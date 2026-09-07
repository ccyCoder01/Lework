import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { StructuredComposer, type StructuredComposerHandle } from "./StructuredComposer";

function ReferenceComposerHarness() {
	const [value, setValue] = useState("");
	const composerRef = useRef<StructuredComposerHandle>(null);
	return (
		<>
			<button
				type="button"
				onClick={() =>
					composerRef.current?.setContent("帮我扩写这段内容 被引用的文字", [
						{
							kind: "reference",
							id: "file-v2",
							label: "被引用的文字",
							start: 9,
							end: 15,
						},
					])
				}
			>
				插入引用
			</button>
			<StructuredComposer
				ref={composerRef}
				value={value}
				onChange={setValue}
				onSubmit={vi.fn()}
				onPasteFiles={vi.fn()}
				onFocus={vi.fn()}
				onBlur={vi.fn()}
				placeholder="请输入"
				isProjectVariant={false}
			/>
		</>
	);
}

describe("StructuredComposer reference token", () => {
	it("renders and removes a document selection reference as one token", async () => {
		render(<ReferenceComposerHarness />);
		fireEvent.click(screen.getByRole("button", { name: "插入引用" }));

		const editor = screen.getByRole("textbox", { name: "请输入" });
		await waitFor(() => {
			expect(editor.querySelector('[data-mention-kind="reference"]')?.textContent).toContain(
				"被引用的文字",
			);
		});

		fireEvent.mouseDown(screen.getByRole("button", { name: "移除文档选区引用 被引用的文字" }));
		await waitFor(() => {
			expect(editor.textContent?.trim()).toBe("帮我扩写这段内容");
			expect(editor.querySelector('[data-mention-kind="reference"]')).toBeNull();
		});
	});
});
