export const FOLDER_UPLOAD_MAX_BYTES = 500 * 1024 * 1024;

export const FOLDER_UPLOAD_SIZE_EXCEEDED_MESSAGE = "文件夹大小超过 500MB 上限，请重新选择。";

export function getFolderUploadTotalSize(files: File[]): number {
	return files.reduce((total, file) => total + file.size, 0);
}

export function isFolderUploadSizeExceeded(files: File[]): boolean {
	return getFolderUploadTotalSize(files) > FOLDER_UPLOAD_MAX_BYTES;
}

export function getFileRelativePath(file: File): string | undefined {
	const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath?.trim();
	return relativePath || undefined;
}

export function getFolderNameFromFiles(files: File[]): string {
	for (const file of files) {
		const relativePath = getFileRelativePath(file);
		if (!relativePath) continue;
		const root = relativePath.split("/")[0]?.trim();
		if (root) return root;
	}
	return "文件夹";
}
