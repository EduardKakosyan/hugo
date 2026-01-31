<script lang="ts">
	import { serviceStatus, connected } from '$lib/stores/statusStore';

	function statusColor(s: string): string {
		if (s === 'ok' || s === 'configured') return 'bg-green-500';
		if (s === 'unknown' || s === 'not_loaded' || s === 'not_configured') return 'bg-yellow-500';
		return 'bg-red-500';
	}
</script>

<div class="flex items-center gap-4 rounded-lg bg-[var(--color-surface)] px-4 py-2 text-sm">
	<div class="flex items-center gap-1.5">
		<span class="h-2 w-2 rounded-full {$connected ? 'bg-green-500' : 'bg-red-500'}"></span>
		<span class="text-[var(--color-text-muted)]">WS</span>
	</div>
	<div class="flex items-center gap-1.5">
		<span class="h-2 w-2 rounded-full {statusColor($serviceStatus.voice)}"></span>
		<span class="text-[var(--color-text-muted)]">Voice</span>
	</div>
	<div class="flex items-center gap-1.5">
		<span class="h-2 w-2 rounded-full {statusColor($serviceStatus.vision)}"></span>
		<span class="text-[var(--color-text-muted)]">Vision</span>
	</div>
	<div class="flex items-center gap-1.5">
		<span class="h-2 w-2 rounded-full {statusColor($serviceStatus.openclaw)}"></span>
		<span class="text-[var(--color-text-muted)]">OpenClaw</span>
	</div>
</div>
