import { afterEach, describe, expect, it } from "vitest";

import {
	clampLeftRailWidth,
	LEFT_RAIL_COLLAPSED_STORAGE_KEY,
	LEFT_RAIL_DEFAULT_WIDTH,
	LEFT_RAIL_WIDTH_STORAGE_KEY,
	readStoredLeftRailPreferences,
	writeStoredLeftRailCollapsed,
	writeStoredLeftRailWidth,
} from "./leftRailStorage";

describe("leftRailStorage", () => {
	afterEach(() => {
		window.localStorage.removeItem(LEFT_RAIL_WIDTH_STORAGE_KEY);
		window.localStorage.removeItem(LEFT_RAIL_COLLAPSED_STORAGE_KEY);
	});

	it("无缓存时返回默认宽度与展开状态", () => {
		expect(readStoredLeftRailPreferences()).toEqual({
			width: LEFT_RAIL_DEFAULT_WIDTH,
			collapsed: false,
		});
	});

	it("会同步读取并 clamp 已保存的宽度", () => {
		window.localStorage.setItem(LEFT_RAIL_WIDTH_STORAGE_KEY, "400");
		window.localStorage.setItem(LEFT_RAIL_COLLAPSED_STORAGE_KEY, "true");

		expect(readStoredLeftRailPreferences()).toEqual({
			width: clampLeftRailWidth(400),
			collapsed: true,
		});
	});

	it("写入宽度与收起状态", () => {
		writeStoredLeftRailWidth(280);
		writeStoredLeftRailCollapsed(true);

		expect(window.localStorage.getItem(LEFT_RAIL_WIDTH_STORAGE_KEY)).toBe("280");
		expect(window.localStorage.getItem(LEFT_RAIL_COLLAPSED_STORAGE_KEY)).toBe("true");
	});
});
