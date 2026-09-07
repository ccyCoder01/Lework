const WEEKDAY_NAMES = [
	"\u661f\u671f\u65e5",
	"\u661f\u671f\u4e00",
	"\u661f\u671f\u4e8c",
	"\u661f\u671f\u4e09",
	"\u661f\u671f\u56db",
	"\u661f\u671f\u4e94",
	"\u661f\u671f\u516d",
] as const;

const MS_PER_DAY = 86_400_000;
/** 小于该阈值视为 Unix 秒；2026 年的毫秒时间戳约 1.7e12。 */
const UNIX_MS_THRESHOLD = 1e12;

function pad2(value: number): string {
	return String(value).padStart(2, "0");
}

function startOfLocalDay(date: Date): number {
	return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function formatClockTime(date: Date): string {
	return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function toEpochMs(timestamp: number): number {
	if (!Number.isFinite(timestamp) || timestamp <= 0) return Number.NaN;
	return timestamp < UNIX_MS_THRESHOLD ? timestamp * 1000 : timestamp;
}

function calendarDayDiff(date: Date, now: Date): number {
	return Math.floor((startOfLocalDay(now) - startOfLocalDay(date)) / MS_PER_DAY);
}

function formatAbsoluteDateTime(date: Date, now: Date): string {
	const timePart = formatClockTime(date);
	if (date.getFullYear() === now.getFullYear()) {
		return `${date.getMonth() + 1}\u6708${date.getDate()}\u65e5 ${timePart}`;
	}
	return `${date.getFullYear()}\u5e74${date.getMonth() + 1}\u6708${date.getDate()}\u65e5 ${timePart}`;
}

function formatAbsoluteDate(date: Date, now: Date): string {
	if (date.getFullYear() === now.getFullYear()) {
		return `${date.getMonth() + 1}\u6708${date.getDate()}\u65e5`;
	}
	return `${date.getFullYear()}\u5e74${date.getMonth() + 1}\u6708${date.getDate()}\u65e5`;
}

/** 按微信会话消息时间规则展示：当天只显示时刻 / 昨天 / 近7天星期 / 今年月日 / 跨年年月日。 */
export function formatTime(timestamp: number): string {
	const ms = toEpochMs(timestamp);
	if (!Number.isFinite(ms)) return "";
	const date = new Date(ms);
	const now = new Date();
	const timePart = formatClockTime(date);
	const dayDiff = calendarDayDiff(date, now);

	if (dayDiff === 0) {
		return timePart;
	}
	if (dayDiff === 1) {
		return `\u6628\u5929 ${timePart}`;
	}
	if (dayDiff > 1 && dayDiff < 7) {
		return `${WEEKDAY_NAMES[date.getDay()]} ${timePart}`;
	}
	return formatAbsoluteDateTime(date, now);
}

/** 日期分隔线：今天 / 昨天 / 今年月日 / 跨年年月日，不含时刻。 */
export function formatDate(timestamp: number): string {
	const ms = toEpochMs(timestamp);
	if (!Number.isFinite(ms)) return "";
	const date = new Date(ms);
	const now = new Date();
	const dayDiff = calendarDayDiff(date, now);
	if (dayDiff === 0) {
		return "\u4eca\u5929";
	}
	if (dayDiff === 1) {
		return "\u6628\u5929";
	}
	return formatAbsoluteDate(date, now);
}

/** 产物/任务文件时间：按本地日历日展示今天/昨天，避免跨天后仍写成「今天」。 */
export function formatArtifactTime(timestamp?: number): string {
	if (timestamp == null) return "";
	const ms = toEpochMs(timestamp);
	if (!Number.isFinite(ms)) return "";
	const date = new Date(ms);
	const now = new Date();
	const timePart = formatClockTime(date);
	const dayDiff = calendarDayDiff(date, now);
	if (dayDiff === 0) {
		return `\u4eca\u5929 ${timePart}`;
	}
	if (dayDiff === 1) {
		return `\u6628\u5929 ${timePart}`;
	}
	return formatAbsoluteDateTime(date, now);
}

export function parseOptionalTimestamp(value?: string | number): number | undefined {
	if (value == null || value === "") return undefined;
	if (typeof value === "number") {
		const ms = toEpochMs(value);
		return Number.isFinite(ms) && ms > 0 ? ms : undefined;
	}

	const normalized = value.trim();
	if (!normalized || normalized.startsWith("0001-01-01")) return undefined;
	if (/^\d+(\.\d+)?$/.test(normalized)) {
		const ms = toEpochMs(Number(normalized));
		return Number.isFinite(ms) && ms > 0 ? ms : undefined;
	}

	const timestamp = new Date(normalized).getTime();
	return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : undefined;
}

export function formatFileSize(bytes: number): string {
	if (bytes < 1024) return `${bytes}B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function formatTokenCount(count: number): string {
	if (!count) return "0";
	if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`;
	if (count >= 1000) return `${(count / 1000).toFixed(1)}K`;
	return String(count);
}

export function formatLatency(ms: number): string {
	if (!Number.isFinite(ms) || ms <= 0) return "0ms";
	if (ms >= 1000) {
		const seconds = ms / 1000;
		return seconds >= 10 ? `${Math.round(seconds)}s` : `${seconds.toFixed(1)}s`;
	}
	return `${Math.round(ms)}ms`;
}
