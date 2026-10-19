import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PayrollStoredPeopleTable } from "./PayrollStoredPeopleTable";
import * as payrollService from "./payroll-service-client";

const person = {
	id: 31,
	name: "杨福生",
	projectName: "项目A",
	companyName: "部门",
	position: "电工",
	employeeType: "在册" as const,
	gender: "男" as const,
};

describe("PayrollStoredPeopleTable", () => {
	afterEach(() => {
		cleanup();
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
	});

	it("confirms delete and returns to the previous page after deleting its last row", async () => {
		const list = vi
			.spyOn(payrollService, "listPayrollPeople")
			.mockImplementation(async ({ offset = 0 } = {}) => ({
				total: 11,
				initialized: true,
				items: offset ? [person] : [person],
			}));
		const remove = vi.spyOn(payrollService, "deletePayrollPerson").mockResolvedValue();
		vi.stubGlobal(
			"confirm",
			vi.fn(() => true),
		);
		const user = userEvent.setup();
		render(<PayrollStoredPeopleTable />);
		await user.click(await screen.findByRole("button", { name: "2" }));
		await vi.waitFor(() =>
			expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 10 })),
		);
		await user.click(screen.getByRole("button", { name: "删除" }));
		await vi.waitFor(() => expect(remove).toHaveBeenCalledWith(31));
		await vi.waitFor(() =>
			expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0 })),
		);
	});

	it("imports an xlsx directly and shows a safe load error without mock rows", async () => {
		const failure = vi
			.spyOn(payrollService, "listPayrollPeople")
			.mockRejectedValue(new Error("Go Payroll internal error"));
		const importRoster = vi.spyOn(payrollService, "importPayrollRoster").mockResolvedValue({
			task_id: 1,
			status: "success",
			total_count: 1,
			success_count: 1,
			failed_count: 0,
		});
		const user = userEvent.setup();
		render(<PayrollStoredPeopleTable />);
		expect(await screen.findByRole("alert")).toHaveTextContent(
			"暂时无法读取人员底表，请稍后重试。",
		);
		await user.upload(screen.getByLabelText("上传人员底表文件"), new File(["xlsx"], "roster.xlsx"));
		await vi.waitFor(() => expect(importRoster).toHaveBeenCalledTimes(1));
		expect(failure).toHaveBeenCalled();
		expect(screen.queryByText("杨福生")).not.toBeInTheDocument();
	});
});
