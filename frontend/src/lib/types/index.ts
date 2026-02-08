export type Modality = 'text' | 'voice' | 'vision' | 'voice+vision';

export interface ChatMessage {
	id: string;
	role: 'user' | 'assistant';
	content: string;
	timestamp: number;
	streaming?: boolean;
	source?: 'voice' | 'typed';
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
		| 'chat:error'
		| 'voice:transcript'
		| 'voice:response'
		| 'voice:status'
		| 'voice:error'
		| 'session:reset'
		| 'vision:provider'
		| 'vision:error';
	data: string;
}
