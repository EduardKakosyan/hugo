<script lang="ts">
	import { latestFrame, videoConnected } from '$lib/stores/videoStore';
	import { simFrame, simConnected } from '$lib/stores/simulatorStore';

	const frame = $derived($latestFrame ?? $simFrame);
	const isLive = $derived($videoConnected);
	const isSim = $derived(!$videoConnected && $simConnected);
	const badgeText = $derived(isLive ? 'Live' : isSim ? 'Simulator' : 'Offline');
	const badgeBg = $derived(
		isLive
			? 'bg-green-900 text-green-300'
			: isSim
				? 'bg-blue-900 text-blue-300'
				: 'bg-red-900 text-red-300'
	);
	const dotBg = $derived(isLive ? 'bg-green-400' : isSim ? 'bg-blue-400' : 'bg-red-400');
</script>

<div class="relative rounded-lg overflow-hidden bg-gray-900 aspect-video">
	{#if frame}
		<img src={frame} alt="Robot camera feed" class="w-full h-full object-cover" />
	{:else}
		<div class="flex items-center justify-center h-full text-gray-500">
			<div class="text-center">
				<svg class="mx-auto h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
					/>
				</svg>
				<p>No video feed</p>
			</div>
		</div>
	{/if}
	<div class="absolute top-2 right-2">
		<span
			class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium {badgeBg}"
		>
			<span class="h-1.5 w-1.5 rounded-full {dotBg}"></span>
			{badgeText}
		</span>
	</div>
</div>
