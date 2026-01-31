export interface ChatMessage {
	id: string;
	role: 'user' | 'assistant';
	content: string;
	timestamp: number;
	streaming?: boolean;
}

export interface ServiceStatus {
	voice: 'ok' | 'not_loaded' | 'error';
	vision: 'configured' | 'not_configured' | 'error';
	openclaw: 'ok' | 'unknown' | 'error';
}

export interface WSMessage {
	type:
		| 'transcript'
		| 'response'
		| 'status'
		| 'error'
		| 'pong'
		| 'chat:start'
		| 'chat:delta'
		| 'chat:done'
		| 'chat:error';
	data: string;
}
