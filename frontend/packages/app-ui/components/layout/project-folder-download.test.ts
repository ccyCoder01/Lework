import { describe, expect, it } from "vitest";
import type { ProjectFileNode } from "./project-files";
import { getFolderZipEntryPath } from "./project-folder-download";

function makeFileNode(
	partial: Partial<ProjectFileNode> & Pick<ProjectFileNode, "name" | "path">,
): ProjectFileNode {
	return {
		type: "file",
		nodeType: "file",
		parentId: "",
		parentIds: [],
		children: [],
		size: 0,
		mimeType: "",
		modTime: 0,
		createdAt: 0,
		publicId: "",
		storageUri: "",
		initialFilePublicId: "",
		versionNo: 0,
		versionLabel: "",
		versionCount: 0,
		resourceType: "",
		...partial,
	};
}

describe("getFolderZipEntryPath", () => {
	it("builds zip paths from storage relative paths", () => {
		const folder = makeFileNode({
			name: "myProject",
			path: "uploads/myProject/",
			type: "directory",
			nodeType: "folder",
		});
		const file = makeFileNode({
			name: "main.go",
			path: "uploads/myProject/main.go",
		});

		expect(getFolderZipEntryPath(folder, file)).toBe("myProject/main.go");
	});

	it("builds nested zip paths", () => {
		const folder = makeFileNode({
			name: "myProject",
			path: "uploads/myProject/",
			type: "directory",
			nodeType: "folder",
		});
		const file = makeFileNode({
			name: "main.go",
			path: "uploads/myProject/src/main.go",
		});

		expect(getFolderZipEntryPath(folder, file)).toBe("myProject/src/main.go");
	});
});
