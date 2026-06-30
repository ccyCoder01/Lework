"use client";

import { useChatStore, useLayoutStore } from "@leros/store";
import { useEffect, useLayoutEffect } from "react";
import { ChatHeader } from "../chat/ChatHeader";
import { MessageTimeline } from "../chat/MessageTimeline";
import { ChatInput } from "../input/ChatInput";

export function CenterCanvas() {
	const { loadConversationMessages, activeSessionId } = useChatStore(
		(s) => s,
	);
	const { clearTaskDetailRoute } = useLayoutStore((s) => s);

	useLayoutEffect(() => {
		clearTaskDetailRoute();
	}, [clearTaskDetailRoute]);

	// 挂载时重新加载会话消息，若 runtime_status 为 "responding" 则自动触发 SSE 回放
	useEffect(() => {
		if (activeSessionId) {
			loadConversationMessages(activeSessionId);
		}
	}, [activeSessionId, loadConversationMessages]);

	return (
		<div data-slot="center-canvas" className="flex h-full flex-1 flex-col bg-slate-50/80">
			<ChatHeader />
			<div className="flex min-h-0 flex-1 flex-col bg-[linear-gradient(180deg,#f8fafc_0%,#f6f7fb_100%)]">
				<MessageTimeline />
				<ChatInput />
			</div>
		</div>
	);
}
