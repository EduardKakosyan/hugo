import { writable } from 'svelte/store';
import type { AppSettings } from '$lib/types';

const DEFAULT_SETTINGS: AppSettings = {
	backendUrl: 'http://localhost:8080',
	wsUrl: 'ws://localhost:8080',
	llmProvider: 'gemini/gemini-2.5-flash',
	voiceEngine: 'fallback',
	robotHost: 'localhost',
	robotPort: 8000,
	simulation: true
};

function loadSettings(): AppSettings {
	if (typeof window === 'undefined') return DEFAULT_SETTINGS;
	try {
		const stored = localStorage.getItem('hugo-settings');
		if (stored) return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) };
	} catch {
		// ignore
	}
	return DEFAULT_SETTINGS;
}

export const settings = writable<AppSettings>(loadSettings());

settings.subscribe((value) => {
	if (typeof window !== 'undefined') {
		localStorage.setItem('hugo-settings', JSON.stringify(value));
	}
});
