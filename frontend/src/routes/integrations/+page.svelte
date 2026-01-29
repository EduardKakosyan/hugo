<script lang="ts">
	import { onMount } from 'svelte';
	import { settings } from '$lib/stores/settingsStore';
	import type { IntegrationInfo } from '$lib/types';

	let integrations: IntegrationInfo[] = $state([]);
	let configuring: string | null = $state(null);
	let configValues: Record<string, string> = $state({});
	let saveStatus: string = $state('');

	onMount(async () => {
		try {
			const resp = await fetch(`${$settings.backendUrl}/api/integrations`);
			if (resp.ok) {
				integrations = await resp.json();
			}
		} catch {
			// backend not reachable
		}
	});

	async function configure(name: string) {
		try {
			const resp = await fetch(`${$settings.backendUrl}/api/integrations/${name}/configure`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ config: configValues })
			});
			const result = await resp.json();
			saveStatus = result.success ? 'Configured successfully' : 'Configuration failed';
			configuring = null;

			// Refresh list
			const listResp = await fetch(`${$settings.backendUrl}/api/integrations`);
			if (listResp.ok) {
				integrations = await listResp.json();
			}
		} catch {
			saveStatus = 'Error connecting to backend';
		}
	}
</script>

<svelte:head>
	<title>HUGO — Integrations</title>
</svelte:head>

<div class="space-y-6">
	<div>
		<h1 class="text-2xl font-bold text-white">Integrations</h1>
		<p class="mt-1 text-sm text-gray-400">Manage API integrations for your assistant.</p>
	</div>

	{#if saveStatus}
		<div class="rounded-lg bg-gray-800 px-4 py-3 text-sm text-gray-300">
			{saveStatus}
		</div>
	{/if}

	<div class="grid gap-4">
		{#each integrations as integration}
			<div class="rounded-lg bg-gray-900 border border-gray-800 p-4">
				<div class="flex items-center justify-between">
					<div>
						<h3 class="font-medium text-white capitalize">{integration.name}</h3>
						<p class="text-sm text-gray-400 mt-0.5">{integration.description}</p>
					</div>
					<div class="flex items-center gap-3">
						<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium
							{integration.active ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}">
							<span class="h-1.5 w-1.5 rounded-full
								{integration.active ? 'bg-green-400' : 'bg-gray-500'}"></span>
							{integration.active ? 'Active' : 'Inactive'}
						</span>
						<button
							onclick={() => { configuring = integration.name; configValues = {}; }}
							class="text-sm text-blue-400 hover:text-blue-300"
						>
							Configure
						</button>
					</div>
				</div>

				{#if configuring === integration.name}
					<div class="mt-4 pt-4 border-t border-gray-800 space-y-3">
						{#if integration.name === 'outlook'}
							<input type="text" placeholder="Client ID" bind:value={configValues.client_id}
								class="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200" />
							<input type="password" placeholder="Client Secret" bind:value={configValues.client_secret}
								class="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200" />
							<input type="text" placeholder="Tenant ID" bind:value={configValues.tenant_id}
								class="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200" />
						{:else if integration.name === 'calendar'}
							<textarea placeholder="Google Calendar Credentials JSON" bind:value={configValues.credentials_json}
								rows="4"
								class="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200"></textarea>
						{:else if integration.name === 'obsidian'}
							<input type="password" placeholder="API Key" bind:value={configValues.api_key}
								class="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200" />
							<input type="text" placeholder="Host (http://localhost:27124)" bind:value={configValues.host}
								class="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-200" />
						{/if}
						<div class="flex gap-2">
							<button onclick={() => configure(integration.name)}
								class="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700">
								Save
							</button>
							<button onclick={() => { configuring = null; }}
								class="rounded bg-gray-700 px-3 py-1.5 text-sm font-medium text-gray-300 hover:bg-gray-600">
								Cancel
							</button>
						</div>
					</div>
				{/if}
			</div>
		{:else}
			<div class="text-center py-8 text-gray-500">
				<p>No integrations available. Is the backend running?</p>
			</div>
		{/each}
	</div>
</div>
