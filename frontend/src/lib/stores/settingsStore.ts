import { writable } from 'svelte/store';

export const voiceEnabled = writable(true);
export const visionEnabled = writable(true);
export const visionProvider = writable<'gemini' | 'mlx'>('mlx');
