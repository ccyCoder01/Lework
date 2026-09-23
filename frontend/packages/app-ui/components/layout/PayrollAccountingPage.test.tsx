import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
	sendWorkbenchMessage: vi.fn(),
	fetchProjects: vi.fn(),
	fetchTasks: vi.fn(),
	uploadLoose: vi.fn(),
	openPreview: vi.fn(),
}));

vi.mock("./file-preview-store", () => ({
	filePreviewActions: {
		open: (...args: unknown[]) => mocks.openPreview(...args),
	},
}));

vi.mock("@leros/store", () => ({
	useLayoutStore: (selector: (state: Record<string, unknown>) => unknown) =>
		selector({
			projects: [],
			fetchProjects: mocks.fetchProjects,
			fetchTasks: mocks.fetchTasks,
			sendWorkbenchMessage: mocks.sendWorkbenchMessage,
		}),
	projectFileApi: {
		uploadLoose: (...args: unknown[]) => mocks.uploadLoose(...args),
		upload: (...args: unknown[]) => mocks.uploadLoose(...args),
	},
}));

vi.mock("../auth", () => ({
	useAuth: () => ({
		isAuthenticated: true,
		requireAuth: (fn: () => void) => fn(),
	}),
}));

vi.mock("./ProjectTaskPicker", () => ({
	ProjectTaskPickerField: () => <div>项目任务选择</div>,
}));

vi.mock("../input/BidComparisonConfigDialog", () => ({
	ProjectFilePicker: () => null,
}));

import { PayrollAccountingPage } from "./PayrollAccountingPage";
import { resetPayrollServiceStore } from "./payroll-service-client";
import * as payrollService from "./payroll-service-client";

