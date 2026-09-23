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

export const PAYROLL_BASELINE_FIELDS = [
	["positionWage", "岗位工资"],
	["performanceWage", "绩效标准"],
	["seniorityWage", "工龄工资"],
	["titleWage", "职称工资"],
	["siteSubsidyDailyRate", "施工补贴日标准"],
	["phoneSubsidy", "话费补贴"],
	["highTempSubsidy", "高温补贴"],
	["transportSubsidy", "交通补贴"],
	["overtimeDailyRate", "特殊加班日标准"],
] as const;

export type PayrollStoredPerson = {
	id: number;
	employeeNo: string;
	name: string;
	projectName: string;
	companyName: string;
	position: string;
	employeeType: PayrollEmployeeType;
	positionWage: string;
	performanceWage: string;
	seniorityWage: string;
	titleWage: string;
	siteSubsidyDailyRate: string;
	phoneSubsidy: string;
	highTempSubsidy: string;
	transportSubsidy: string;
	overtimeDailyRate: string;
};

export type PayrollPeopleFilter = {
	name?: string;
	employeeNo?: string;
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
		hint: "导入基准时必填，可多份；MCP 解析后落库",
		requiredFor: "import",
	},
	{
		role: "attendance",
		title: "当月考勤",
		hint: "已有沉淀后可直接核算，支持 PDF，可多份",
		requiredFor: "compute",
	},
];

export type PayrollBaselineIssueKind = "duplicate_name" | "similar_name";

export type PayrollBaselineIssue = {
	id: string;
	kind: PayrollBaselineIssueKind;
	title: string;
	detail: string;
	employeeNos: string[];
};

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

export function payrollImportPrompt(files: PayrollSelectedFile[]): string {
	const names = (role: PayrollSourceKind) =>
		filesForRole(files, role)
			.map((file) => file.name)
			.join("、");
	return [
		"请解析人员底表与历史工资表：调用 MCP 解析 Excel 并落库工资基准，再把核对 JSON 交给模型总结。",
		"若存在重名、名称相近或其他需人工确认的问题，请逐条说明，等待用户确认后再进行考勤核算。",
		`人员底表：${names("roster")}`,
		`历史工资表：${names("historical_payroll")}`,
	].join("\n");
}

export function payrollStarterPrompt(files: PayrollSelectedFile[]): string {
	const names = (role: PayrollSourceKind) =>
		filesForRole(files, role)
			.map((file) => file.name)
			.join("、") || "未提交，使用独立服务已沉淀数据";
	return [
		"请开展考勤工资核算。人员基准已沉淀，请先对考勤 PDF 做 OCR 并返回 JSON，再交给 MCP 计算并生成产物。",
		`人员底表：${names("roster")}`,
		`历史工资表：${names("historical_payroll")}`,
		`当月考勤表：${names("attendance")}`,
	].join("\n");
}

export function createMockPayrollBaselineIssues(): PayrollBaselineIssue[] {
	return [
		{
			id: "issue-duplicate-zhangwei",
			kind: "duplicate_name",
			title: "重名",
			detail: "张伟 出现 2 次（E2026001 / E2026008），项目分别为瀚阅府与杨职院。请确认是否为不同人员。",
			employeeNos: ["E2026001", "E2026008"],
		},
		{
			id: "issue-similar-liuyang",
			kind: "similar_name",
			title: "名称相近",
			detail: "「刘洋」与历史表中的「刘旸」仅一字之差，请确认是否为同一人。",
			employeeNos: ["E2026010"],
		},
	];
}

export function filterPayrollPeople(
	people: PayrollStoredPerson[],
	filter: PayrollPeopleFilter,
): PayrollStoredPerson[] {
	const name = filter.name?.trim().toLowerCase() ?? "";
	const employeeNo = filter.employeeNo?.trim().toLowerCase() ?? "";
	const employeeType = filter.employeeType?.trim() ?? "";
	return people.filter((person) => {
		if (name && !person.name.toLowerCase().includes(name)) return false;
		if (employeeNo && !person.employeeNo.toLowerCase().includes(employeeNo)) return false;
		if (employeeType && person.employeeType !== employeeType) return false;
		return true;
	});
}

