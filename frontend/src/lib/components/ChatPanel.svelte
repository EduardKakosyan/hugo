<script lang="ts">
	import { messages, isLoading, sendChat, voiceActive, toggleVoice, wsConnected } from '$lib/stores/chatStore';

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
		<button
			type="button"
			onclick={toggleVoice}
			disabled={!$wsConnected}
			class="rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50 {$voiceActive
				? 'bg-red-500 text-white hover:bg-red-600'
				: 'bg-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-border)]/80'}"
			title={$voiceActive ? 'Stop listening' : 'Start listening'}
		>
			<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				{#if $voiceActive}
					<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
					<path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
					<line x1="12" x2="12" y1="19" y2="22"/>
				{:else}
					<line x1="2" x2="22" y1="2" y2="22"/>
					<path d="M18.89 13.23A7.12 7.12 0 0 0 19 12v-2"/>
					<path d="M5 10v2a7 7 0 0 0 12 0"/>
					<path d="M15 9.34V5a3 3 0 0 0-5.68-1.33"/>
					<path d="M9 9v3a3 3 0 0 0 5.12 2.12"/>
					<line x1="12" x2="12" y1="19" y2="22"/>
				{/if}
			</svg>
		</button>
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
