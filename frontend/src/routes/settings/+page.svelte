<script lang="ts">
	import { voiceEnabled, visionEnabled, visionProvider } from '$lib/stores/settingsStore';
	import { setVisionProvider } from '$lib/stores/chatStore';

	function onProviderChange(e: Event) {
		const value = (e.target as HTMLSelectElement).value as 'gemini' | 'mlx';
		visionProvider.set(value);
		setVisionProvider(value);
	}
</script>

<div class="mx-auto max-w-lg space-y-6">
	<h2 class="text-xl font-bold">Settings</h2>

	<div
		class="rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] p-4 space-y-4"
	>
		<label class="flex items-center justify-between">
			<span class="text-sm">Voice Input</span>
			<input type="checkbox" bind:checked={$voiceEnabled} class="accent-[var(--color-accent)]" />
		</label>
		<label class="flex items-center justify-between">
			<span class="text-sm">Vision</span>
			<input
				type="checkbox"
				bind:checked={$visionEnabled}
				class="accent-[var(--color-accent)]"
			/>
		</label>
		<label class="flex items-center justify-between">
			<span class="text-sm">Vision Provider</span>
			<select
				value={$visionProvider}
				onchange={onProviderChange}
				class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
			>
				<option value="gemini">Gemini (Cloud)</option>
				<option value="mlx">MLX (Local)</option>
			</select>
		</label>
	</div>

	<a href="/" class="inline-block text-sm text-[var(--color-accent)] hover:underline"
		>Back to Dashboard</a
	>
</div>
