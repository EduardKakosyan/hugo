import { writable, get } from 'svelte/store';
import type { ChatMessage, WSMessage } from '$lib/types';

export const messages = writable<ChatMessage[]>([]);
export const isLoading = writable(false);
export const wsConnected = writable(false);
export const voiceTranscripts = writable<string[]>([]);

let nextId = 0;
let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

// Map OpenClaw reqId to our message id for streaming updates
const reqIdToMsgId = new Map<string, string>();

export function addMessage(
	role: 'user' | 'assistant',
	content: string,
	streaming = false
): string {
	const id = String(nextId++);
	messages.update((msgs) => [...msgs, { id, role, content, timestamp: Date.now(), streaming }]);
	return id;
}

function updateMessage(id: string, updater: (msg: ChatMessage) => ChatMessage): void {
	messages.update((msgs) => msgs.map((m) => (m.id === id ? updater(m) : m)));
}

function handleWsMessage(event: MessageEvent): void {
	const msg: WSMessage = JSON.parse(event.data);
	const data = typeof msg.data === 'string' ? JSON.parse(msg.data) : msg.data;

	switch (msg.type) {
		case 'chat:start': {
			// Create a placeholder assistant message for streaming
			const msgId = addMessage('assistant', '', true);
			reqIdToMsgId.set(data.reqId, msgId);
			break;
		}
		case 'chat:delta': {
			const msgId = reqIdToMsgId.get(data.reqId);
			if (msgId) {
				updateMessage(msgId, (m) => ({ ...m, content: m.content + data.delta }));
			}
			break;
		}
		case 'chat:done': {
			const msgId = reqIdToMsgId.get(data.reqId);
			if (msgId) {
				updateMessage(msgId, (m) => ({
					...m,
					content: data.text || m.content,
					streaming: false
				}));
				reqIdToMsgId.delete(data.reqId);
			}
			isLoading.set(false);
			break;
		}
		case 'chat:error': {
			addMessage('assistant', `Error: ${data.error}`);
			isLoading.set(false);
			break;
		}
		case 'voice:transcript': {
			voiceTranscripts.update((t) => [...t, `You: ${data.text}`]);
			break;
		}
		case 'voice:response': {
			voiceTranscripts.update((t) => [...t, `Hugo: ${data.text}`]);
			break;
		}
		case 'pong':
			break;
	}
}

export function connectWs(): void {
	if (ws && ws.readyState === WebSocket.OPEN) return;

	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	const url = `${protocol}//${window.location.host}/ws`;
	ws = new WebSocket(url);

	ws.onopen = () => {
		wsConnected.set(true);
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
	};

	ws.onmessage = handleWsMessage;

	ws.onclose = () => {
		wsConnected.set(false);
		ws = null;
		// Auto-reconnect after 2 seconds
		reconnectTimer = setTimeout(connectWs, 2000);
	};

	ws.onerror = () => {
		ws?.close();
	};
}

export function disconnectWs(): void {
	if (reconnectTimer) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}
	ws?.close();
	ws = null;
	wsConnected.set(false);
}

export function sendChat(message: string): void {
	addMessage('user', message);
	isLoading.set(true);

	if (ws && ws.readyState === WebSocket.OPEN) {
		// Stream via WebSocket
		ws.send(JSON.stringify({ type: 'chat', data: message }));
	} else {
		// Fallback to REST if WebSocket not connected
		fetch('/api/chat', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ message })
		})
			.then((resp) => resp.json())
			.then((data) => {
				if (data.response) {
					addMessage('assistant', data.response);
				} else if (data.error) {
					addMessage('assistant', `Error: ${data.error}`);
				}
			})
			.catch((err) => {
				addMessage('assistant', `Network error: ${err}`);
			})
			.finally(() => {
				isLoading.set(false);
			});
	}
}
