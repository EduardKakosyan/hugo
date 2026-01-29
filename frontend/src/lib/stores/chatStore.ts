import { writable, get } from 'svelte/store';
import type { ChatMessage } from '$lib/types';

export const messages = writable<ChatMessage[]>([]);
export const isStreaming = writable(false);

let ws: WebSocket | null = null;

export function connectChat(wsUrl: string): void {
	if (ws) ws.close();

	ws = new WebSocket(`${wsUrl}/ws/chat`);

	ws.onmessage = (event) => {
		try {
			const data = JSON.parse(event.data);

			if (data.type === 'token') {
				messages.update((msgs) => {
					const last = msgs[msgs.length - 1];
					if (last && last.role === 'assistant') {
						last.content += data.content;
						return [...msgs.slice(0, -1), last];
					}
					return [
						...msgs,
						{ role: 'assistant', content: data.content, timestamp: Date.now() }
					];
				});
			}

			if (data.type === 'done') {
				isStreaming.set(false);
			}

			if (data.type === 'error') {
				isStreaming.set(false);
				messages.update((msgs) => [
					...msgs,
					{ role: 'assistant', content: `Error: ${data.content}`, timestamp: Date.now() }
				]);
			}
		} catch {
			// ignore
		}
	};

	ws.onclose = () => {
		setTimeout(() => connectChat(wsUrl), 3000);
	};
}

export function sendMessage(text: string): void {
	if (!ws || ws.readyState !== WebSocket.OPEN) return;

	messages.update((msgs) => [...msgs, { role: 'user', content: text, timestamp: Date.now() }]);

	isStreaming.set(true);
	ws.send(JSON.stringify({ message: text }));
}

export function disconnectChat(): void {
	if (ws) {
		ws.close();
		ws = null;
	}
}
