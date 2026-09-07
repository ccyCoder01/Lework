import { describe, expect, it } from "vitest";
import {
	buildProjectFileTree,
	buildProjectFileTreeWithPaths,
	getProjectFileFlatDisplayPathLabel,
	getProjectFileFullDisplayPath,
	getProjectFileLocationLabel,
	getProjectFileSourceLabel,
	getProjectFileTypeLabel,
	getProjectFolderStats,
	matchesProjectFilePathSearch,
	type ProjectFileNode,
	unwrapProjectFileDisplayPath,
	unwrapProjectFileStorageRoots,
} from "./project-files";

describe("buildProjectFileTree", () => {
	it("builds nested folders from flat parent_id links", () => {
		const flat: ProjectFileNode[] = [
			{
				name: "uploads",
				path: "uploads/",
				type: "directory",
				nodeType: "folder",
				parentId: "",
				parentIds: [],
				children: [],
				size: 0,
				mimeType: "",
				modTime: 0,
				createdAt: 0,
				publicId: "folder_root",
				storageUri: "",
				initialFilePublicId: "folder_root",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
			{
				name: "myProject",
				path: "uploads/myProject/",
				type: "directory",
				nodeType: "folder",
				parentId: "folder_root",
				parentIds: ["folder_root"],
				children: [],
				size: 0,
				mimeType: "",
				modTime: 0,
				createdAt: 0,
				publicId: "folder_project",
				storageUri: "",
				initialFilePublicId: "folder_project",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
			{
				name: "main.go",
				path: "uploads/myProject/main.go",
				type: "file",
				nodeType: "file",
				parentId: "folder_project",
				parentIds: ["folder_root", "folder_project"],
				children: [],
				size: 12,
				mimeType: "text/plain",
				modTime: 0,
				createdAt: 0,
				publicId: "file_1",
				storageUri: "",
				initialFilePublicId: "file_1",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
		];

		const tree = buildProjectFileTree(flat);
		expect(tree).toHaveLength(1);
		expect(tree[0]?.children[0]?.children[0]?.name).toBe("main.go");
	});
});

describe("buildProjectFileTreeWithPaths", () => {
	it("nests files under folder nodes from parent_id", () => {
		const flat: ProjectFileNode[] = [
			{
				name: "uploads",
				path: "uploads/",
				type: "directory",
				nodeType: "folder",
				parentId: "",
				parentIds: [],
				children: [],
				size: 0,
				mimeType: "",
				modTime: 0,
				createdAt: 0,
				publicId: "folder_root",
				storageUri: "",
				initialFilePublicId: "folder_root",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
			{
				name: "myProject",
				path: "uploads/myProject/",
				type: "directory",
				nodeType: "folder",
				parentId: "folder_root",
				parentIds: ["folder_root"],
				children: [],
				size: 0,
				mimeType: "",
				modTime: 0,
				createdAt: 0,
				publicId: "folder_project",
				storageUri: "",
				initialFilePublicId: "folder_project",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
			{
				name: "main.go",
				path: "uploads/myProject/main.go",
				type: "file",
				nodeType: "file",
				parentId: "folder_project",
				parentIds: ["folder_root", "folder_project"],
				children: [],
				size: 12,
				mimeType: "text/plain",
				modTime: 0,
				createdAt: 0,
				publicId: "file_1",
				storageUri: "",
				initialFilePublicId: "file_1",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
		];

		const tree = buildProjectFileTreeWithPaths(flat);
		expect(tree).toHaveLength(1);
		expect(tree[0]?.children[0]?.children[0]?.name).toBe("main.go");
	});

	it("builds virtual folders from path when folder nodes are missing", () => {
		const flat: ProjectFileNode[] = [
			{
				name: "main.go",
				path: "uploads/myProject/main.go",
				type: "file",
				nodeType: "file",
				parentId: "",
				parentIds: [],
				children: [],
				size: 12,
				mimeType: "text/plain",
				modTime: 0,
				createdAt: 0,
				publicId: "file_1",
				storageUri: "",
				initialFilePublicId: "file_1",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
		];

		const tree = buildProjectFileTreeWithPaths(flat);
		expect(tree[0]?.name).toBe("uploads");
		expect(tree[0]?.children[0]?.name).toBe("myProject");
		expect(tree[0]?.children[0]?.children[0]?.name).toBe("main.go");
	});
});

describe("unwrapProjectFileStorageRoots", () => {
	it("promotes user folders above uploads root", () => {
		const tree: ProjectFileNode[] = [
			{
				name: "uploads",
				path: "uploads/",
				type: "directory",
				nodeType: "folder",
				parentId: "",
				parentIds: [],
				children: [
					{
						name: "myProject",
						path: "uploads/myProject/",
						type: "directory",
						nodeType: "folder",
						parentId: "folder_root",
						parentIds: ["folder_root"],
						children: [
							{
								name: "main.go",
								path: "uploads/myProject/main.go",
								type: "file",
								nodeType: "file",
								parentId: "folder_project",
								parentIds: ["folder_root", "folder_project"],
								children: [],
								size: 12,
								mimeType: "text/plain",
								modTime: 0,
								createdAt: 0,
								publicId: "file_1",
								storageUri: "",
								initialFilePublicId: "file_1",
								versionNo: 1,
								versionLabel: "",
								versionCount: 1,
								resourceType: "user_upload",
							},
						],
						size: 0,
						mimeType: "",
						modTime: 0,
						createdAt: 0,
						publicId: "folder_project",
						storageUri: "",
						initialFilePublicId: "folder_project",
						versionNo: 1,
						versionLabel: "",
						versionCount: 1,
						resourceType: "user_upload",
					},
				],
				size: 0,
				mimeType: "",
				modTime: 0,
				createdAt: 0,
				publicId: "folder_root",
				storageUri: "",
				initialFilePublicId: "folder_root",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
		];

		const unwrapped = unwrapProjectFileStorageRoots(tree);
		expect(unwrapped).toHaveLength(1);
		expect(unwrapped[0]?.name).toBe("myProject");
		expect(unwrapped[0]?.children[0]?.name).toBe("main.go");
	});

	it("unwraps task-scoped upload folders to root level", () => {
		const tree: ProjectFileNode[] = [
			{
				name: "测试",
				path: "uploads/_task/task_a/测试/",
				type: "directory",
				nodeType: "folder",
				parentId: "",
				parentIds: [],
				children: [
					{
						name: "a.txt",
						path: "uploads/_task/task_a/测试/a.txt",
						type: "file",
						nodeType: "file",
						parentId: "folder_a",
						parentIds: ["folder_a"],
						children: [],
						size: 1,
						mimeType: "text/plain",
						modTime: 0,
						createdAt: 0,
						publicId: "file_a",
						storageUri: "",
						initialFilePublicId: "file_a",
						versionNo: 1,
						versionLabel: "",
						versionCount: 1,
						resourceType: "user_upload",
					},
				],
				size: 0,
				mimeType: "",
				modTime: 0,
				createdAt: 0,
				publicId: "folder_a",
				storageUri: "",
				initialFilePublicId: "folder_a",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
			{
				name: "测试",
				path: "uploads/_task/task_b/测试/",
				type: "directory",
				nodeType: "folder",
				parentId: "",
				parentIds: [],
				children: [],
				size: 0,
				mimeType: "",
				modTime: 0,
				createdAt: 0,
				publicId: "folder_b",
				storageUri: "",
				initialFilePublicId: "folder_b",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
		];

		const unwrapped = unwrapProjectFileStorageRoots(tree);
		expect(unwrapped).toHaveLength(2);
		expect(unwrapped.every((node) => node.name === "测试")).toBe(true);
	});
});

describe("project file tree ordering", () => {
	it("sorts root siblings by createdAt descending before name", () => {
		const flat: ProjectFileNode[] = [
			{
				name: "测试",
				path: "uploads/_task/a/测试/",
				type: "directory",
				nodeType: "folder",
				parentId: "",
				parentIds: [],
				children: [],
				size: 0,
				mimeType: "",
				modTime: 0,
				createdAt: 1_000,
				publicId: "folder_old",
				storageUri: "",
				initialFilePublicId: "folder_old",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
			{
				name: "测试",
				path: "uploads/_task/b/测试/",
				type: "directory",
				nodeType: "folder",
				parentId: "",
				parentIds: [],
				children: [],
				size: 0,
				mimeType: "",
				modTime: 0,
				createdAt: 2_000,
				publicId: "folder_new",
				storageUri: "",
				initialFilePublicId: "folder_new",
				versionNo: 1,
				versionLabel: "",
				versionCount: 1,
				resourceType: "user_upload",
			},
		];

		const tree = unwrapProjectFileStorageRoots(buildProjectFileTreeWithPaths(flat));

		expect(tree[0]?.publicId).toBe("folder_new");
		expect(tree[1]?.publicId).toBe("folder_old");
	});
});

describe("getProjectFileTypeLabel", () => {
	it("returns folder label for directory nodes", () => {
		expect(
			getProjectFileTypeLabel({
				name: "myProject",
				mimeType: "",
				type: "directory",
				nodeType: "folder",
			}),
		).toBe("文件夹");
	});
});

describe("getProjectFileSourceLabel", () => {
	it("returns upload label for user_upload folders", () => {
		expect(
			getProjectFileSourceLabel({
				path: "uploads/测试/",
				resourceType: "user_upload",
			}),
		).toBe("上传文件");
	});
});

describe("unwrapProjectFileDisplayPath", () => {
	it("strips uploads prefix and task scope segments", () => {
		expect(unwrapProjectFileDisplayPath("uploads/_task/task_a/测试/a.txt")).toBe("测试/a.txt");
		expect(unwrapProjectFileDisplayPath("uploads/demo/report.pdf")).toBe("demo/report.pdf");
		expect(unwrapProjectFileDisplayPath("artifacts/summary.md")).toBe("summary.md");
	});

	it("builds user-facing location labels", () => {
		expect(
			getProjectFileLocationLabel({
				path: "uploads/_task/task_a/测试/a.txt",
			}),
		).toBe("测试");
		expect(
			getProjectFileLocationLabel({
				path: "uploads/demo/report.pdf",
			}),
		).toBe("demo");
	});

	it("shows flat path label only for nested files", () => {
		expect(
			getProjectFileFlatDisplayPathLabel({
				name: "report.pdf",
				path: "uploads/report.pdf",
				type: "file",
			}),
		).toBe("");
		expect(
			getProjectFileFlatDisplayPathLabel({
				name: "登录后-首页.png",
				path: "登录后截图/登录后-首页.png",
				type: "file",
			}),
		).toBe("登录后截图\\登录后-首页.png");
	});
});

describe("matchesProjectFilePathSearch", () => {
	it("matches keyword against user-facing path only", () => {
		const fileNode: ProjectFileNode = {
			name: "a.txt",
			path: "uploads/_task/task_a/测试/a.txt",
			type: "file",
			nodeType: "file",
			parentId: "",
			parentIds: [],
			children: [],
			size: 1,
			mimeType: "text/plain",
			modTime: 0,
			createdAt: 0,
			publicId: "file_a",
			storageUri: "",
			initialFilePublicId: "file_a",
			versionNo: 1,
			versionLabel: "",
			versionCount: 1,
			resourceType: "user_upload",
		};
		const folderNode: ProjectFileNode = {
			...fileNode,
			name: "测试",
			path: "uploads/_task/task_a/测试/",
			type: "directory",
			nodeType: "folder",
			publicId: "folder_a",
		};

		expect(matchesProjectFilePathSearch(fileNode, "测试")).toBe(true);
		expect(matchesProjectFilePathSearch(folderNode, "task_a")).toBe(false);
		expect(matchesProjectFilePathSearch(folderNode, "测试")).toBe(true);
		expect(getProjectFileFullDisplayPath(folderNode)).toBe("测试");
	});
});

describe("getProjectFolderStats", () => {
	it("aggregates descendant file size and prefers folder createdAt", () => {
		const stats = getProjectFolderStats({
			name: "测试",
			path: "uploads/测试/",
			type: "directory",
			nodeType: "folder",
			parentId: "",
			parentIds: [],
			children: [
				{
					name: "a.txt",
					path: "uploads/测试/a.txt",
					type: "file",
					nodeType: "file",
					parentId: "",
					parentIds: [],
					children: [],
					size: 100,
					mimeType: "text/plain",
					modTime: 0,
					createdAt: 2_000,
					publicId: "file_a",
					storageUri: "",
					initialFilePublicId: "file_a",
					versionNo: 1,
					versionLabel: "",
					versionCount: 1,
					resourceType: "user_upload",
				},
				{
					name: "nested",
					path: "uploads/测试/nested/",
					type: "directory",
					nodeType: "folder",
					parentId: "",
					parentIds: [],
					children: [
						{
							name: "b.txt",
							path: "uploads/测试/nested/b.txt",
							type: "file",
							nodeType: "file",
							parentId: "",
							parentIds: [],
							children: [],
							size: 50,
							mimeType: "text/plain",
							modTime: 0,
							createdAt: 3_000,
							publicId: "file_b",
							storageUri: "",
							initialFilePublicId: "file_b",
							versionNo: 1,
							versionLabel: "",
							versionCount: 1,
							resourceType: "user_upload",
						},
					],
					size: 0,
					mimeType: "",
					modTime: 0,
					createdAt: 0,
					publicId: "folder_nested",
					storageUri: "",
					initialFilePublicId: "folder_nested",
					versionNo: 1,
					versionLabel: "",
					versionCount: 1,
					resourceType: "user_upload",
				},
			],
			size: 0,
			mimeType: "",
			modTime: 0,
			createdAt: 1_000,
			publicId: "folder_root",
			storageUri: "",
			initialFilePublicId: "folder_root",
			versionNo: 1,
			versionLabel: "",
			versionCount: 1,
			resourceType: "user_upload",
		});

		expect(stats.size).toBe(150);
		expect(stats.createdAt).toBe(1_000);
	});
});
