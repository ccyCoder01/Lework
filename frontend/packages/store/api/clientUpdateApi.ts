import { apiClient } from "./client";
import {
	type ClientUpdatePolicy,
	type ClientVersionReportParams,
	dispatchClientUpgradeRequired,
	getClientVersionReport,
} from "./clientUpdatePolicy";
import type { BackendDataResponse } from "./types";

export const CLIENT_UPDATE_ENDPOINTS = {
	report: "/ClientVersionReport",
} as const;

export const clientUpdateApi = {
	reportVersion: async (params: ClientVersionReportParams = getClientVersionReport()) => {
		const response = await apiClient.post<BackendDataResponse<ClientUpdatePolicy>>(
			CLIENT_UPDATE_ENDPOINTS.report,
			params,
		);

		if (response.data.data?.force_update) {
			dispatchClientUpgradeRequired(response.data.data);
		}

		return response;
	},
};
