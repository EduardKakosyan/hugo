<script lang="ts">
	import { settings } from '$lib/stores/settingsStore';

	const simUrl = $derived(`http://${$settings.robotHost}:${$settings.robotPort}`);
	let loaded = $state(false);
	let error = $state(false);
</script>

<div class="relative rounded-lg overflow-hidden bg-gray-900 aspect-video">
	{#if !error}
		<iframe
			src={simUrl}
			title="Reachy Mini Simulator"
			class="w-full h-full border-0"
			class:opacity-0={!loaded}
			onload={() => (loaded = true)}
			onerror={() => (error = true)}
			sandbox="allow-scripts allow-same-origin"
		></iframe>
		{#if !loaded}
			<div class="absolute inset-0 flex items-center justify-center text-gray-500">
				<p>Loading simulator...</p>
			</div>
		{/if}
	{:else}
		<div class="flex items-center justify-center h-full text-gray-500">
			<div class="text-center">
				<svg class="mx-auto h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
					/>
				</svg>
				<p>Simulator unavailable</p>
				<p class="text-xs mt-1">Check that the daemon is running on port {$settings.robotPort}</p>
			</div>
		</div>
	{/if}
	<div class="absolute top-2 right-2">
		<span
			class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium {loaded &&
			!error
				? 'bg-green-900 text-green-300'
				: 'bg-gray-700 text-gray-400'}"
		>
			<span class="h-1.5 w-1.5 rounded-full {loaded && !error ? 'bg-green-400' : 'bg-gray-500'}"
			></span>
			3D View
		</span>
	</div>
</div>
