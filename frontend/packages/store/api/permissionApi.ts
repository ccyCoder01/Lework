import { apiClient } from "../api/client";
import type { BackendDataResponse } from "../api/types";
import type { Action, BatchCheckItem, BatchCheckResult, ResourceRef } from "../permission/types";

type BackendBatchCheckResult = {
	action: Action;
	resource: {
		type: ResourceRef["type"];
		public_id: string;
	};
	allowed: boolean;
	reason?: string;
	role?: string;
	inherited?: boolean;
};

function toBatchCheckItem(item: BatchCheckItem) {
	return {
		action: item.action,
		resource: {
			type: item.resource.type,
			public_id: item.resource.publicId,
		},
	};
}

export const permissionApi = {
	batchCheck: (items: BatchCheckItem[]) =>
		apiClient.post<BackendDataResponse<BackendBatchCheckResult[]>>("/BatchCheckPermission", {
			items: items.map(toBatchCheckItem),
		}),
};

export function mapBatchCheckResults(
	items: BatchCheckItem[],
	results: BackendBatchCheckResult[],
): BatchCheckResult[] {
	return results.map((result, index) => {
		const requestItem = items[index];
		return {
			action: result.action ?? requestItem?.action,
			resource: {
				type: result.resource?.type ?? requestItem?.resource.type,
				publicId: result.resource?.public_id ?? requestItem?.resource.publicId,
			},
			allowed: Boolean(result.allowed),
			reason: result.reason,
			role: result.role,
			inherited: result.inherited,
		};
	});
}
