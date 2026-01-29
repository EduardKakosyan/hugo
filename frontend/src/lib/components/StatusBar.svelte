<script lang="ts">
	import { robotState } from '$lib/stores/robotStore';

	interface Props {
		agentModel?: string;
		voiceEngine?: string;
	}

	let { agentModel = 'unknown', voiceEngine = 'unknown' }: Props = $props();
</script>

<div class="flex items-center gap-4 px-4 py-2 bg-gray-800 rounded-lg text-xs text-gray-400">
	<div class="flex items-center gap-1.5">
		<span class="h-2 w-2 rounded-full {$robotState.connected ? 'bg-green-400' : 'bg-red-400'}"></span>
		<span>Robot: {$robotState.connected ? 'Connected' : 'Disconnected'}</span>
	</div>

	{#if $robotState.head}
		<div class="hidden sm:flex items-center gap-2 text-gray-500">
			<span>R: {$robotState.head.roll.toFixed(1)}°</span>
			<span>P: {$robotState.head.pitch.toFixed(1)}°</span>
			<span>Y: {$robotState.head.yaw.toFixed(1)}°</span>
		</div>
	{/if}

	<div class="ml-auto flex items-center gap-3">
		<span>LLM: {agentModel}</span>
		<span>Voice: {voiceEngine}</span>
	</div>
</div>