describe("PayrollAccountingPage", () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
		resetPayrollServiceStore();
	});

	it("仅考勤必填，开始核算走现有任务", async () => {
		const user = userEvent.setup();
		mocks.uploadLoose.mockImplementation(async ({ file }: { file: File }) => ({
			data: { public_id: `id-${file.name}`, storage_uri: `s3://${file.name}` },
		}));
		mocks.sendWorkbenchMessage.mockResolvedValue({
			project_id: "p1",
			task_id: "t1",
			session_id: "s1",
		});
		const goToTaskDetail = vi.fn();

		render(
			<PayrollAccountingPage
				navigation={{
					currentPath: "/workbench/payroll",
					goToRoute: vi.fn(),
					goToPath: vi.fn(),
					goToProject: vi.fn(),
					goToProjectTasks: vi.fn(),
					goToTaskDetail,
					goToAutomationDetail: vi.fn(),
				}}
			/>,
		);

		expect(await screen.findByLabelText("E2026001-name")).toBeInTheDocument();
		expect(screen.getByLabelText("E2026001-positionWage")).toHaveValue("6500.00");
		expect(screen.getByLabelText("E2026001-titleWage")).toHaveValue("300.00");
		expect(screen.getByLabelText("E2026001-siteSubsidyDailyRate")).toHaveValue("30");
		expect(screen.getByText("职称工资")).toBeInTheDocument();
		expect(screen.getByText("施工补贴日标准")).toBeInTheDocument();
		expect(screen.queryByText("应发工资")).not.toBeInTheDocument();
		expect(screen.getByLabelText("E2026008-name")).toHaveValue("张伟");
		expect(screen.queryByText("应发工资")).not.toBeInTheDocument();
		expect(screen.queryByText("部门", { exact: true })).not.toBeInTheDocument();
		expect(screen.getByLabelText("E2026001-projectName")).toHaveValue("瀚阅府");
		expect(screen.getByText("人员底表", { exact: true })).toBeInTheDocument();
		expect(screen.getByText("历史工资表")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "开始核算" })).toBeDisabled();

		const hiddenInputs = document.querySelectorAll('input[type="file"]');
		const attendanceInput = hiddenInputs[2] as HTMLInputElement;
		const attendanceFile = new File(["attendance"], "当月考勤.pdf", { type: "application/pdf" });
		await user.upload(attendanceInput, attendanceFile);
		expect(screen.getByTitle("预览文件")).toBeInTheDocument();
		await user.click(screen.getByTitle("预览文件"));
		expect(mocks.openPreview).toHaveBeenCalledWith(
			expect.objectContaining({ name: "当月考勤.pdf", url: expect.any(String) }),
		);

		await user.click(screen.getByRole("button", { name: "开始核算" }));

		await vi.waitFor(() => {
			expect(mocks.sendWorkbenchMessage).toHaveBeenCalled();
		});
		const args = mocks.sendWorkbenchMessage.mock.calls[0];
		expect(args[7]).toBe("salary_accounting");
		expect(args[3]).toHaveLength(1);
		expect(args[3][0].attachmentRole).toBe("attendance");
		expect(String(args[0])).toContain("未提交，使用独立服务已沉淀数据");
		expect(goToTaskDetail).toHaveBeenCalledWith("p1", "t1", "s1");
	});

	it("上传底表和历史工资后开始核算走解析问答", async () => {
		const user = userEvent.setup();
		mocks.uploadLoose.mockImplementation(async ({ file }: { file: File }) => ({
			data: { public_id: `id-${file.name}`, storage_uri: `s3://${file.name}` },
		}));
		mocks.sendWorkbenchMessage.mockResolvedValue({
			project_id: "p1",
			task_id: "t1",
			session_id: "s-import",
		});
		const goToTaskDetail = vi.fn();

		render(
			<PayrollAccountingPage
				navigation={{
					currentPath: "/workbench/payroll",
					goToRoute: vi.fn(),
					goToPath: vi.fn(),
					goToProject: vi.fn(),
					goToProjectTasks: vi.fn(),
					goToTaskDetail,
					goToAutomationDetail: vi.fn(),
				}}
			/>,
		);

		const hiddenInputs = document.querySelectorAll('input[type="file"]');
		await user.upload(
			hiddenInputs[0] as HTMLInputElement,
			new File(["roster"], "人员底表.xlsx"),
		);
		await user.upload(
			hiddenInputs[1] as HTMLInputElement,
			new File(["history"], "历史工资.xlsx"),
		);
		await user.click(screen.getByRole("button", { name: "开始核算" }));

		await vi.waitFor(() => {
			expect(mocks.sendWorkbenchMessage).toHaveBeenCalled();
		});
		const args = mocks.sendWorkbenchMessage.mock.calls[0];
		expect(args[7]).toBeUndefined();
		expect(args[3]).toHaveLength(2);
		expect(args[3].map((item: { attachmentRole: string }) => item.attachmentRole).sort()).toEqual([
			"historical_payroll",
			"roster",
		]);
		expect(String(args[0])).toContain("落库工资基准");
		expect(goToTaskDetail).toHaveBeenCalledWith("p1", "t1", "s-import");
		expect(payrollService.isPayrollTaskSession("s-import")).toBe(true);
	});

	it("可按姓名筛选同名人员", async () => {
		const user = userEvent.setup();
		render(
			<PayrollAccountingPage
				navigation={{
					currentPath: "/workbench/payroll",
					goToRoute: vi.fn(),
					goToPath: vi.fn(),
					goToProject: vi.fn(),
					goToProjectTasks: vi.fn(),
					goToTaskDetail: vi.fn(),
					goToAutomationDetail: vi.fn(),
				}}
			/>,
		);

		expect(await screen.findByLabelText("E2026001-name")).toBeInTheDocument();
		expect(screen.getByLabelText("E2026002-name")).toBeInTheDocument();
		await user.type(screen.getByLabelText("筛选人员名称"), "张伟");
		expect(screen.getByLabelText("E2026001-name")).toBeInTheDocument();
		expect(screen.getByLabelText("E2026008-name")).toBeInTheDocument();
		expect(screen.queryByLabelText("E2026002-name")).not.toBeInTheDocument();
	});

	it("编辑工资基准会调用独立服务更新接口", async () => {
		const user = userEvent.setup();
		const updateSpy = vi.spyOn(payrollService, "updatePayrollPerson");
		render(
			<PayrollAccountingPage
				navigation={{
					currentPath: "/workbench/payroll",
					goToRoute: vi.fn(),
					goToPath: vi.fn(),
					goToProject: vi.fn(),
					goToProjectTasks: vi.fn(),
					goToTaskDetail: vi.fn(),
					goToAutomationDetail: vi.fn(),
				}}
			/>,
		);

		const wage = await screen.findByLabelText("E2026001-positionWage");
		await user.clear(wage);
		await user.type(wage, "7000.00");
		await user.tab();

		await vi.waitFor(() => {
			expect(updateSpy).toHaveBeenCalledWith(101, { positionWage: "7000.00" });
		});
	});
});
