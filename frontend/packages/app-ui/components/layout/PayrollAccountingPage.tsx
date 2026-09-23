"use client";

import { useLayoutStore } from "@leros/store";
import { Button } from "@leros/ui/components/ui/button";
import { ArrowLeft, Calculator } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "../auth";
import {
	type BidComparisonProjectFile,
	ProjectFilePicker,
} from "../input/BidComparisonConfigDialog";
import { filePreviewActions } from "./file-preview-store";
import type { AppNavigation } from "./LeftRail";
import { PayrollFileSlots } from "./PayrollFileSlots";
import { PayrollStoredPeopleTable } from "./PayrollStoredPeopleTable";
import { ProjectTaskPickerField } from "./ProjectTaskPicker";
import {
	canStartPayrollAccounting,
	canStartPayrollBaselineImport,
	canStartPayrollTask,
	payrollImportPrompt,
	payrollStarterPrompt,
	WORKBENCH_PAYROLL_PATH,
	type PayrollSelectedFile,
	type PayrollSourceKind,
} from "./payroll-accounting-mock";
import {
	appendPayrollLocalFiles,
	revokePayrollPreviewUrl,
	uploadPayrollAttachments,
} from "./payroll-file-upload";
import {
	hasPersistedPayrollBaseline,
	markPayrollTaskSession,
	parsePayrollBaselineMock,
} from "./payroll-service-client";

export function PayrollAccountingPage({ navigation }: { navigation?: AppNavigation }) {
	const { projects, fetchProjects, fetchTasks, sendWorkbenchMessage } = useLayoutStore((s) => s);
	const { isAuthenticated } = useAuth();
	const [projectId, setProjectId] = useState("");
	const [taskId, setTaskId] = useState("");
	const [files, setFiles] = useState<PayrollSelectedFile[]>([]);
	const [submitting, setSubmitting] = useState(false);
	const [hasBaseline, setHasBaseline] = useState(false);
	const [filePickerRole, setFilePickerRole] = useState<PayrollSourceKind | null>(null);
	const filesRef = useRef(files);
	filesRef.current = files;

	useEffect(() => {
		return () => {
			for (const file of filesRef.current) {
				revokePayrollPreviewUrl(file.previewUrl);
			}
		};
	}, []);

	const projectOptions = useMemo(
		() => projects.map((project) => ({ id: project.id, name: project.name, tasks: project.tasks })),
		[projects],
	);

	useEffect(() => {
		if (!isAuthenticated) return;
		void fetchProjects();
	}, [fetchProjects, isAuthenticated]);

	useEffect(() => {
		void hasPersistedPayrollBaseline().then(setHasBaseline);
	}, []);

	const goBack = () => {
		if (navigation?.goToPath) {
			navigation.goToPath("/workbench");
			return;
		}
		navigation?.goToRoute("workbench");
	};

	const openProjectFilePicker = (role: PayrollSourceKind) => {
		if (!projects.length) {
			toast.info("当前账号暂无项目，请先创建项目");
			return;
		}
		setFilePickerRole(role);
	};

	const selectProjectFiles = (selected: BidComparisonProjectFile[]) => {
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
	};

	const openPreview = (file: PayrollSelectedFile) => {
		filePreviewActions.open({
			name: file.name,
			title: file.name,
			mimeType: file.mimeType,
			url: file.previewUrl,
			publicId: file.publicId,
			storageUri: file.storageUri,
			projectId: file.projectId,
			projectPath: file.projectPath,
		});
	};

	const removeFile = (id: string) => {
		setFiles((current) => {
			const target = current.find((file) => file.id === id);
			revokePayrollPreviewUrl(target?.previewUrl);
			return current.filter((file) => file.id !== id);
		});
	};

	const goToCreatedTask = (result: {
		project_id?: string;
		task_id?: string;
		session_id?: string;
	}) => {
		if (!result.project_id || !result.task_id || !result.session_id) {
			throw new Error("创建工资核算任务失败");
		}
		markPayrollTaskSession(result.session_id);
		navigation?.goToTaskDetail(result.project_id, result.task_id, result.session_id);
	};

	const startAnalysis = async () => {
		if (!canStartPayrollTask(files) || submitting) return;
		setSubmitting(true);
		try {
			if (canStartPayrollBaselineImport(files)) {
				await parsePayrollBaselineMock();
				setHasBaseline(true);
			}
			const computing = canStartPayrollAccounting(files);
			const attachments = await uploadPayrollAttachments(files, projectId);
			const result = await sendWorkbenchMessage(
				computing ? payrollStarterPrompt(files) : payrollImportPrompt(files),
				projectId || undefined,
				"default",
				attachments,
				undefined,
				undefined,
				undefined,
				computing ? "salary_accounting" : undefined,
				undefined,
				taskId || null,
			);
			goToCreatedTask(result ?? {});
		} catch (error) {
			console.error("PayrollAccountingPage start analysis error:", error);
			toast.error(error instanceof Error ? error.message : "启动工资核算失败");
		} finally {
			setSubmitting(false);
		}
	};

	return (
		<div
			data-slot="payroll-accounting-page"
			data-path={WORKBENCH_PAYROLL_PATH}
			className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--leros-app-bg)]"
		>
			<header className="shrink-0 border-b border-[var(--leros-control-border)] px-4 py-4 sm:px-6 sm:py-5">
				<Button
					type="button"
					variant="ghost"
					size="sm"
					className="-ml-2 mb-2 text-[var(--leros-text-muted)]"
					onClick={goBack}
				>
					<ArrowLeft className="size-4" />
					返回工作台
				</Button>
				<div className="flex items-center justify-between gap-3">
					<div className="flex min-w-0 items-center gap-3">
						<div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
							<Calculator className="size-5" />
						</div>
						<h1 className="truncate text-xl font-semibold text-[var(--leros-text-strong)]">
							考勤工资核算
						</h1>
					</div>
					<Button
						type="button"
						disabled={!isAuthenticated || submitting || !canStartPayrollTask(files)}
						onClick={() => void startAnalysis()}
						className="shrink-0 bg-[var(--leros-primary)] text-white hover:bg-[var(--leros-primary)]/90"
					>
						{submitting ? "启动中..." : "开始核算"}
					</Button>
				</div>
			</header>

			<main className="flex min-h-0 min-w-0 flex-1 flex-col gap-5 overflow-x-hidden overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
				<ProjectTaskPickerField
					projectId={projectId}
					taskId={taskId}
					allowNewProject
					allowSelectTask
					onLoadProjectTasks={fetchTasks}
					onSelect={(nextProjectId, nextTaskId) => {
						setProjectId(nextProjectId);
						setTaskId(nextTaskId);
						if (nextProjectId) fetchTasks(nextProjectId);
					}}
				/>

				{hasBaseline ? (
					<PayrollStoredPeopleTable />
				) : (
					<section className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-400">
						尚未沉淀人员基准。可上传人员底表和历史工资表后开始核算，解析结果会在对话中说明。
					</section>
				)}

				<PayrollFileSlots
					files={files}
					onAddFiles={(selected, role) =>
						setFiles((current) => appendPayrollLocalFiles(current, selected, role))
					}
					onRemove={removeFile}
					onPreview={openPreview}
					onPickProject={openProjectFilePicker}
				/>
			</main>

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
					onConfirm={selectProjectFiles}
					onClose={() => setFilePickerRole(null)}
				/>
			) : null}
		</div>
	);
}
