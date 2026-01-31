<script lang="ts">
	let { transcripts = [] }: { transcripts: string[] } = $props();
</script>

<div class="rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]">
	<div class="border-b border-[var(--color-border)] px-4 py-2 text-sm font-medium text-[var(--color-text)]">
		Voice Transcripts
	</div>
	<div class="max-h-48 overflow-y-auto p-4 space-y-2">
		{#if transcripts.length === 0}
			<p class="text-sm text-[var(--color-text-muted)]">No transcripts yet. Speak into the mic.</p>
		{:else}
			{#each transcripts as t, i (i)}
				<p class="text-sm text-[var(--color-text)]">{t}</p>
			{/each}
		{/if}
	</div>
</div>
