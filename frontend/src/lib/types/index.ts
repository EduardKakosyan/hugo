export interface RobotState {
	connected: boolean;
	head?: {
		roll: number;
		pitch: number;
		yaw: number;
	};
	error?: string;
}

export interface ChatMessage {
	role: 'user' | 'assistant';
	content: string;
	timestamp: number;
}

export interface IntegrationInfo {
	name: string;
	description: string;
	active: boolean;
}

export interface StatusResponse {
	robot_connected: boolean;
	agent_model: string;
	voice_engine: string;
	active_integrations: string[];
}

export interface AppSettings {
	backendUrl: string;
	wsUrl: string;
	llmProvider: string;
	voiceEngine: string;
	robotHost: string;
	robotPort: number;
	simulation: boolean;
}
