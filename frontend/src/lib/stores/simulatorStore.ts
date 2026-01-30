import { writable } from 'svelte/store';

export const simFrame = writable<string | null>(null);
export const simConnected = writable(false);

let ws: WebSocket | null = null;
let currentUrl: string | null = null;

export function connectSimulator(wsUrl: string): void {
	if (ws && currentUrl === wsUrl) return;
	disconnectSimulator();

	currentUrl = wsUrl;
	ws = new WebSocket(`${wsUrl}/ws/sim_video`);
	ws.binaryType = 'arraybuffer';

	ws.onopen = () => {
		simConnected.set(true);
	};

	ws.onmessage = (event) => {
		const blob = new Blob([event.data], { type: 'image/jpeg' });
		const url = URL.createObjectURL(blob);
		simFrame.update((prev) => {
			if (prev) URL.revokeObjectURL(prev);
			return url;
		});
	};

	ws.onclose = () => {
		simConnected.set(false);
		currentUrl = null;
		setTimeout(() => connectSimulator(wsUrl), 3000);
	};

	ws.onerror = () => {
		simConnected.set(false);
	};
}

export function disconnectSimulator(): void {
	if (ws) {
		ws.close();
		ws = null;
		currentUrl = null;
	}
}