export function createMockPayrollPeople(): PayrollStoredPerson[] {
	return [
		{
			id: 101,
			employeeNo: "E2026001",
			name: "张伟",
			projectName: "瀚阅府",
			companyName: "工程六部",
			position: "施工员",
			employeeType: "易通外包",
			positionWage: "6500.00",
			performanceWage: "1200.00",
			seniorityWage: "200.00",
			titleWage: "300.00",
			siteSubsidyDailyRate: "30",
			phoneSubsidy: "100.00",
			highTempSubsidy: "300.00",
			transportSubsidy: "200.00",
			overtimeDailyRate: "598",
		},
		{
			id: 102,
			employeeNo: "E2026002",
			name: "李娜",
			projectName: "瀚阅府",
			companyName: "工程六部",
			position: "资料员",
			employeeType: "益通外包",
			positionWage: "5800.00",
			performanceWage: "800.00",
			seniorityWage: "100.00",
			titleWage: "0.00",
			siteSubsidyDailyRate: "20",
			phoneSubsidy: "80.00",
			highTempSubsidy: "0.00",
			transportSubsidy: "150.00",
			overtimeDailyRate: "",
		},
		{
			id: 103,
			employeeNo: "E2026003",
			name: "王强",
			projectName: "瀚阅府",
			companyName: "工程六部",
			position: "安全员",
			employeeType: "在册",
			positionWage: "7200.00",
			performanceWage: "1500.00",
			seniorityWage: "400.00",
			titleWage: "500.00",
			siteSubsidyDailyRate: "0",
			phoneSubsidy: "150.00",
			highTempSubsidy: "0.00",
			transportSubsidy: "0.00",
			overtimeDailyRate: "",
		},
		{
			id: 104,
			employeeNo: "E2026004",
			name: "赵敏",
			projectName: "杨职院",
			companyName: "工程六部",
			position: "施工员",
			employeeType: "博途外包",
			positionWage: "6500.00",
			performanceWage: "1000.00",
			seniorityWage: "150.00",
			titleWage: "200.00",
			siteSubsidyDailyRate: "15+50",
			phoneSubsidy: "100.00",
			highTempSubsidy: "300.00",
			transportSubsidy: "200.00",
			overtimeDailyRate: "598",
		},
		{
			id: 105,
			employeeNo: "E2026008",
			name: "张伟",
			projectName: "杨职院",
			companyName: "工程六部",
			position: "材料员",
			employeeType: "劳务派遣",
			positionWage: "5400.00",
			performanceWage: "600.00",
			seniorityWage: "50.00",
			titleWage: "0.00",
			siteSubsidyDailyRate: "25",
			phoneSubsidy: "60.00",
			highTempSubsidy: "0.00",
			transportSubsidy: "100.00",
			overtimeDailyRate: "",
		},
		{
			id: 106,
			employeeNo: "E2026009",
			name: "陈浩",
			projectName: "瀚阅府",
			companyName: "工程六部",
			position: "质量员",
			employeeType: "在册",
			positionWage: "6800.00",
			performanceWage: "1100.00",
			seniorityWage: "300.00",
			titleWage: "400.00",
			siteSubsidyDailyRate: "0",
			phoneSubsidy: "120.00",
			highTempSubsidy: "0.00",
			transportSubsidy: "0.00",
			overtimeDailyRate: "",
		},
		{
			id: 107,
			employeeNo: "E2026010",
			name: "刘洋",
			projectName: "杨职院",
			companyName: "工程六部",
			position: "施工员",
			employeeType: "易通外包",
			positionWage: "6300.00",
			performanceWage: "900.00",
			seniorityWage: "180.00",
			titleWage: "0.00",
			siteSubsidyDailyRate: "30",
			phoneSubsidy: "100.00",
			highTempSubsidy: "300.00",
			transportSubsidy: "200.00",
			overtimeDailyRate: "580",
		},
		{
			id: 108,
			employeeNo: "E2026011",
			name: "周芳",
			projectName: "瀚阅府",
			companyName: "工程六部",
			position: "资料员",
			employeeType: "益通外包",
			positionWage: "5600.00",
			performanceWage: "700.00",
			seniorityWage: "80.00",
			titleWage: "0.00",
			siteSubsidyDailyRate: "20",
			phoneSubsidy: "80.00",
			highTempSubsidy: "0.00",
			transportSubsidy: "150.00",
			overtimeDailyRate: "",
		},
	];
}

export function applyPayrollPersonPatch(
	person: PayrollStoredPerson,
	patch: Partial<PayrollStoredPerson>,
): PayrollStoredPerson {
	const next = { ...person };
	for (const key of Object.keys(patch) as Array<keyof PayrollStoredPerson>) {
		const value = patch[key];
		if (value !== undefined) {
			(next[key] as PayrollStoredPerson[typeof key]) = value;
		}
	}
	return next;
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
