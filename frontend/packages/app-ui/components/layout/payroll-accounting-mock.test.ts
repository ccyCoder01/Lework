import { describe, expect, it } from "vitest";
import {
	canStartPayrollAccounting,
	canStartPayrollBaselineImport,
	canStartPayrollTask,
	createMockPayrollFiles,
	filesForRole,
	payrollStarterPrompt,
} from "./payroll-accounting-mock";

describe("payroll-accounting-mock", () => {
	it("demo files remain fixtures and baseline files do not start attendance accounting", () => {
		const files = createMockPayrollFiles();
		expect(filesForRole(files, "historical_payroll")).toHaveLength(2);
		expect(canStartPayrollBaselineImport(files)).toBe(true);
		expect(canStartPayrollTask(files.filter((file) => file.role !== "attendance"))).toBe(true);
		expect(canStartPayrollAccounting(files.filter((file) => file.role !== "attendance"))).toBe(
			false,
		);
	});

	it("attendance starts the existing workbench accounting flow", () => {
		const files = createMockPayrollFiles().filter((file) => file.role === "attendance");
		expect(canStartPayrollAccounting(files)).toBe(true);
		expect(payrollStarterPrompt(files)).toContain("attendance-payroll Skill");
		expect(payrollStarterPrompt(files)).toContain("等待我确认考勤事实后再匹配人员");
		expect(payrollStarterPrompt(files)).toContain("只有我后续明确确认开始核算才计算工资");
	});
});
