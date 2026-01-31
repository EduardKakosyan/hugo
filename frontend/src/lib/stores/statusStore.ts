import { writable } from 'svelte/store';
import type { ServiceStatus } from '$lib/types';

export const serviceStatus = writable<ServiceStatus>({
	voice: 'not_loaded',
	vision: 'not_configured',
	openclaw: 'unknown'
});

export const connected = writable(false);

export async function fetchStatus(): Promise<void> {
	try {
		const resp = await fetch('/api/status');
		const data = await resp.json();
		serviceStatus.set({
			voice: data.voice,
			vision: data.vision,
			openclaw: data.openclaw
		});
	} catch {
		serviceStatus.set({ voice: 'error', vision: 'error', openclaw: 'error' });
	}
}
