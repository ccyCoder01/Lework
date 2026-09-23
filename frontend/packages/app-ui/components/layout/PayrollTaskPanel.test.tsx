import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
	sendTaskRoomMessage: vi.fn(),
	uploadLoose: vi.fn(),
}));

vi.mock("@leros/store", () => ({
	useLayoutStore: (selector: (state: Record<string, unknown>) => unknown) =>
		selector({
			projects: [],
		}),
	useChatStore: (selector: (state: Record<string, unknown>) => unknown) =>
		selector({
			sendTaskRoomMessage: mocks.sendTaskRoomMessage,
		}),
	projectFileApi: {
		uploadLoose: (...args: unknown[]) => mocks.uploadLoose(...args),
		upload: (...args: unknown[]) => mocks.uploadLoose(...args),
	},
}));

vi.mock("../input/BidComparisonConfigDialog", () => ({
	ProjectFilePicker: () => null,
}));

vi.mock("./file-preview-store", () => ({
	filePreviewActions: { open: vi.fn() },
}));

import { PayrollTaskPanel } from "./PayrollTaskPanel";
import { resetPayrollServiceStore } from "./payroll-service-client";

describe("PayrollTaskPanel", () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
		resetPayrollServiceStore();
	});

	it("窗口内可编辑基准并直接上传考勤核算", async () => {
		const user = userEvent.setup();
		mocks.uploadLoose.mockImplementation(async ({ file }: { file: File }) => ({
			data: { public_id: `id-${file.name}`, storage_uri: `s3://${file.name}` },
		}));
		mocks.sendTaskRoomMessage.mockResolvedValue({
			project_id: "p1",
			task_id: "t1",
			session_id: "s1",
		});

		render(
			<PayrollTaskPanel
				open
				onOpenChange={vi.fn()}
				projectId="p1"
				taskId="t1"
				sessionId="s1"
			/>,
		);

		expect(await screen.findByText("人员基准")).toBeInTheDocument();
		expect(screen.queryByText("确认人员基准无误")).not.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "开始核算" })).toBeDisabled();

		const attendanceInput = document.querySelectorAll(
			'input[type="file"]',
		)[2] as HTMLInputElement;
		await user.upload(attendanceInput, new File(["att"], "当月考勤.pdf", { type: "application/pdf" }));
		await user.click(screen.getByRole("button", { name: "开始核算" }));

		await vi.waitFor(() => {
			expect(mocks.sendTaskRoomMessage).toHaveBeenCalled();
		});
		expect(mocks.sendTaskRoomMessage.mock.calls[0][1]).toEqual(
			expect.objectContaining({ scene: "salary_accounting", sessionId: "s1" }),
		);
	});
});
