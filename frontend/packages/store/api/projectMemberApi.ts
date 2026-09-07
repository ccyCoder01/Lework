import { type UserInfo, userApi } from "./userApi";

export type HumanProjectMemberOption = UserInfo;

export const projectMemberApi = {
	listHumanMembers: async (params: { keyword?: string; limit?: number } = {}) => {
		const response = await userApi.list({
			keyword: params.keyword,
			offset: 0,
			limit: params.limit ?? 100,
		});
		return response.data.data?.items ?? [];
	},
};
