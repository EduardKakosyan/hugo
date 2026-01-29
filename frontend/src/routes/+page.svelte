<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import VideoFeed from '$lib/components/VideoFeed.svelte';
	import ChatPanel from '$lib/components/ChatPanel.svelte';
	import StatusBar from '$lib/components/StatusBar.svelte';
	import QuickActions from '$lib/components/QuickActions.svelte';
	import { connectTelemetry, disconnectTelemetry } from '$lib/stores/robotStore';
	import { connectChat, disconnectChat } from '$lib/stores/chatStore';
	import { connectVideo, disconnectVideo } from '$lib/stores/videoStore';
	import { settings } from '$lib/stores/settingsStore';
	import type { StatusResponse } from '$lib/types';

	let status: StatusResponse | null = $state(null);

	onMount(async () => {
		const wsUrl = $settings.wsUrl;
		connectTelemetry(wsUrl);
		connectChat(wsUrl);
		connectVideo(wsUrl);

		try {
			const resp = await fetch(`${$settings.backendUrl}/api/status`);
			if (resp.ok) {
				status = await resp.json();
			}
		} catch {
			// backend not reachable
		}
	});

	onDestroy(() => {
		disconnectTelemetry();
		disconnectChat();
		disconnectVideo();
	});
</script>

<svelte:head>
	<title>HUGO — Dashboard</title>
</svelte:head>

<div class="space-y-4">
	<StatusBar
		agentModel={status?.agent_model ?? 'loading...'}
		voiceEngine={status?.voice_engine ?? 'loading...'}
	/>

	<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
		<div class="space-y-4">
			<VideoFeed />
			<QuickActions />
		</div>

		<div class="h-[calc(100vh-12rem)]">
			<ChatPanel />
		</div>
	</div>
</div>
