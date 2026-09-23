import {
	applyPayrollPersonPatch,
	createMockPayrollBaselineIssues,
	createMockPayrollPeople,
	type PayrollBaselineIssue,
	type PayrollStoredPerson,
} from "./payroll-accounting-mock";

const PAYROLL_SESSION_STORAGE_KEY = "leros-payroll-task-sessions";

let peopleStore = createMockPayrollPeople();
let issuesStore: PayrollBaselineIssue[] = [];

function clonePerson(person: PayrollStoredPerson): PayrollStoredPerson {
	return { ...person };
}

function readPayrollSessions(): Set<string> {
	if (typeof sessionStorage === "undefined") return new Set();
	try {
		const raw = sessionStorage.getItem(PAYROLL_SESSION_STORAGE_KEY);
		const parsed = raw ? (JSON.parse(raw) as unknown) : [];
		return new Set(Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : []);
	} catch {
		return new Set();
	}
}

function writePayrollSessions(sessions: Set<string>) {
	if (typeof sessionStorage === "undefined") return;
	sessionStorage.setItem(PAYROLL_SESSION_STORAGE_KEY, JSON.stringify([...sessions]));
}

export function resetPayrollServiceStore() {
	peopleStore = createMockPayrollPeople();
	issuesStore = [];
	writePayrollSessions(new Set());
}

export function seedEmptyPayrollStore() {
	peopleStore = [];
	issuesStore = [];
}

/** 列出独立服务已沉淀的人员底表 + 工资基准。当前为 mock，后续替换为 payroll HTTP。 */
export async function listPayrollPeople(): Promise<PayrollStoredPerson[]> {
	return peopleStore.map(clonePerson);
}

export async function hasPersistedPayrollBaseline(): Promise<boolean> {
	return peopleStore.length > 0;
}

/** 更新一条人员底表/工资基准。当前为 mock，后续对应独立服务更新接口。 */
export async function updatePayrollPerson(
	id: number,
	patch: Partial<Omit<PayrollStoredPerson, "id">>,
): Promise<PayrollStoredPerson> {
	const index = peopleStore.findIndex((person) => person.id === id);
	if (index < 0) {
		throw new Error(`人员 ${id} 不存在`);
	}
	peopleStore[index] = applyPayrollPersonPatch(peopleStore[index], patch);
	return clonePerson(peopleStore[index]);
}

/** 模拟 MCP 解析 Excel、落库，并返回需模型总结的核对问题。 */
export async function parsePayrollBaselineMock(): Promise<{
	people: PayrollStoredPerson[];
	issues: PayrollBaselineIssue[];
}> {
	peopleStore = createMockPayrollPeople();
	issuesStore = createMockPayrollBaselineIssues();
	return {
		people: peopleStore.map(clonePerson),
		issues: issuesStore.map((issue) => ({ ...issue })),
	};
}

export async function listPayrollBaselineIssues(): Promise<PayrollBaselineIssue[]> {
	return issuesStore.map((issue) => ({ ...issue }));
}

export function markPayrollTaskSession(sessionId: string) {
	const sessions = readPayrollSessions();
	sessions.add(sessionId);
	writePayrollSessions(sessions);
}

export function isPayrollTaskSession(sessionId: string): boolean {
	return readPayrollSessions().has(sessionId);
}
