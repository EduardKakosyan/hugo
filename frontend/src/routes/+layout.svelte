<script lang="ts">
	import '../app.css';
	import StatusBar from '$lib/components/StatusBar.svelte';
	import { fetchStatus } from '$lib/stores/statusStore';
	import { connectWs, disconnectWs } from '$lib/stores/chatStore';
	import { onMount } from 'svelte';

	let { children } = $props();

	onMount(() => {
		fetchStatus();
		connectWs();
		const interval = setInterval(fetchStatus, 10000);
		return () => {
			clearInterval(interval);
			disconnectWs();
		};
	});
</script>

<svelte:head>
	<title>HUGO</title>
</svelte:head>

<div class="flex min-h-screen flex-col bg-[var(--color-bg)] text-[var(--color-text)]">
	<header class="flex items-center justify-between border-b border-[var(--color-border)] px-6 py-3">
		<h1 class="text-lg font-bold">HUGO</h1>
		<div class="flex items-center gap-4">
			<StatusBar />
			<a href="/settings" class="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)]">
				Settings
			</a>
		</div>
	</header>
	<main class="flex-1 p-6">
		{@render children()}
	</main>
</div>
