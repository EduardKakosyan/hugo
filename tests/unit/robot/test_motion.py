"""MotionManager behavior against a fake robot (VEN-57): asserts the
externally visible stream of motor/toggle commands per conversation state,
plus the hardware-safety rules (deadband, slew) as pure functions. Never
inspects manager internals beyond the published `state`."""

import asyncio
from collections.abc import Callable

from hugo.robot.motion import (
    ATTENTIVE_ANTENNAS,
    ATTENTIVE_HEAD,
    MAX_ANTENNA_PER_TICK_RAD,
    MAX_ROTATION_PER_TICK_RAD,
    NEUTRAL_ANTENNAS,
    NEUTRAL_HEAD,
    NEUTRAL_RETURN_S,
    PERK_DURATION_S,
    MotionManager,
    antennas_if_changed,
    head_if_changed,
    slew_limited_antennas,
    slew_limited_head,
)
from hugo.robot.motion_io import HeadOffsets

Call = tuple[object, ...]


class FakeRobotMotion:
    def __init__(self) -> None:
        self.calls: list[Call] = []

    def targets(self) -> list[Call]:
        return [c for c in self.calls if c[0] == "set_target"]

    async def set_motion_target(
        self, head: HeadOffsets | None, antennas: tuple[float, float] | None
    ) -> None:
        self.calls.append(("set_target", head, antennas))

    async def goto(
        self,
        head: HeadOffsets | None,
        antennas: tuple[float, float] | None,
        duration_s: float,
    ) -> None:
        self.calls.append(("goto", head, antennas, duration_s))

    async def hold_current_head_pose(self) -> None:
        self.calls.append(("hold_current",))

    async def enable_wobbling(self) -> None:
        self.calls.append(("enable_wobbling",))

    async def disable_wobbling(self) -> None:
        self.calls.append(("disable_wobbling",))

    async def set_head_tracking(self, weight: float) -> None:
        self.calls.append(("tracking", weight))

    async def stop_head_tracking(self) -> None:
        self.calls.append(("stop_tracking",))


async def _wait_until(predicate: Callable[[], bool], timeout_s: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0.005)


async def _settled_call_count(robot: FakeRobotMotion, ticks: float = 0.1) -> int:
    """Snapshot the call count, wait several ticks, return the new count."""
    before = len(robot.calls)
    await asyncio.sleep(ticks)
    return len(robot.calls) - before


def _build(
    use_wobbler: bool = False, use_head_tracking: bool = False
) -> tuple[MotionManager, FakeRobotMotion]:
    robot = FakeRobotMotion()
    manager = MotionManager(
        robot, tick_s=0.005, use_wobbler=use_wobbler, use_head_tracking=use_head_tracking
    )
    return manager, robot


async def test_default_start_touches_nothing_and_idles_perfectly_still() -> None:
    manager, robot = _build()
    await manager.start()
    try:
        # Wobbler and tracking are opt-in (both produced wild motion on
        # this hardware), and idle means STILL: zero motor traffic until
        # a conversation.
        assert await _settled_call_count(robot) == 0
        assert robot.calls == []
    finally:
        await manager.stop()


async def test_wobbler_is_enabled_only_when_opted_in() -> None:
    manager, robot = _build(use_wobbler=True)
    await manager.start()
    try:
        assert robot.calls[0] == ("enable_wobbling",)
    finally:
        await manager.stop()


async def test_stop_disables_wobbling_and_tracking() -> None:
    manager, robot = _build()
    await manager.start()
    await manager.stop()
    assert ("disable_wobbling",) in robot.calls
    assert ("stop_tracking",) in robot.calls
    # And the motor writer is really gone: no further targets after stop.
    assert await _settled_call_count(robot) == 0


async def test_wake_perks_then_holds_still_without_tracking() -> None:
    manager, robot = _build()
    await manager.start()
    try:
        manager.cue("wake")
        await _wait_until(lambda: manager.state == "attentive")

        perk = ("goto", ATTENTIVE_HEAD, ATTENTIVE_ANTENNAS, PERK_DURATION_S)
        assert perk in robot.calls
        assert ("tracking", 1.0) not in robot.calls
        # Attentive = stillness: no procedural targets while listening.
        assert await _settled_call_count(robot) == 0
    finally:
        await manager.stop()


async def test_wake_perks_before_handing_the_head_to_tracking() -> None:
    manager, robot = _build(use_head_tracking=True)
    await manager.start()
    try:
        manager.cue("wake")
        await _wait_until(lambda: ("tracking", 1.0) in robot.calls)

        perk_at = robot.calls.index(("goto", ATTENTIVE_HEAD, ATTENTIVE_ANTENNAS, PERK_DURATION_S))
        tracking_at = robot.calls.index(("tracking", 1.0))
        # Perk before tracking: once tracking owns the head, the perk
        # would never show.
        assert perk_at < tracking_at
    finally:
        await manager.stop()


async def test_user_speech_holds_pose_then_pauses_tracking() -> None:
    manager, robot = _build(use_head_tracking=True)
    await manager.start()
    try:
        manager.cue("wake")
        await _wait_until(lambda: manager.state == "attentive")
        manager.cue("user_speech_start")
        await _wait_until(lambda: ("tracking", 0.0) in robot.calls)

        # The anchor must be held BEFORE tracking pauses, or the head
        # snaps back to the stale app target.
        assert robot.calls.index(("hold_current",)) < robot.calls.index(("tracking", 0.0))
        # Frozen while the user speaks: zero motor traffic.
        assert await _settled_call_count(robot) == 0
    finally:
        await manager.stop()


