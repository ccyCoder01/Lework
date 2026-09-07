"use client";

import { FilePreviewDrawer } from "./FilePreviewDrawer";
import { useFilePreviewStore } from "./file-preview-store";

export function FilePreviewHost() {
	const { file, isOpen, closeFilePreview } = useFilePreviewStore();

	return (
		<FilePreviewDrawer
			file={file}
			open={isOpen}
			onOpenChange={(open) => {
				if (!open) closeFilePreview();
			}}
		/>
	);
}
