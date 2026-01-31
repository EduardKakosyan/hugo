<script lang="ts">
	import { messages, isLoading, sendChat } from '$lib/stores/chatStore';

	let input = $state('');
	let messagesContainer: HTMLDivElement;

	// Auto-scroll to bottom when messages change
	$effect(() => {
		// Access messages to subscribe
		$messages;
		if (messagesContainer) {
			messagesContainer.scrollTop = messagesContainer.scrollHeight;
		}
	});

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		const msg = input.trim();
		if (!msg) return;
		input = '';
		sendChat(msg);
	}
</script>

<div class="flex h-full flex-col rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]">
	<div class="border-b border-[var(--color-border)] px-4 py-2 text-sm font-medium text-[var(--color-text)]">
		Chat
	</div>

	<div bind:this={messagesContainer} class="flex-1 overflow-y-auto p-4 space-y-3">
		{#each $messages as msg (msg.id)}
			<div class="flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
				<div
					class="max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap {msg.role === 'user'
						? 'bg-[var(--color-accent)] text-white'
						: 'bg-[var(--color-border)] text-[var(--color-text)]'}"
				>
					{msg.content}{#if msg.streaming}<span class="inline-block w-1.5 h-4 bg-[var(--color-text-muted)] ml-0.5 animate-pulse"></span>{/if}
				</div>
			</div>
		{/each}
		{#if $isLoading && !$messages.some((m) => m.streaming)}
			<div class="flex justify-start">
				<div class="rounded-lg bg-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text-muted)]">
					Thinking...
				</div>
			</div>
		{/if}
	</div>

	<form onsubmit={handleSubmit} class="border-t border-[var(--color-border)] p-3 flex gap-2">
		<input
			type="text"
			bind:value={input}
			placeholder="Type a message..."
			class="flex-1 rounded-md bg-[var(--color-bg)] border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] outline-none focus:border-[var(--color-accent)]"
		/>
		<button
			type="submit"
			disabled={$isLoading}
			class="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
		>
			Send
		</button>
	</form>
</div>
