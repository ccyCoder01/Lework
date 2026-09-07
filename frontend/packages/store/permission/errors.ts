import type { BackendBaseResponse } from "../api/types";
import type { ApiError } from "../types/api";
import {
	CODE_FORBIDDEN,
	dispatchPermissionDenied,
	type PermissionDecision,
	toPermissionMessage,
} from "./types";

export class PermissionDeniedError extends Error {
	readonly code = CODE_FORBIDDEN;

	constructor(message = "permission denied") {
		super(message);
		this.name = "PermissionDeniedError";
	}
}

function readBackendCode(err: unknown): number | undefined {
	const apiErr = err as ApiError;
	const data = apiErr?.response?.data as BackendBaseResponse | undefined;
	return typeof data?.code === "number" ? data.code : undefined;
}

export function isPermissionDeniedError(err: unknown): boolean {
	if (err instanceof PermissionDeniedError) return true;
	const apiErr = err as ApiError;
	if (apiErr?.status === 403) return true;
	return readBackendCode(err) === CODE_FORBIDDEN;
}

export function toPermissionDeniedError(err: unknown): PermissionDeniedError | null {
	if (!isPermissionDeniedError(err)) return null;
	if (err instanceof PermissionDeniedError) return err;
	const apiErr = err as ApiError;
	const data = apiErr?.response?.data as BackendBaseResponse | undefined;
	return new PermissionDeniedError(data?.message || apiErr.message || "permission denied");
}

export function handlePermissionDenied(err: unknown, notify = true): boolean {
	if (!isPermissionDeniedError(err)) return false;
	const message = toPermissionMessage(readPermissionReason(err));
	if (notify) {
		dispatchPermissionDenied(message);
	}
	return true;
}

function readPermissionReason(err: unknown): string | undefined {
	const apiErr = err as ApiError;
	const data = apiErr?.response?.data as BackendBaseResponse | undefined;
	return typeof data?.message === "string" ? data.message : undefined;
}

export function decisionFromBatchResult(result: {
	allowed: boolean;
	reason?: string;
	role?: string;
	inherited?: boolean;
}): PermissionDecision {
	return {
		allowed: result.allowed,
		reason: result.reason,
		role: result.role,
		inherited: result.inherited,
	};
}

export function throwIfForbiddenResponse(payload: BackendBaseResponse): void {
	if (payload.code === CODE_FORBIDDEN) {
		throw new PermissionDeniedError(payload.message || "permission denied");
	}
}
