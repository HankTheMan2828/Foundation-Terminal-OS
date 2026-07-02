"""engine.py has no curses window handling — just key->direction mapping and
the step accumulator that decouples game speed from poll rate."""
import curses

from foundation_arcade import engine


def test_direction_for_arrows_and_wasd_and_vim_agree():
    assert engine.direction_for(curses.KEY_UP) == engine.DIR_UP
    assert engine.direction_for(ord("w")) == engine.DIR_UP
    assert engine.direction_for(ord("k")) == engine.DIR_UP
    assert engine.direction_for(ord("j")) == engine.DIR_DOWN
    assert engine.direction_for(ord("a")) == engine.DIR_LEFT
    assert engine.direction_for(ord("d")) == engine.DIR_RIGHT


def test_direction_for_unmapped_key_is_none():
    assert engine.direction_for(ord("z")) is None


def test_step_accumulator_emits_whole_steps_only():
    acc = engine.StepAccumulator(step_ms=100)
    assert acc.advance(50) == 0
    assert acc.advance(60) == 1     # 110 acc'd, one step, 10ms carried over
    assert acc.advance(90) == 1     # 100 acc'd exactly


def test_step_accumulator_catches_up_after_lag():
    acc = engine.StepAccumulator(step_ms=100)
    assert acc.advance(350) == 3


def test_set_step_ms_changes_future_steps():
    acc = engine.StepAccumulator(step_ms=100)
    acc.set_step_ms(50)
    assert acc.advance(120) == 2
