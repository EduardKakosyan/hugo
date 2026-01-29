<script lang="ts">
	import '../app.css';
	import type { Snippet } from 'svelte';

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();
</script>

<div class="min-h-screen bg-gray-950 text-gray-100">
	<nav class="border-b border-gray-800 bg-gray-900">
		<div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
			<div class="flex h-14 items-center justify-between">
				<div class="flex items-center gap-6">
					<a href="/" class="text-lg font-bold text-white">HUGO</a>
					<div class="flex gap-4">
						<a href="/" class="text-sm text-gray-400 hover:text-white transition-colors">Dashboard</a>
						<a href="/integrations" class="text-sm text-gray-400 hover:text-white transition-colors">Integrations</a>
						<a href="/settings" class="text-sm text-gray-400 hover:text-white transition-colors">Settings</a>
					</div>
				</div>
			</div>
		</div>
	</nav>

	<main class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6">
		{@render children()}
	</main>
</div>
