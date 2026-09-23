"use client";

import { useChatStore, useLayoutStore } from "@leros/store";
import { Button } from "@leros/ui/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@leros/ui/components/ui/dialog";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
	type BidComparisonProjectFile,
	ProjectFilePicker,
} from "../input/BidComparisonConfigDialog";
import { filePreviewActions } from "./file-preview-store";
import { PayrollFileSlots } from "./PayrollFileSlots";
import { PayrollStoredPeopleTable } from "./PayrollStoredPeopleTable";
import {
	canStartPayrollAccounting,
	canStartPayrollBaselineImport,
	canStartPayrollTask,
	type PayrollSelectedFile,
	type PayrollSourceKind,
	payrollImportPrompt,
	payrollStarterPrompt,
} from "./payroll-accounting-mock";
import {
	appendPayrollLocalFiles,
	revokePayrollPreviewUrl,
	uploadPayrollAttachments,
} from "./payroll-file-upload";
import { parsePayrollBaselineMock } from "./payroll-service-client";

export function PayrollTaskPanel({
	open,
	onOpenChange,
	projectId,
	taskId,
	sessionId,
}: {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	projectId: string;
	taskId: string;
	sessionId: string;
}) {
	const { projects } = useLayoutStore((s) => s);
	const sendTaskRoomMessage = useChatStore((s) => s.sendTaskRoomMessage);
	const [files, setFiles] = useState<PayrollSelectedFile[]>([]);
	const [submitting, setSubmitting] = useState(false);
	const [filePickerRole, setFilePickerRole] = useState<PayrollSourceKind | null>(null);
	const filesRef = useRef(files);
	filesRef.current = files;

	const projectOptions = useMemo(
		() => projects.map((project) => ({ id: project.id, name: project.name, tasks: project.tasks })),
		[projects],
	);

	useEffect(() => {
		return () => {
			for (const file of filesRef.current) {
				revokePayrollPreviewUrl(file.previewUrl);
			}
		};
	}, []);

	const startTask = async () => {
		if (!canStartPayrollTask(files) || submitting) return;
		setSubmitting(true);
		try {
			if (canStartPayrollBaselineImport(files)) {
				await parsePayrollBaselineMock();
			}
			const computing = canStartPayrollAccounting(files);
			const attachments = await uploadPayrollAttachments(files, projectId);
			const result = await sendTaskRoomMessage(
				computing ? payrollStarterPrompt(files) : payrollImportPrompt(files),
				{
					projectId,
					taskId,
					sessionId,
					...(computing ? { scene: "salary_accounting" } : {}),
				},
				attachments,
			);
			if (!result) throw new Error("提交失败");
			setFiles((current) => {
				for (const file of current) revokePayrollPreviewUrl(file.previewUrl);
				return [];
			});
			onOpenChange(false);
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "提交失败");
		} finally {
			setSubmitting(false);
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="flex max-h-[calc(100dvh-2rem)] w-[min(96vw,88rem)] max-w-none flex-col overflow-hidden p-6">
				<DialogHeader>
					<DialogTitle>人员基准</DialogTitle>
					<DialogDescription>
						可编辑已落库基准，或在此上传资料后继续核算。解析问题会在对话里说明。
					</DialogDescription>
				</DialogHeader>
				<div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto py-3">
					<PayrollStoredPeopleTable />
					<PayrollFileSlots
						files={files}
						onAddFiles={(selected, role) =>
							setFiles((current) => appendPayrollLocalFiles(current, selected, role))
						}
						onRemove={(id) =>
							setFiles((current) => {
								const target = current.find((file) => file.id === id);
								revokePayrollPreviewUrl(target?.previewUrl);
								return current.filter((file) => file.id !== id);
							})
						}
						onPreview={(file) =>
							filePreviewActions.open({
								name: file.name,
								title: file.name,
								mimeType: file.mimeType,
								url: file.previewUrl,
								publicId: file.publicId,
								storageUri: file.storageUri,
								projectId: file.projectId,
								projectPath: file.projectPath,
							})
						}
						onPickProject={(role) => {
							if (!projects.length) {
								toast.info("当前账号暂无项目，请先创建项目");
								return;
							}
							setFilePickerRole(role);
						}}
					/>
				</div>
				<div className="flex justify-end">
					<Button
						type="button"
						disabled={submitting || !canStartPayrollTask(files)}
						onClick={() => void startTask()}
						className="bg-[var(--leros-primary)] text-white hover:bg-[var(--leros-primary)]/90"
					>
						{submitting ? "提交中..." : "开始核算"}
					</Button>
				</div>
			</DialogContent>
			{filePickerRole ? (
				<ProjectFilePicker
					open
					mode="compare"
					titleOverride={
						filePickerRole === "roster"
							? "选择人员底表"
							: filePickerRole === "historical_payroll"
								? "选择历史工资表"
								: "选择当月考勤表"
					}
					maxCountOverride={Number.POSITIVE_INFINITY}
					projects={projectOptions}
					initialSelected={files
						.filter((file) => file.role === filePickerRole && file.publicId && file.projectId)
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
					onConfirm={(selected) => {
						if (!filePickerRole) return;
						const role = filePickerRole;
						setFiles((current) => {
							const uploads = current.filter((file) => file.role === role && !file.publicId);
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
							return [...current.filter((file) => file.role !== role), ...uploads, ...projectFiles];
						});
						setFilePickerRole(null);
					}}
					onClose={() => setFilePickerRole(null)}
				/>
			) : null}
		</Dialog>
	);
}
