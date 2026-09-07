import { apiClient } from "./client";
import type { BackendDataResponse } from "./types";

export type FeedbackType = "problem" | "suggestion" | "experience" | "other";

export type SubmitFeedbackParams = {
	type: FeedbackType;
	content: string;
	attachment_ids?: string[];
	client?: { platform: "web" | "desktop"; version?: string };
};

export type SubmitFeedbackResponse = {
	status: "accepted";
};

export const feedbackApi = {
	submit: (params: SubmitFeedbackParams) =>
		apiClient.post<BackendDataResponse<SubmitFeedbackResponse>>("/SubmitFeedback", params),
};
