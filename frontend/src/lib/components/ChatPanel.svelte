<script lang="ts">
	import { messages, isStreaming, sendMessage } from '$lib/stores/chatStore';

	let input = $state('');

	function handleSend() {
		const text = input.trim();
		if (!text || $isStreaming) return;
		sendMessage(text);
		input = '';
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	}
</script>

<div class="flex flex-col h-full bg-gray-900 rounded-lg">
	<div class="px-4 py-3 border-b border-gray-700">
		<h2 class="text-sm font-semibold text-gray-200">Chat</h2>
	</div>

	<div class="flex-1 overflow-y-auto p-4 space-y-3">
		{#each $messages as msg}
			<div class="flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
				<div class="max-w-[80%] rounded-lg px-3 py-2 text-sm
					{msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-200'}">
					{msg.content}
				</div>
			</div>
		{/each}

		{#if $isStreaming}
			<div class="flex justify-start">
				<div class="bg-gray-700 rounded-lg px-3 py-2 text-sm text-gray-400">
					<span class="animate-pulse">Thinking...</span>
				</div>
			</div>
		{/if}
	</div>

	<div class="p-3 border-t border-gray-700">
		<div class="flex gap-2">
			<input
				type="text"
				bind:value={input}
				onkeydown={handleKeydown}
				placeholder="Type a message..."
				class="flex-1 rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-gray-200
					placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
				disabled={$isStreaming}
			/>
			<button
				onclick={handleSend}
				disabled={$isStreaming || !input.trim()}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white
					hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
			>
				Send
			</button>
		</div>
	</div>
</div>
