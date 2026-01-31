<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'dompurify';
	import {
		messages,
		isLoading,
		sendChat,
		voiceActive,
		toggleVoice,
		wsConnected,
		clearChat,
		resetSession
	} from '$lib/stores/chatStore';

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

	function renderMarkdown(content: string): string {
		const raw = marked.parse(content, { async: false }) as string;
		return DOMPurify.sanitize(raw);
	}

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		const msg = input.trim();
		if (!msg) return;
		input = '';
		sendChat(msg);
	}
</script>

<div class="flex h-full flex-col rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]">
	<div class="border-b border-[var(--color-border)] px-4 py-2 flex items-center justify-between">
		<span class="text-sm font-medium text-[var(--color-text)]">Chat</span>
		<div class="flex gap-2">
			<button
				type="button"
				onclick={() => clearChat()}
				class="rounded-md px-2 py-1 text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors"
			>
				Clear Chat
			</button>
			<button
				type="button"
				onclick={() => resetSession()}
				class="rounded-md px-2 py-1 text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors"
			>
				Reset Session
			</button>
		</div>
	</div>

	<div bind:this={messagesContainer} class="flex-1 overflow-y-auto p-4 space-y-3">
		{#each $messages as msg (msg.id)}
			<div class="flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
				<div class="flex items-start gap-1.5 max-w-[80%]">
					{#if msg.source === 'voice' && msg.role === 'user'}
						<svg class="mt-2 shrink-0 text-[var(--color-text-muted)]" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
							<path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
							<line x1="12" x2="12" y1="19" y2="22"/>
						</svg>
					{/if}
					<div
						class="rounded-lg px-3 py-2 text-sm min-w-0 break-words {msg.role === 'user'
							? 'bg-[var(--color-accent)] text-white whitespace-pre-wrap'
							: 'bg-[var(--color-border)] text-[var(--color-text)] markdown-content'}"
					>
						{#if msg.role === 'assistant'}
							{@html renderMarkdown(msg.content)}{#if msg.streaming}<span class="inline-block w-1.5 h-4 bg-[var(--color-text-muted)] ml-0.5 animate-pulse"></span>{/if}
						{:else}
							{msg.content}{#if msg.streaming}<span class="inline-block w-1.5 h-4 bg-[var(--color-text-muted)] ml-0.5 animate-pulse"></span>{/if}
						{/if}
					</div>
					{#if msg.source === 'voice' && msg.role === 'assistant'}
						<svg class="mt-2 shrink-0 text-[var(--color-text-muted)]" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
							<path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
							<line x1="12" x2="12" y1="19" y2="22"/>
						</svg>
					{/if}
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

<style>
	:global(.markdown-content p) {
		margin-bottom: 0.5em;
	}
	:global(.markdown-content p:last-child) {
		margin-bottom: 0;
	}
	:global(.markdown-content code) {
		background: rgba(0, 0, 0, 0.15);
		border-radius: 0.25rem;
		padding: 0.1em 0.3em;
		font-size: 0.875em;
	}
	:global(.markdown-content pre) {
		background: rgba(0, 0, 0, 0.15);
		border-radius: 0.375rem;
		padding: 0.75em;
		overflow-x: auto;
		margin: 0.5em 0;
	}
	:global(.markdown-content pre code) {
		background: none;
		padding: 0;
	}
	:global(.markdown-content ul),
	:global(.markdown-content ol) {
		padding-left: 1.5em;
		margin: 0.5em 0;
	}
	:global(.markdown-content li) {
		margin: 0.25em 0;
	}
	:global(.markdown-content strong) {
		font-weight: 600;
	}
	:global(.markdown-content h1),
	:global(.markdown-content h2),
	:global(.markdown-content h3) {
		font-weight: 600;
		margin: 0.5em 0 0.25em;
	}
	:global(.markdown-content blockquote) {
		border-left: 3px solid rgba(255, 255, 255, 0.3);
		padding-left: 0.75em;
		margin: 0.5em 0;
		opacity: 0.85;
	}
</style>
