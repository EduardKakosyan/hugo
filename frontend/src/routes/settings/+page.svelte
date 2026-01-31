<script lang="ts">
	import { voiceEnabled, visionEnabled } from '$lib/stores/settingsStore';
</script>

<div class="mx-auto max-w-lg space-y-6">
	<h2 class="text-xl font-bold">Settings</h2>

	<div class="rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] p-4 space-y-4">
		<label class="flex items-center justify-between">
			<span class="text-sm">Voice Input</span>
			<input type="checkbox" bind:checked={$voiceEnabled} class="accent-[var(--color-accent)]" />
		</label>
		<label class="flex items-center justify-between">
			<span class="text-sm">Vision</span>
			<input type="checkbox" bind:checked={$visionEnabled} class="accent-[var(--color-accent)]" />
		</label>
	</div>

	<a href="/" class="inline-block text-sm text-[var(--color-accent)] hover:underline">Back to Dashboard</a>
</div>
