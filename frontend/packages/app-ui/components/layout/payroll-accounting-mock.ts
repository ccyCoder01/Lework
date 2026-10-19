export const WORKBENCH_PAYROLL_PATH = "/workbench/payroll";

export type PayrollSourceKind = "roster" | "historical_payroll" | "attendance";

export type PayrollSelectedFile = {
	id: string;
	file?: File;
	name: string;
	publicId?: string;
	projectId?: string;
	storageUri?: string;
	projectPath?: string;
	mimeType?: string;
	size: number;
	role: PayrollSourceKind;
	previewUrl?: string;
};

export type PayrollEmployeeType = "在册" | "易通外包" | "益通外包" | "博途外包" | "劳务派遣";

export const PAYROLL_EMPLOYEE_TYPES: PayrollEmployeeType[] = [
	"在册",
	"易通外包",
	"益通外包",
	"博途外包",
	"劳务派遣",
];

export const PAYROLL_ROSTER_TEXT_FIELDS = [["position", "岗位"]] as const;

export type PayrollStoredPerson = {
	id: number;
	name: string;
	projectName: string;
	companyName: string;
	position: string;
	employeeType: PayrollEmployeeType;
	gender: "未知" | "男" | "女";
};

export type PayrollPeopleFilter = {
	name?: string;
	employeeType?: string;
};

export const PAYROLL_SOURCE_SLOTS: ReadonlyArray<{
	role: PayrollSourceKind;
	title: string;
	hint: string;
	requiredFor: "import" | "compute";
}> = [
	{
		role: "roster",
		title: "人员底表",
		hint: "导入基准时必填，可多份",
		requiredFor: "import",
	},
	{
		role: "historical_payroll",
		title: "历史工资表",
		hint: "导入基准时必填，可多份；同步导入 Payroll 服务",
		requiredFor: "import",
	},
	{
		role: "attendance",
		title: "当月考勤",
		hint: "已有沉淀后可直接核算，支持 PDF，可多份",
		requiredFor: "compute",
	},
];

export function filesForRole(
	files: PayrollSelectedFile[],
	role: PayrollSourceKind,
): PayrollSelectedFile[] {
	return files.filter((file) => file.role === role);
}

export function canStartPayrollBaselineImport(files: PayrollSelectedFile[]): boolean {
	return (
		filesForRole(files, "roster").length >= 1 &&
		filesForRole(files, "historical_payroll").length >= 1
	);
}

export function canStartPayrollAccounting(files: PayrollSelectedFile[]): boolean {
	return filesForRole(files, "attendance").length >= 1;
}

export function canStartPayrollTask(files: PayrollSelectedFile[]): boolean {
	return canStartPayrollAccounting(files) || canStartPayrollBaselineImport(files);
}

export function payrollStarterPrompt(_files: PayrollSelectedFile[]): string {
	return "请按照 attendance-payroll Skill 处理本次当月考勤核算。先完整识别并展示考勤，等待我确认考勤事实后再匹配人员；人员映射确认并预检查后再次停下，只有我后续明确确认开始核算才计算工资。";
}

export function filterPayrollPeople(
	people: PayrollStoredPerson[],
	filter: PayrollPeopleFilter,
): PayrollStoredPerson[] {
	const name = filter.name?.trim().toLowerCase() ?? "";
	const employeeType = filter.employeeType?.trim() ?? "";
	return people.filter((person) => {
		if (name && !person.name.toLowerCase().includes(name)) return false;
		if (employeeType && person.employeeType !== employeeType) return false;
		return true;
	});
}

export function createMockPayrollFiles(): PayrollSelectedFile[] {
	const roster = new File(["mock-roster"], "工程六部人员底表.xlsx");
	const historyMay = new File(["mock-history-may"], "工程六部2026年5月工资.xlsx");
	const historyApr = new File(["mock-history-apr"], "工程六部2026年4月工资.xlsx");
	const attendance = new File(["mock-attendance"], "工程六部2026年6月考勤.pdf");
	return [
		{
			id: "mock-roster-1",
			name: roster.name,
			mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			size: 12_288,
			role: "roster",
			file: roster,
			previewUrl: URL.createObjectURL(roster),
		},
		{
			id: "mock-history-1",
			name: historyMay.name,
			mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			size: 24_576,
			role: "historical_payroll",
			file: historyMay,
			previewUrl: URL.createObjectURL(historyMay),
		},
		{
			id: "mock-history-2",
			name: historyApr.name,
			mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			size: 20_480,
			role: "historical_payroll",
			file: historyApr,
			previewUrl: URL.createObjectURL(historyApr),
		},
		{
			id: "mock-attendance-1",
			name: attendance.name,
			mimeType: "application/pdf",
			size: 98_304,
			role: "attendance",
			file: attendance,
			previewUrl: URL.createObjectURL(attendance),
		},
	];
}
