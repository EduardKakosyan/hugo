<script lang="ts">
	import { settings } from '$lib/stores/settingsStore';

	let saveStatus: string = $state('');

	const providers = [
		{ value: 'gemini/gemini-2.5-flash', label: 'Google Gemini 2.5 Flash' },
		{ value: 'openai/gpt-4o', label: 'OpenAI GPT-4o' },
		{ value: 'anthropic/claude-sonnet-4-20250514', label: 'Anthropic Claude Sonnet' },
		{ value: 'huggingface/mistralai/Ministral-3-14B-Reasoning-2512', label: 'HuggingFace Ministral' },
		{ value: 'ollama/llama3.1', label: 'Ollama (Local)' }
	];

	async function switchProvider() {
		try {
			const resp = await fetch(`${$settings.backendUrl}/api/settings/provider`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ provider: $settings.llmProvider })
			});
			if (resp.ok) {
				saveStatus = 'Provider updated';
			}
		} catch {
			saveStatus = 'Error connecting to backend';
		}
	}

	async function switchVoice() {
		try {
			const resp = await fetch(`${$settings.backendUrl}/api/settings/voice`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ engine: $settings.voiceEngine })
			});
			if (resp.ok) {
				saveStatus = 'Voice engine updated';
			}
		} catch {
			saveStatus = 'Error connecting to backend';
		}
	}
</script>

<svelte:head>
	<title>HUGO — Settings</title>
</svelte:head>

<div class="space-y-8 max-w-2xl">
	<div>
		<h1 class="text-2xl font-bold text-white">Settings</h1>
		<p class="mt-1 text-sm text-gray-400">Configure LLM provider, voice engine, and robot connection.</p>
	</div>

	{#if saveStatus}
		<div class="rounded-lg bg-gray-800 px-4 py-3 text-sm text-gray-300">
			{saveStatus}
		</div>
	{/if}

	<!-- LLM Provider -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold text-white">LLM Provider</h2>
		<div class="space-y-3">
			<label class="block">
				<span class="text-sm text-gray-400">Provider</span>
				<select bind:value={$settings.llmProvider}
					class="mt-1 block w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200">
					{#each providers as p}
						<option value={p.value}>{p.label}</option>
					{/each}
				</select>
			</label>
			<button onclick={switchProvider}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
				Apply Provider
			</button>
		</div>
	</section>

	<!-- Voice Engine -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold text-white">Voice Engine</h2>
		<div class="space-y-3">
			<label class="block">
				<span class="text-sm text-gray-400">Engine</span>
				<select bind:value={$settings.voiceEngine}
					class="mt-1 block w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200">
					<option value="personaplex">PersonaPlex (GPU required)</option>
					<option value="fallback">Cloud Fallback (OpenAI)</option>
				</select>
			</label>
			<button onclick={switchVoice}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
				Apply Voice Engine
			</button>
		</div>
	</section>

	<!-- Robot Connection -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold text-white">Robot Connection</h2>
		<div class="grid grid-cols-2 gap-3">
			<label class="block">
				<span class="text-sm text-gray-400">Host</span>
				<input type="text" bind:value={$settings.robotHost}
					class="mt-1 block w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200" />
			</label>
			<label class="block">
				<span class="text-sm text-gray-400">Port</span>
				<input type="number" bind:value={$settings.robotPort}
					class="mt-1 block w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200" />
			</label>
		</div>
		<label class="flex items-center gap-2">
			<input type="checkbox" bind:checked={$settings.simulation}
				class="rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500" />
			<span class="text-sm text-gray-400">Simulation mode</span>
		</label>
	</section>

	<!-- Backend Connection -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold text-white">Backend Connection</h2>
		<div class="space-y-3">
			<label class="block">
				<span class="text-sm text-gray-400">Backend URL</span>
				<input type="text" bind:value={$settings.backendUrl}
					class="mt-1 block w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200" />
			</label>
			<label class="block">
				<span class="text-sm text-gray-400">WebSocket URL</span>
				<input type="text" bind:value={$settings.wsUrl}
					class="mt-1 block w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200" />
			</label>
		</div>
	</section>
</div>
