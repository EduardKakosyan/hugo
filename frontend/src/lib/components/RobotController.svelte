<script lang="ts">
	import { settings } from '$lib/stores/settingsStore';
	import { robotState } from '$lib/stores/robotStore';

	let roll = $state(0);
	let pitch = $state(0);
	let yaw = $state(0);
	let leftAntenna = $state(0);
	let rightAntenna = $state(0);
	let duration = $state(0.5);
	let sending = $state(false);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	// Sync sliders from telemetry
	$effect(() => {
		const head = $robotState.head;
		if (head && !sending) {
			roll = Math.round(head.roll);
			pitch = Math.round(head.pitch);
			yaw = Math.round(head.yaw);
		}
	});

	async function sendMove() {
		sending = true;
		try {
			await fetch(`${$settings.backendUrl}/api/robot/move`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					roll,
					pitch,
					yaw,
					left_antenna: leftAntenna,
					right_antenna: rightAntenna,
					duration
				})
			});
		} catch {
			// ignore
		} finally {
			sending = false;
		}
	}

	function debouncedMove() {
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(sendMove, 150);
	}

	function applyPreset(r: number, p: number, y: number, la: number, ra: number) {
		roll = r;
		pitch = p;
		yaw = y;
		leftAntenna = la;
		rightAntenna = ra;
		sendMove();
	}

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

<div class="rounded-lg bg-gray-800 p-4 space-y-4">
	<h3 class="text-sm font-semibold text-gray-300 uppercase tracking-wide">Robot Control</h3>

	<!-- Head Sliders -->
	<div class="space-y-2">
		<label class="flex items-center justify-between text-xs text-gray-400">
			<span>Roll</span>
			<span class="tabular-nums">{roll}&deg;</span>
		</label>
		<input
			type="range"
			min="-45"
			max="45"
			bind:value={roll}
			oninput={debouncedMove}
			class="w-full accent-blue-500"
		/>

		<label class="flex items-center justify-between text-xs text-gray-400">
			<span>Pitch</span>
			<span class="tabular-nums">{pitch}&deg;</span>
		</label>
		<input
			type="range"
			min="-45"
			max="45"
			bind:value={pitch}
			oninput={debouncedMove}
			class="w-full accent-blue-500"
		/>

		<label class="flex items-center justify-between text-xs text-gray-400">
			<span>Yaw</span>
			<span class="tabular-nums">{yaw}&deg;</span>
		</label>
		<input
			type="range"
			min="-60"
			max="60"
			bind:value={yaw}
			oninput={debouncedMove}
			class="w-full accent-blue-500"
		/>
	</div>

	<!-- Antenna Sliders -->
	<div class="space-y-2">
		<label class="flex items-center justify-between text-xs text-gray-400">
			<span>Left Antenna</span>
			<span class="tabular-nums">{leftAntenna}&deg;</span>
		</label>
		<input
			type="range"
			min="0"
			max="150"
			bind:value={leftAntenna}
			oninput={debouncedMove}
			class="w-full accent-purple-500"
		/>

		<label class="flex items-center justify-between text-xs text-gray-400">
			<span>Right Antenna</span>
			<span class="tabular-nums">{rightAntenna}&deg;</span>
		</label>
		<input
			type="range"
			min="0"
			max="150"
			bind:value={rightAntenna}
			oninput={debouncedMove}
			class="w-full accent-purple-500"
		/>
	</div>

	<!-- Duration -->
	<div class="space-y-1">
		<label class="flex items-center justify-between text-xs text-gray-400">
			<span>Duration</span>
			<span class="tabular-nums">{duration.toFixed(1)}s</span>
		</label>
		<input
			type="range"
			min="0.1"
			max="2.0"
			step="0.1"
			bind:value={duration}
			class="w-full accent-gray-500"
		/>
	</div>

	<!-- Preset Poses -->
	<div>
		<p class="text-xs text-gray-500 mb-2">Presets</p>
		<div class="flex flex-wrap gap-1.5">
			<button
				onclick={() => applyPreset(0, 0, 0, 0, 0)}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Neutral
			</button>
			<button
				onclick={() => applyPreset(0, -30, 0, 0, 0)}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Look Up
			</button>
			<button
				onclick={() => applyPreset(0, 30, 0, 0, 0)}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Look Down
			</button>
			<button
				onclick={() => applyPreset(-30, 0, 0, 0, 0)}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Tilt Left
			</button>
			<button
				onclick={() => applyPreset(30, 0, 0, 0, 0)}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Tilt Right
			</button>
			<button
				onclick={() => applyPreset(0, -10, 0, 140, 140)}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Happy
			</button>
		</div>
	</div>

	<!-- Quick Actions -->
	<div>
		<p class="text-xs text-gray-500 mb-2">Quick Actions</p>
		<div class="flex flex-wrap gap-1.5">
			<button
				onclick={() => sendAction('Wave hello!')}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Wave
			</button>
			<button
				onclick={() => sendAction('Look at the camera.')}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Look at Camera
			</button>
			<button
				onclick={() => sendAction('Reset to neutral position.')}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Reset Position
			</button>
			<button
				onclick={() => sendAction('What do you see right now?')}
				class="rounded bg-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-600 transition-colors"
			>
				Analyze Scene
			</button>
		</div>
	</div>
</div>
