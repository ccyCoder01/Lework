import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PayrollHistoricalSalaryTable } from "./PayrollHistoricalSalaryTable";
import * as payrollService from "./payroll-service-client";

const sampleSalary = {
	id: 11,
	payroll_month: "2026-06",
	roster_id: 7,
	name: "杨福生",
	position: "电工",
	work_days: "26",
	gross_amount: "12345.60",
};

describe("PayrollHistoricalSalaryTable", () => {
	afterEach(() => {
		cleanup();
		vi.restoreAllMocks();
	});

	it("uses server month/name filters and independent numeric pagination", async () => {
		const list = vi.spyOn(payrollService, "listPayrollSalary").mockResolvedValue({
			total: 259,
			initialized: true,
			items: [
				{
					id: 1,
					payroll_month: "2026-06",
					roster_id: 7,
					name: "杨福生",
					position: "电工",
					work_days: "26",
					gross_amount: "12345.60",
				},
			],
		});
		const user = userEvent.setup();
		render(<PayrollHistoricalSalaryTable />);
		expect(await screen.findByText("杨福生")).toBeInTheDocument();
		expect(screen.getByText("¥12,345.60")).toBeInTheDocument();
		expect(list).toHaveBeenCalledWith(expect.objectContaining({ offset: 0, limit: 10 }));
		await user.click(screen.getByRole("button", { name: "2" }));
		await vi.waitFor(() =>
			expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 10, limit: 10 })),
		);
		await user.selectOptions(screen.getByLabelText("每页数量"), "20");
		await vi.waitFor(() =>
			expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0, limit: 20 })),
		);
		await user.selectOptions(screen.getByLabelText("每页数量"), "50");
		await vi.waitFor(() =>
			expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0, limit: 50 })),
		);
		await user.type(screen.getByLabelText("筛选工资月份"), "2026-05");
		await vi.waitFor(() =>
			expect(list).toHaveBeenLastCalledWith(
				expect.objectContaining({ payrollMonth: "2026-05", offset: 0 }),
			),
		);
		await user.type(screen.getByLabelText("筛选历史工资姓名"), "杨");
		await vi.waitFor(() =>
			expect(list).toHaveBeenLastCalledWith(
				expect.objectContaining({ name: "杨", payrollMonth: "2026-05", offset: 0 }),
			),
		);
	});

	it("updates salary using the selected real roster ID", async () => {
		vi.spyOn(payrollService, "listPayrollSalary").mockResolvedValue({
			total: 1,
			initialized: true,
			items: [sampleSalary],
		});
		vi.spyOn(payrollService, "listPayrollPeople").mockResolvedValue({
			total: 1,
			initialized: true,
			items: [
				{
					id: 99,
					name: "杨福生新",
					projectName: "项目B",
					companyName: "部门",
					position: "焊工",
					employeeType: "在册",
					gender: "男",
				},
			],
		});
		const update = vi
			.spyOn(payrollService, "updatePayrollSalary")
			.mockResolvedValue({ ...sampleSalary, roster_id: 99, name: "杨福生新", position: "焊工" });
		const user = userEvent.setup();
		render(<PayrollHistoricalSalaryTable />);
		await user.click(await screen.findByRole("button", { name: "编辑" }));
		await screen.findByRole("option", { name: /杨福生新/ });
		await user.selectOptions(screen.getByLabelText("人员"), "99");
		await user.click(screen.getByRole("button", { name: "保存" }));
		await vi.waitFor(() =>
			expect(update).toHaveBeenCalledWith(
				expect.objectContaining({
					id: 11,
					payroll_month: "2026-06",
					roster_id: 99,
					name: "杨福生新",
					position: "焊工",
					work_days: "26",
					gross_amount: "12345.60",
				}),
			),
		);
	});

	it("confirms delete and returns to the previous page after deleting its last row", async () => {
		const list = vi
			.spyOn(payrollService, "listPayrollSalary")
			.mockImplementation(async ({ offset = 0 } = {}) => ({
				total: 11,
				initialized: true,
				items: offset ? [sampleSalary] : [sampleSalary],
			}));
		const remove = vi.spyOn(payrollService, "deletePayrollSalary").mockResolvedValue();
		vi.stubGlobal(
			"confirm",
			vi.fn(() => true),
		);
		const user = userEvent.setup();
		render(<PayrollHistoricalSalaryTable />);
		await user.click(await screen.findByRole("button", { name: "2" }));
		await vi.waitFor(() =>
			expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 10 })),
		);
		await user.click(screen.getByRole("button", { name: "删除" }));
		await vi.waitFor(() => expect(remove).toHaveBeenCalledWith(11));
		await vi.waitFor(() =>
			expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0 })),
		);
	});
});
