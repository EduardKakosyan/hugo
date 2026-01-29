import { writable } from 'svelte/store';
import type { RobotState } from '$lib/types';

export const robotState = writable<RobotState>({ connected: false });

let ws: WebSocket | null = null;

export function connectTelemetry(wsUrl: string): void {
	if (ws) ws.close();

	ws = new WebSocket(`${wsUrl}/ws/telemetry`);

	ws.onmessage = (event) => {
		try {
			const state: RobotState = JSON.parse(event.data);
			robotState.set(state);
		} catch {
			// ignore parse errors
		}
	};

	ws.onclose = () => {
		robotState.set({ connected: false });
		// Reconnect after 3 seconds
		setTimeout(() => connectTelemetry(wsUrl), 3000);
	};

	ws.onerror = () => {
		robotState.set({ connected: false });
	};
}

export function disconnectTelemetry(): void {
	if (ws) {
		ws.close();
		ws = null;
	}
}
