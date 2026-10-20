"use client";

import type { ComponentProps } from "react";
import { toast } from "sonner";
import {
	type BidComparisonProjectFile,
	ProjectFilePicker,
} from "../input/BidComparisonConfigDialog";
import type { PayrollSelectedFile, PayrollSourceKind } from "./payroll-accounting-mock";
import { importPayrollFileByRole } from "./payroll-service-client";

type ProjectOptions = ComponentProps<typeof ProjectFilePicker>["projects"];

export function PayrollProjectFilePicker({
	role,
	projects,
	files,
	onClose,
	onAttendanceSelected,
	onImported,
}: {
	role: PayrollSourceKind | null;
	projects: ProjectOptions;
	files: PayrollSelectedFile[];
	onClose: () => void;
	onAttendanceSelected: (files: PayrollSelectedFile[]) => void;
	onImported: (role: PayrollSourceKind) => void;
}) {
	if (!role) return null;

	const selectFiles = async (selected: BidComparisonProjectFile[]) => {
		const projectFiles = selected.map((file) => ({
			id: `payroll-project-${file.publicId}`,
			name: file.name,
			publicId: file.publicId,
			projectId: file.projectId,
			storageUri: file.storageUri,
			mimeType: file.mimeType,
			size: file.size ?? 0,
			role,
			projectPath: file.projectPath,
		}));
		onClose();
		if (role === "attendance") {
			onAttendanceSelected(projectFiles);
			return;
		}
		for (const file of projectFiles) {
			try {
				const result = await importPayrollFileByRole(role, file);
				toast.success(
					`${file.name}：导入 ${result.success_count}/${result.total_count} 条，失败 ${result.failed_count} 条${result.message ? `；${result.message}` : ""}`,
				);
			} catch (error) {
				toast.error(error instanceof Error ? error.message : "项目文件导入失败");
			}
		}
		onImported(role);
	};

	return (
		<ProjectFilePicker
			open
			mode="compare"
			titleOverride={
				role === "roster"
					? "选择人员底表"
					: role === "historical_payroll"
						? "选择历史工资表"
						: "选择当月考勤表"
			}
			maxCountOverride={Number.POSITIVE_INFINITY}
			projects={projects}
			initialSelected={files
				.filter((file) => file.role === role && file.publicId && file.projectId)
				.map(
					(file) =>
						({
							name: file.name,
							publicId: file.publicId,
							projectId: file.projectId,
							storageUri: file.storageUri,
							mimeType: file.mimeType,
							size: file.size,
						}) satisfies BidComparisonProjectFile,
				)}
			onConfirm={(selected) => void selectFiles(selected)}
			onClose={onClose}
		/>
	);
}
