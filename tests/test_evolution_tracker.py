"""EvolutionTracker 进化追踪器测试：世代号与谱系递归查询。"""

from __future__ import annotations

from core.digital_life.evolution_tracker import EvolutionTracker


class FakeLifeForm:
    def __init__(self, species="deer"):
        self.species = species


def make_tracker():
    return EvolutionTracker(environment=None)


def test_initial_generation_no_parents():
    t = make_tracker()
    lf = FakeLifeForm()
    t.record_birth(lf)
    assert t._generation == 1
    assert t._max_generation_per_species["deer"] == 1


def test_second_generation_two_parents():
    t = make_tracker()
    a = FakeLifeForm()
    b = FakeLifeForm()
    t.record_birth(a)
    t.record_birth(b)
    child = FakeLifeForm()
    t.record_birth(child, parents=[a, b])
    assert t._generation == 2
    assert t._get_generation(id(child)) == 2


def test_third_generation_lineage_recursion():
    t = make_tracker()
    a = FakeLifeForm()
    t.record_birth(a)
    child = FakeLifeForm()
    t.record_birth(child, parents=[a])
    grand = FakeLifeForm()
    t.record_birth(grand, parents=[child])
    assert t._get_generation(id(grand)) == 3
    assert t._generation == 3


def test_parents_of_different_generations_take_max_plus_one():
    t = make_tracker()
    a = FakeLifeForm()
    t.record_birth(a)
    b = FakeLifeForm()
    t.record_birth(b)
    child = FakeLifeForm()
    t.record_birth(child, parents=[a, b])
    # a 是初代(1)，child 是第二代(2) → 混合子代应为 3
    mixed = FakeLifeForm()
    t.record_birth(mixed, parents=[a, child])
    assert t._get_generation(id(mixed)) == 3


def test_single_parent():
    t = make_tracker()
    a = FakeLifeForm()
    t.record_birth(a)
    offspring = FakeLifeForm()
    t.record_birth(offspring, parents=[a])
    assert t._get_generation(id(offspring)) == 2


def test_get_generation_edge_cases():
    t = make_tracker()
    assert t._get_generation(None) == 1
    assert t._get_generation(999999) == 1


def test_max_generation_per_species_tracks_max():
    t = make_tracker()
    a = FakeLifeForm("deer")
    t.record_birth(a)
    child = FakeLifeForm("deer")
    t.record_birth(child, parents=[a])
    assert t._max_generation_per_species["deer"] == 2
