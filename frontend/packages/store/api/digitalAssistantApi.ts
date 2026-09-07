import { apiClient } from "./client";
import type {
	BackendAITeammateTemplate,
	BackendDataResponse,
	BackendDigitalAssistant,
	BackendPaginatedResponse,
} from "./types";

export type DigitalAssistantVisibility = "public" | "private";
export type DigitalAssistantPermissionRole = "owner" | "admin" | "member";

export type DigitalAssistantPermission = {
	role: DigitalAssistantPermissionRole;
};

export type DigitalAssistantPermissionUser = {
	public_id: string;
	name: string;
	email?: string;
	avatar_url?: string;
};

export type DigitalAssistantPermissionMember = {
	user: DigitalAssistantPermissionUser;
	role: DigitalAssistantPermissionRole;
};

export type DigitalAssistantPermissionSettings = {
	visibility: DigitalAssistantVisibility;
	members: DigitalAssistantPermissionMember[];
};

export type DigitalAssistantPermissionMemberInput = {
	user: { public_id: string };
	role: DigitalAssistantPermissionRole;
};

export type CreateDAParams = {
	public_id?: string;
	name: string;
	role_name?: string;
	description?: string;
	avatar?: string;
	system_prompt?: string;
	expertise?: string[];
	template_id?: number;
	source?: string;
};

export type UpdateDAParams = {
	id: number;
	name?: string;
	role_name?: string;
	description?: string;
	avatar?: string;
	system_prompt?: string;
	expertise?: string[];
	template_id?: number;
	source?: string;
};

export type UpdateDAStatusParams = {
	id: number;
	status: string;
};

export type ListDAParams = {
	keyword?: string;
	status?: string;
	list_all?: boolean;
	offset?: number;
	limit?: number;
};

export type GetDAParams = {
	id?: number;
	public_id?: string;
};

export type CheckDANameParams = {
	name: string;
	exclude_id?: number;
};

export type CreateDAFromTemplateParams = {
	template_id: number;
	public_id?: string;
	name?: string;
	role_name?: string;
	description?: string;
	avatar?: string;
	system_prompt?: string;
	expertise?: string[];
};

export type ListAITeammateTemplateParams = {
	keyword?: string;
	category?: string;
	status?: string;
	list_all?: boolean;
	offset?: number;
	limit?: number;
};

export type GetAITeammateTemplateParams = {
	id?: number;
	code?: string;
};

export type IncrementAITeammateTemplateCountParams = {
	id?: number;
	code?: string;
};

export type UpdateDigitalAssistantPermissionsParams = {
	public_id: string;
	visibility: DigitalAssistantVisibility;
	members: DigitalAssistantPermissionMemberInput[];
};

const DA_ENDPOINTS = {
	create: "/CreateDigitalAssistant",
	createFromTemplate: "/CreateDigitalAssistantFromTemplate",
	list: "/ListDigitalAssistant",
	checkName: "/CheckDigitalAssistantName",
	get: "/GetDigitalAssistant",
	update: "/UpdateDigitalAssistant",
	updateStatus: "/UpdateDigitalAssistantStatus",
	delete: "/DeleteDigitalAssistant",
	getPermissions: "/GetDigitalAssistantPermissions",
	updatePermissions: "/UpdateDigitalAssistantPermissions",
	listTemplates: "/ListAITeammateTemplates",
	getTemplate: "/GetAITeammateTemplate",
	incrementTemplateUseCount: "/IncrementAITeammateTemplateUseCount",
	incrementTemplateRecommendCount: "/IncrementAITeammateTemplateRecommendCount",
};

export const digitalAssistantApi = {
	create: (params: CreateDAParams) =>
		apiClient.post<BackendDataResponse<BackendDigitalAssistant>>(DA_ENDPOINTS.create, params),

	createFromTemplate: (params: CreateDAFromTemplateParams) =>
		apiClient.post<BackendDataResponse<BackendDigitalAssistant>>(
			DA_ENDPOINTS.createFromTemplate,
			params,
		),

	list: (params: ListDAParams) =>
		apiClient.post<BackendPaginatedResponse<BackendDigitalAssistant>>(DA_ENDPOINTS.list, params),

	checkName: (params: CheckDANameParams) =>
		apiClient.post<BackendDataResponse<{ available: boolean }>>(DA_ENDPOINTS.checkName, params),

	get: (params: GetDAParams) =>
		apiClient.post<BackendDataResponse<BackendDigitalAssistant>>(DA_ENDPOINTS.get, params),

	update: (params: UpdateDAParams) =>
		apiClient.post<BackendDataResponse<BackendDigitalAssistant>>(DA_ENDPOINTS.update, params),

	updateStatus: (params: UpdateDAStatusParams) =>
		apiClient.post<BackendDataResponse<null>>(DA_ENDPOINTS.updateStatus, params),

	delete: (id: number) => apiClient.post<BackendDataResponse<null>>(DA_ENDPOINTS.delete, { id }),

	getPermissions: (publicID: string) =>
		apiClient.post<BackendDataResponse<DigitalAssistantPermissionSettings>>(
			DA_ENDPOINTS.getPermissions,
			{ public_id: publicID },
		),

	updatePermissions: (params: UpdateDigitalAssistantPermissionsParams) =>
		apiClient.post<BackendDataResponse<DigitalAssistantPermissionSettings>>(
			DA_ENDPOINTS.updatePermissions,
			params,
		),

	listTemplates: (params: ListAITeammateTemplateParams) =>
		apiClient.post<BackendPaginatedResponse<BackendAITeammateTemplate>>(
			DA_ENDPOINTS.listTemplates,
			params,
		),

	getTemplate: (params: GetAITeammateTemplateParams) =>
		apiClient.post<BackendDataResponse<BackendAITeammateTemplate>>(
			DA_ENDPOINTS.getTemplate,
			params,
		),

	incrementTemplateUseCount: (params: IncrementAITeammateTemplateCountParams) =>
		apiClient.post<BackendDataResponse<null>>(DA_ENDPOINTS.incrementTemplateUseCount, params),

	incrementTemplateRecommendCount: (params: IncrementAITeammateTemplateCountParams) =>
		apiClient.post<BackendDataResponse<null>>(DA_ENDPOINTS.incrementTemplateRecommendCount, params),
};
