"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
	filterPayrollPeople,
	PAYROLL_BASELINE_FIELDS,
	PAYROLL_EMPLOYEE_TYPES,
	PAYROLL_ROSTER_TEXT_FIELDS,
	type PayrollStoredPerson,
} from "./payroll-accounting-mock";
import { listPayrollPeople, updatePayrollPerson } from "./payroll-service-client";

const CELL_PX = "px-2.5";
const STICKY_CELL = `sticky z-20 ${CELL_PX} min-w-0 bg-white`;
const HEADER_CELL = `sticky top-0 z-10 ${CELL_PX} min-w-0 bg-white py-2.5 font-medium whitespace-nowrap`;

function tableColCount() {
	return 4 + PAYROLL_ROSTER_TEXT_FIELDS.length + PAYROLL_BASELINE_FIELDS.length;
}

function stickyLeftStyle(columnIndex: number): { left: string } {
	return { left: `${(100 / tableColCount()) * columnIndex}%` };
}

export function PayrollStoredPeopleTable() {
	const [rows, setRows] = useState<PayrollStoredPerson[]>([]);
	const [loading, setLoading] = useState(true);
	const [savingId, setSavingId] = useState<number | null>(null);
	const [nameQuery, setNameQuery] = useState("");
	const [employeeNoQuery, setEmployeeNoQuery] = useState("");
	const [employeeTypeQuery, setEmployeeTypeQuery] = useState("");

	useEffect(() => {
		let cancelled = false;
		void listPayrollPeople()
			.then((people) => {
				if (!cancelled) setRows(people);
			})
			.catch((error: unknown) => {
				toast.error(error instanceof Error ? error.message : "加载人员与工资基准失败");
			})
			.finally(() => {
				if (!cancelled) setLoading(false);
			});
		return () => {
			cancelled = true;
		};
	}, []);

	const visibleRows = useMemo(
		() =>
			filterPayrollPeople(rows, {
				name: nameQuery,
				employeeNo: employeeNoQuery,
				employeeType: employeeTypeQuery,
			}),
		[rows, nameQuery, employeeNoQuery, employeeTypeQuery],
	);

	const commitField = async (
		person: PayrollStoredPerson,
		field: keyof Omit<PayrollStoredPerson, "id">,
		value: string,
	) => {
		if (person[field] === value) return;
		setSavingId(person.id);
		try {
			const updated = await updatePayrollPerson(person.id, {
				[field]: value,
			} as Partial<Omit<PayrollStoredPerson, "id">>);
			setRows((current) => current.map((row) => (row.id === updated.id ? updated : row)));
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "保存失败");
		} finally {
			setSavingId(null);
		}
	};

	return (
		<section className="min-w-0 rounded-xl border border-slate-200 bg-white p-4">
			<div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
				<div className="min-w-0">
					<h2 className="text-sm font-semibold text-slate-800">人员底表与工资基准</h2>
					<p className="mt-0.5 text-xs text-slate-400">
						仅展示可沉淀的基准项；施工补贴存日标准，失焦后保存
						{savingId ? " · 保存中" : ""}
					</p>
				</div>
				<div className="grid min-w-0 flex-1 grid-cols-1 gap-2 sm:max-w-xl sm:grid-cols-3">
					<label className="min-w-0 text-xs text-slate-500">
						人员名称
						<input
							aria-label="筛选人员名称"
							className="mt-1 h-8 w-full rounded-md border border-slate-200 px-2 text-sm text-slate-800"
							placeholder="按姓名筛选"
							value={nameQuery}
							onChange={(event) => setNameQuery(event.target.value)}
						/>
					</label>
					<label className="min-w-0 text-xs text-slate-500">
						人员编号
						<input
							aria-label="筛选人员编号"
							className="mt-1 h-8 w-full rounded-md border border-slate-200 px-2 text-sm text-slate-800"
							placeholder="按编号筛选"
							value={employeeNoQuery}
							onChange={(event) => setEmployeeNoQuery(event.target.value)}
						/>
					</label>
					<label className="min-w-0 text-xs text-slate-500">
						人员类别
						<select
							aria-label="筛选人员类别"
							className="mt-1 h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-800"
							value={employeeTypeQuery}
							onChange={(event) => setEmployeeTypeQuery(event.target.value)}
						>
							<option value="">全部</option>
							{PAYROLL_EMPLOYEE_TYPES.map((type) => (
								<option key={type} value={type}>
									{type}
								</option>
							))}
						</select>
					</label>
				</div>
			</div>
			{loading ? (
				<p className="py-6 text-center text-sm text-slate-400">加载中...</p>
			) : (
				<div className="max-h-[min(22rem,50vh)] overflow-auto rounded-lg border border-slate-100">
					<table className="w-full table-fixed border-separate border-spacing-0 text-left text-sm">
						<thead className="text-xs text-slate-500">
							<tr className="border-b border-slate-100">
								<th className={`${STICKY_CELL} top-0 z-30 left-0 py-2.5 font-medium`}>项目</th>
								<th
									className={`${STICKY_CELL} top-0 z-30 py-2.5 font-medium`}
									style={stickyLeftStyle(1)}
								>
									人员编号
								</th>
								<th
									className={`${STICKY_CELL} top-0 z-30 py-2.5 font-medium shadow-[1px_0_0_0_rgb(241_245_249)]`}
									style={stickyLeftStyle(2)}
								>
									姓名
								</th>
								{PAYROLL_ROSTER_TEXT_FIELDS.map(([, label]) => (
									<th key={label} className={HEADER_CELL}>
										{label}
									</th>
								))}
								<th className={HEADER_CELL}>人员类别</th>
								{PAYROLL_BASELINE_FIELDS.map(([, label]) => (
									<th key={label} className={`${HEADER_CELL} text-center`}>
										{label}
									</th>
								))}
							</tr>
						</thead>
						<tbody>
							{visibleRows.length === 0 ? (
								<tr>
									<td
										colSpan={4 + PAYROLL_ROSTER_TEXT_FIELDS.length + PAYROLL_BASELINE_FIELDS.length}
										className="px-3 py-8 text-center text-sm text-slate-400"
									>
										没有匹配的人员
									</td>
								</tr>
							) : (
								visibleRows.map((person) => (
									<tr key={person.id} className="border-b border-slate-50">
										<td className={`${STICKY_CELL} left-0 py-1`}>
											<input
												aria-label={`${person.employeeNo}-projectName`}
												className="h-8 w-full min-w-0 overflow-hidden text-ellipsis rounded-md border border-transparent px-0 hover:border-slate-200 focus:border-slate-300 focus:outline-none"
												defaultValue={person.projectName}
												key={`${person.id}-projectName-${person.projectName}`}
												onBlur={(event) =>
													void commitField(person, "projectName", event.target.value.trim())
												}
											/>
										</td>
										<td className={`${STICKY_CELL} py-1`} style={stickyLeftStyle(1)}>
											<input
												aria-label={`${person.employeeNo}-employeeNo`}
												className="h-8 w-full min-w-0 overflow-hidden text-ellipsis rounded-md border border-transparent px-0 hover:border-slate-200 focus:border-slate-300 focus:outline-none"
												defaultValue={person.employeeNo}
												key={`${person.id}-employeeNo-${person.employeeNo}`}
												onBlur={(event) =>
													void commitField(person, "employeeNo", event.target.value.trim())
												}
											/>
										</td>
										<td
											className={`${STICKY_CELL} py-1 shadow-[1px_0_0_0_rgb(241_245_249)]`}
											style={stickyLeftStyle(2)}
										>
											<input
												aria-label={`${person.employeeNo}-name`}
												className="h-8 w-full min-w-0 overflow-hidden text-ellipsis rounded-md border border-transparent px-0 hover:border-slate-200 focus:border-slate-300 focus:outline-none"
												defaultValue={person.name}
												key={`${person.id}-name-${person.name}`}
												onBlur={(event) =>
													void commitField(person, "name", event.target.value.trim())
												}
											/>
										</td>
										{PAYROLL_ROSTER_TEXT_FIELDS.map(([field]) => (
											<td key={field} className={`${CELL_PX} min-w-0 py-1`}>
												<input
													aria-label={`${person.employeeNo}-${field}`}
													className="h-8 w-full min-w-0 overflow-hidden text-ellipsis rounded-md border border-transparent px-0 hover:border-slate-200 focus:border-slate-300 focus:outline-none"
													defaultValue={person[field]}
													key={`${person.id}-${field}-${person[field]}`}
													onBlur={(event) =>
														void commitField(person, field, event.target.value.trim())
													}
												/>
											</td>
										))}
										<td className={`${CELL_PX} min-w-0 py-1`}>
											<select
												aria-label={`${person.employeeNo}-employeeType`}
												className="h-8 w-full min-w-0 overflow-hidden text-ellipsis rounded-md border border-transparent bg-transparent px-0 hover:border-slate-200 focus:border-slate-300 focus:outline-none"
												value={person.employeeType}
												onChange={(event) =>
													void commitField(person, "employeeType", event.target.value)
												}
											>
												{PAYROLL_EMPLOYEE_TYPES.map((type) => (
													<option key={type} value={type}>
														{type}
													</option>
												))}
											</select>
										</td>
										{PAYROLL_BASELINE_FIELDS.map(([field]) => (
											<td key={field} className={`${CELL_PX} min-w-0 py-1`}>
												<input
													aria-label={`${person.employeeNo}-${field}`}
													className="h-8 w-full min-w-0 overflow-hidden text-ellipsis rounded-md border border-transparent px-0 text-center tabular-nums hover:border-slate-200 focus:border-slate-300 focus:outline-none"
													defaultValue={person[field]}
													key={`${person.id}-${field}-${person[field]}`}
													onBlur={(event) =>
														void commitField(person, field, event.target.value.trim())
													}
												/>
											</td>
										))}
									</tr>
								))
							)}
						</tbody>
					</table>
				</div>
			)}
		</section>
	);
}
