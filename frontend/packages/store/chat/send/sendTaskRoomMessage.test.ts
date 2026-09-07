import { afterEach, describe, expect, it, vi } from "vitest";

import { isSessionReplySuppressed } from "../messageMerge";
import type { SendPipelineDeps } from "./deps";
import { sendTaskRoomMessage } from "./sendTaskRoomMessage";

vi.mock("../../api/sessionApi", () => ({
	sessionApi: {
		addMessage: vi.fn(),
	},
}));

vi.mock("./assistantFallback", () => ({
	waitForGlobalAssistantOrFail: vi.fn().mockResolvedValue(undefined),
}));

import { sessionApi } from "../../api/sessionApi";

function createDeps(overrides?: Partial<ReturnType<SendPipelineDeps["get"]>>): SendPipelineDeps {
	let state = {
		activeSessionId: "session-1",
		streamingMessageId: null,
		isGenerating: false,
		suppressedReplySessionId: null as string | null,
		executionMode: "default" as const,
		messagesMap: {},
		messageIds: [],
		...overrides,
	};
	return {
		get: () => state as never,
		set: (partial: Parameters<SendPipelineDeps["set"]>[0]) => {
			state = {
				...state,
				...(typeof partial === "function" ? partial(state as never) : partial),
			};
		},
		addMessage: vi.fn(),
		updateMessage: vi.fn(),
		finishStream: vi.fn(),
		loadConversationMessages: vi.fn().mockResolvedValue(undefined),
		startGlobalEvents: vi.fn(),
		drainGlobalEvents: vi.fn(),
		effects: {
			navigateToTaskDetail: vi.fn(),
			clearComposer: vi.fn(),
		},
	} as unknown as SendPipelineDeps;
}

const params = {
	projectId: "project-1",
	taskId: "task-1",
	sessionId: "session-1",
};

describe("isSessionReplySuppressed", () => {
	it("仅在当前 session 被超时抑制时为真", () => {
		expect(isSessionReplySuppressed({ suppressedReplySessionId: "session-1" }, "session-1")).toBe(
			true,
		);
		expect(isSessionReplySuppressed({ suppressedReplySessionId: "session-1" }, "session-2")).toBe(
			false,
		);
		expect(isSessionReplySuppressed({ suppressedReplySessionId: null }, "session-1")).toBe(false);
		expect(isSessionReplySuppressed({ suppressedReplySessionId: "session-1" }, null)).toBe(false);
	});
});

describe("sendTaskRoomMessage", () => {
	afterEach(() => {
		vi.clearAllMocks();
	});

	it("当前会话已超时报错时拒绝续聊，不调用 AddMessage", async () => {
		const addMessage = vi.mocked(sessionApi.addMessage);
		const deps = createDeps({ suppressedReplySessionId: "session-1" });

		const result = await sendTaskRoomMessage(deps, "第二轮提问", params);

		expect(result).toBeNull();
		expect(deps.addMessage).not.toHaveBeenCalled();
		expect(addMessage).not.toHaveBeenCalled();
		expect(deps.get().suppressedReplySessionId).toBe("session-1");
	});

	it("抑制的是其他会话时仍允许发送", async () => {
		const addMessage = vi.mocked(sessionApi.addMessage).mockResolvedValue({} as never);
		const deps = createDeps({ suppressedReplySessionId: "session-other" });

		const result = await sendTaskRoomMessage(deps, "继续提问", params);

		expect(result).toEqual({
			project_id: "project-1",
			task_id: "task-1",
			session_id: "session-1",
		});
		expect(addMessage).toHaveBeenCalled();
	});
});
