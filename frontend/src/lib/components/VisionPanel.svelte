<script lang="ts">
	import { visionProvider } from '$lib/stores/settingsStore';
	import { setVisionProvider } from '$lib/stores/chatStore';

	const STREAM_URL = '/api/camera/stream';

	let analysis = $state('No analysis yet.');
	let loading = $state(false);
	let paused = $state(false);
	let streamSrc = $state(STREAM_URL);

	function toggleProvider() {
		const next = $visionProvider === 'gemini' ? 'mlx' : 'gemini';
		visionProvider.set(next);
		setVisionProvider(next);
	}

	async function togglePause() {
		if (paused) {
			await fetch('/api/camera/resume', { method: 'POST' });
			streamSrc = STREAM_URL;
		} else {
			await fetch('/api/camera/pause', { method: 'POST' });
			streamSrc = '';
		}
		paused = !paused;
	}

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
		<div class="flex items-center gap-2">
			<button
				onclick={toggleProvider}
				class="rounded-md border border-[var(--color-border)] px-2 py-1 text-xs font-medium text-[var(--color-text-muted)] hover:bg-[var(--color-border)]"
				title="Switch vision provider"
			>
				{$visionProvider === 'gemini' ? 'Gemini' : 'MLX'}
			</button>
			<button
				onclick={togglePause}
				class="rounded-md border border-[var(--color-border)] px-2 py-1 text-xs font-medium text-[var(--color-text-muted)] hover:bg-[var(--color-border)]"
				title={paused ? 'Resume camera preview' : 'Pause camera preview'}
			>
				{paused ? 'Resume' : 'Pause'}
			</button>
			<button
				onclick={analyze}
				disabled={loading}
				class="rounded-md bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
			>
				{loading ? 'Analyzing...' : 'Capture'}
			</button>
		</div>
	</div>
	{#if streamSrc}
		<img
			src={streamSrc}
			alt="Camera preview"
			class="w-full rounded-b-lg object-cover"
		/>
	{:else}
		<div class="flex h-48 items-center justify-center text-sm text-[var(--color-text-muted)]">
			Preview paused
		</div>
	{/if}
	<div class="p-4 text-sm text-[var(--color-text-muted)]">
		{analysis}
	</div>
</div>
