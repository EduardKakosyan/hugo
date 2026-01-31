<script lang="ts">
	let analysis = $state('No analysis yet.');
	let loading = $state(false);

	async function analyze() {
		loading = true;
		try {
			const resp = await fetch('/tools/vision/analyze', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ query: 'Describe what you see in detail.' })
			});
			const data = await resp.json();
			analysis = data.description || 'No description returned.';
		} catch (err) {
			analysis = `Error: ${err}`;
		} finally {
			loading = false;
		}
	}
</script>

<div class="rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]">
	<div class="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2">
		<span class="text-sm font-medium text-[var(--color-text)]">Vision</span>
		<button
			onclick={analyze}
			disabled={loading}
			class="rounded-md bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
		>
			{loading ? 'Analyzing...' : 'Capture'}
		</button>
	</div>
	<div class="p-4 text-sm text-[var(--color-text-muted)]">
		{analysis}
	</div>
</div>
