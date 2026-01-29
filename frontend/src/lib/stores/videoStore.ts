import { writable } from 'svelte/store';

export const latestFrame = writable<string | null>(null);
export const videoConnected = writable(false);

let ws: WebSocket | null = null;

export function connectVideo(wsUrl: string): void {
	if (ws) ws.close();

	ws = new WebSocket(`${wsUrl}/ws/video`);
	ws.binaryType = 'arraybuffer';

	ws.onopen = () => {
		videoConnected.set(true);
	};

	ws.onmessage = (event) => {
		const blob = new Blob([event.data], { type: 'image/jpeg' });
		const url = URL.createObjectURL(blob);
		latestFrame.update((prev) => {
			if (prev) URL.revokeObjectURL(prev);
			return url;
		});
	};

	ws.onclose = () => {
		videoConnected.set(false);
		setTimeout(() => connectVideo(wsUrl), 3000);
	};

	ws.onerror = () => {
		videoConnected.set(false);
	};
}

export function disconnectVideo(): void {
	if (ws) {
		ws.close();
		ws = null;
	}
}
