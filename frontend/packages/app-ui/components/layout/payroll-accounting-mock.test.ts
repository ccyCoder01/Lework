import { describe, expect, it } from "vitest";
import {
	applyPayrollPersonPatch,
	canStartPayrollAccounting,
	canStartPayrollBaselineImport,
	canStartPayrollTask,
	createMockPayrollBaselineIssues,
	createMockPayrollFiles,
	createMockPayrollPeople,
	filesForRole,
	filterPayrollPeople,
	PAYROLL_BASELINE_FIELDS,
	payrollImportPrompt,
	payrollStarterPrompt,
} from "./payroll-accounting-mock";

describe("payroll-accounting-mock", () => {
	it("只要有当月考勤即可开始，底表和历史工资可选", () => {
		const files = createMockPayrollFiles();
		expect(filesForRole(files, "historical_payroll")).toHaveLength(2);
		expect(canStartPayrollAccounting(files)).toBe(true);
		expect(canStartPayrollAccounting(files.filter((file) => file.role === "attendance"))).toBe(true);
		expect(payrollStarterPrompt(files.filter((file) => file.role === "attendance"))).toContain(
			"未提交，使用独立服务已沉淀数据",
		);
	});

	it("有考勤则核算，只有底表和历史则可导入", () => {
		const files = createMockPayrollFiles();
		expect(canStartPayrollBaselineImport(files)).toBe(true);
		expect(canStartPayrollTask(files)).toBe(true);
		expect(canStartPayrollTask(files.filter((file) => file.role !== "attendance"))).toBe(true);
		expect(canStartPayrollAccounting(files.filter((file) => file.role !== "attendance"))).toBe(false);
		expect(payrollImportPrompt(files)).toContain("重名");
		expect(createMockPayrollBaselineIssues()[0]?.kind).toBe("duplicate_name");
	});

	it("缺少考勤时不能开始核算", () => {
		const files = createMockPayrollFiles().filter((file) => file.role !== "attendance");
		expect(canStartPayrollAccounting(files)).toBe(false);
	});

	it("人员底表与工资基准可合并为一行并打补丁", () => {
		const [person] = createMockPayrollPeople();
		expect(person.name).toBe("张伟");
		expect(person.employeeNo).toBe("E2026001");
		expect(person.positionWage).toBe("6500.00");
		expect(person.titleWage).toBe("300.00");
		expect(person.seniorityWage).toBe("200.00");
		expect(person.phoneSubsidy).toBe("100.00");
		expect(person.siteSubsidyDailyRate).toBe("30");
		expect(person).not.toHaveProperty("grossPay");
		expect(person).not.toHaveProperty("siteSubsidy");
		expect(PAYROLL_BASELINE_FIELDS.map(([, label]) => label)).toEqual([
			"岗位工资",
			"绩效标准",
			"工龄工资",
			"职称工资",
			"施工补贴日标准",
			"话费补贴",
			"高温补贴",
			"交通补贴",
			"特殊加班日标准",
		]);
		expect(applyPayrollPersonPatch(person, { positionWage: "7000.00" }).positionWage).toBe("7000.00");
	});

	it("可按姓名或编号筛选同名人员", () => {
		const people = createMockPayrollPeople();
		expect(filterPayrollPeople(people, { name: "张伟" })).toHaveLength(2);
		expect(filterPayrollPeople(people, { employeeNo: "E2026008" }).map((row) => row.name)).toEqual([
			"张伟",
		]);
		expect(filterPayrollPeople(people, { employeeType: "在册" })).toHaveLength(2);
	});
});
