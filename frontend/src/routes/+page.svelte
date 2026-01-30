<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import VideoFeed from '$lib/components/VideoFeed.svelte';
	import SimulatorView from '$lib/components/SimulatorView.svelte';
	import ChatPanel from '$lib/components/ChatPanel.svelte';
	import StatusBar from '$lib/components/StatusBar.svelte';
	import RobotController from '$lib/components/RobotController.svelte';
	import { connectTelemetry, disconnectTelemetry } from '$lib/stores/robotStore';
	import { connectChat, disconnectChat } from '$lib/stores/chatStore';
	import { connectVideo, disconnectVideo } from '$lib/stores/videoStore';
	import { connectSimulator, disconnectSimulator } from '$lib/stores/simulatorStore';
	import { settings } from '$lib/stores/settingsStore';
	import type { StatusResponse } from '$lib/types';

	let status: StatusResponse | null = $state(null);
	let activeTab: 'camera' | 'simulator' = $state('camera');

	onMount(async () => {
		const wsUrl = $settings.wsUrl;
		connectTelemetry(wsUrl);
		connectChat(wsUrl);
		connectVideo(wsUrl);
		connectSimulator($settings.wsUrl);

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
		disconnectSimulator();
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
			<!-- Video / Simulator tabs -->
			<div>
				<div class="flex gap-1 mb-2">
					<button
						onclick={() => (activeTab = 'camera')}
						class="px-3 py-1.5 rounded text-xs font-medium transition-colors {activeTab === 'camera'
							? 'bg-blue-600 text-white'
							: 'bg-gray-700 text-gray-400 hover:bg-gray-600'}"
					>
						Camera
					</button>
					<button
						onclick={() => (activeTab = 'simulator')}
						class="px-3 py-1.5 rounded text-xs font-medium transition-colors {activeTab ===
						'simulator'
							? 'bg-blue-600 text-white'
							: 'bg-gray-700 text-gray-400 hover:bg-gray-600'}"
					>
						Simulator
					</button>
				</div>

				{#if activeTab === 'camera'}
					<VideoFeed />
				{:else}
					<SimulatorView />
				{/if}
			</div>

			<RobotController />
		</div>

		<div class="h-[calc(100vh-12rem)]">
			<ChatPanel />
		</div>
	</div>
</div>