async def test_thinking_sways_one_antenna_and_never_the_head() -> None:
    manager, robot = _build()
    await manager.start()
    try:
        manager.cue("wake")
        await _wait_until(lambda: manager.state == "attentive")
        before = len(robot.targets())
        manager.cue("thinking")
        await _wait_until(lambda: len(robot.targets()) >= before + 2)
        for _, head, antennas in robot.targets()[before:]:
            assert head is None
            assert antennas is not None
    finally:
        await manager.stop()


async def test_speaking_nods_the_head_and_wags_antennas() -> None:
    manager, robot = _build()
    await manager.start()
    try:
        manager.cue("wake")
        await _wait_until(lambda: manager.state == "attentive")
        before = len(robot.targets())
        manager.cue("speaking")
        # With tracking off the head is ours: the gentle nod must show up
        # alongside the wag (our controllable stand-in for the wobbler).
        await _wait_until(lambda: any(head is not None for _, head, _ in robot.targets()[before:]))
        await _wait_until(
            lambda: len({antennas for _, _, antennas in robot.targets()[before:]}) >= 2
        )
    finally:
        await manager.stop()


async def test_speaking_with_tracking_leaves_the_head_anchored() -> None:
    manager, robot = _build(use_head_tracking=True)
    await manager.start()
    try:
        manager.cue("wake")
        await _wait_until(lambda: manager.state == "attentive")
        manager.cue("user_speech_start")
        await _wait_until(lambda: manager.state == "user_speech_hold")
        before = len(robot.targets())
        manager.cue("speaking")
        await _wait_until(lambda: len(robot.targets()) >= before + 2)
        for _, head, _antennas in robot.targets()[before:]:
            # The head stays on the face anchor; only antennas move.
            assert head is None
    finally:
        await manager.stop()


async def test_conversation_end_settles_to_neutral_then_stillness() -> None:
    manager, robot = _build()
    await manager.start()
    try:
        manager.cue("wake")
        await _wait_until(lambda: manager.state == "attentive")
        manager.cue("conversation_end")
        await _wait_until(lambda: manager.state == "idle")

        assert ("goto", NEUTRAL_HEAD, NEUTRAL_ANTENNAS, NEUTRAL_RETURN_S) in robot.calls
        # Settled means settled: no further motor traffic while idle.
        assert await _settled_call_count(robot) == 0
    finally:
        await manager.stop()


async def test_conversation_end_stops_tracking_before_the_neutral_goto() -> None:
    manager, robot = _build(use_head_tracking=True)
    await manager.start()
    try:
        manager.cue("wake")
        await _wait_until(lambda: manager.state == "attentive")
        manager.cue("conversation_end")
        await _wait_until(lambda: manager.state == "idle")

        neutral_goto = ("goto", NEUTRAL_HEAD, NEUTRAL_ANTENNAS, NEUTRAL_RETURN_S)
        # Tracking off before the neutral goto, or the goto's head
        # component is fought by the tracker.
        assert robot.calls.index(("stop_tracking",)) < robot.calls.index(neutral_goto)
    finally:
        await manager.stop()


async def test_robot_errors_do_not_kill_the_motion_task() -> None:
    manager, robot = _build()

    async def explode(head: HeadOffsets | None, antennas: tuple[float, float] | None) -> None:
        robot.calls.append(("set_target", head, antennas))
        raise ConnectionError("daemon hiccup")

    robot.set_motion_target = explode  # type: ignore[method-assign]
    await manager.start()
    try:
        manager.cue("wake")
        await _wait_until(lambda: manager.state == "attentive")
        manager.cue("speaking")
        # Ticks keep coming despite every send failing.
        await _wait_until(lambda: len(robot.targets()) >= 3)
    finally:
        await manager.stop()


def test_head_deadband_suppresses_unchanged_targets() -> None:
    last = HeadOffsets(z_m=0.003)
    assert head_if_changed(last, HeadOffsets(z_m=0.0031)) is None
    assert head_if_changed(last, HeadOffsets(z_m=0.004)) == HeadOffsets(z_m=0.004)
    assert head_if_changed(None, last) == last


def test_antenna_deadband_suppresses_unchanged_targets() -> None:
    last = (-0.17, 0.17)
    assert antennas_if_changed(last, (-0.171, 0.171)) is None
    assert antennas_if_changed(last, (-0.3, 0.3)) == (-0.3, 0.3)
    assert antennas_if_changed(None, last) == last


def test_slew_limit_caps_a_violent_swing() -> None:
    limited = slew_limited_head(HeadOffsets(), HeadOffsets(yaw_rad=1.0))
    assert limited.yaw_rad == MAX_ROTATION_PER_TICK_RAD
    # Unknown last pose: nothing to slew against.
    assert slew_limited_head(None, HeadOffsets(yaw_rad=1.0)) == HeadOffsets(yaw_rad=1.0)


def test_antenna_slew_eases_state_change_snaps() -> None:
    eased = slew_limited_antennas((-0.06, 0.06), (-0.5, 0.06))
    assert eased == (-0.06 - MAX_ANTENNA_PER_TICK_RAD, 0.06)
    assert slew_limited_antennas(None, (-0.5, 0.06)) == (-0.5, 0.06)
