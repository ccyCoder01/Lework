import { afterEach, describe, expect, it, vi } from "vitest";

import { formatArtifactTime, formatDate, formatTime, parseOptionalTimestamp } from "./format";

describe("formatArtifactTime", () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it("当天文件显示为今天 HH:MM，而不是裸时刻", () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date(2026, 7, 24, 10, 30, 0));

		expect(formatArtifactTime(new Date(2026, 7, 24, 15, 4, 0).getTime())).toBe("今天 15:04");
	});

	it("前一天生成的文件跨天后显示昨天，而不是今天", () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date(2026, 7, 24, 10, 30, 0));

		expect(formatArtifactTime(new Date(2026, 7, 23, 15, 4, 0).getTime())).toBe("昨天 15:04");
	});

	it("更早的文件显示月日，不带今天", () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date(2026, 7, 24, 10, 30, 0));

		expect(formatArtifactTime(new Date(2026, 7, 10, 9, 5, 0).getTime())).toBe("8月10日 09:05");
	});

	it("兼容 Unix 秒级时间戳，避免被当成 1970 年而误判日期", () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date(2026, 7, 24, 10, 30, 0));
		const yesterdaySeconds = Math.floor(new Date(2026, 7, 23, 15, 4, 0).getTime() / 1000);

		expect(formatArtifactTime(yesterdaySeconds)).toBe("昨天 15:04");
	});
});

describe("formatDate", () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it("日期分隔线只显示今天/昨天，不含时刻", () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date(2026, 7, 24, 10, 30, 0));

		expect(formatDate(new Date(2026, 7, 24, 15, 4, 0).getTime())).toBe("今天");
		expect(formatDate(new Date(2026, 7, 23, 15, 4, 0).getTime())).toBe("昨天");
	});
});

describe("formatTime", () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it("会话消息：当天只显示时刻，昨天带昨天前缀", () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date(2026, 7, 24, 10, 30, 0));

		expect(formatTime(new Date(2026, 7, 24, 15, 4, 0).getTime())).toBe("15:04");
		expect(formatTime(new Date(2026, 7, 23, 15, 4, 0).getTime())).toBe("昨天 15:04");
	});
});

describe("parseOptionalTimestamp", () => {
	it("解析 RFC3339 字符串为毫秒", () => {
		expect(parseOptionalTimestamp("2026-08-23T07:04:00.000Z")).toBe(Date.parse("2026-08-23T07:04:00.000Z"));
	});

	it("解析 Unix 秒数字，避免 trim 报错或当成 1970", () => {
		expect(parseOptionalTimestamp(1_777_000_000)).toBe(1_777_000_000_000);
	});

	it("忽略 Go 零值时间", () => {
		expect(parseOptionalTimestamp("0001-01-01T00:00:00Z")).toBeUndefined();
	});
});
