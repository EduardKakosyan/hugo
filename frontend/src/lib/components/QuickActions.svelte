<script lang="ts">
	import { settings } from '$lib/stores/settingsStore';

	async function sendAction(action: string) {
		try {
			await fetch(`${$settings.backendUrl}/api/chat`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ message: action })
			});
		} catch {
			// ignore
		}
	}
</script>

<div class="flex flex-wrap gap-2">
	<button
		onclick={() => sendAction('Wave hello!')}
		class="rounded-lg bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300
			hover:bg-gray-600 transition-colors"
	>
		👋 Wave
	</button>
	<button
		onclick={() => sendAction('Look at the camera.')}
		class="rounded-lg bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300
			hover:bg-gray-600 transition-colors"
	>
		📷 Look at Camera
	</button>
	<button
		onclick={() => sendAction('Reset to neutral position.')}
		class="rounded-lg bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300
			hover:bg-gray-600 transition-colors"
	>
		🔄 Reset Position
	</button>
	<button
		onclick={() => sendAction('What do you see right now?')}
		class="rounded-lg bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300
			hover:bg-gray-600 transition-colors"
	>
		👁 Analyze Scene
	</button>
</div>
