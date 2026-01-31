<script lang="ts">
	import ChatPanel from '$lib/components/ChatPanel.svelte';
	import VisionPanel from '$lib/components/VisionPanel.svelte';
</script>

<div class="grid h-[calc(100vh-5rem)] grid-cols-1 gap-6 lg:grid-cols-3">
	<div class="lg:col-span-2">
		<ChatPanel />
	</div>
	<div class="flex flex-col gap-6">
		<VisionPanel />
	</div>
</div>
