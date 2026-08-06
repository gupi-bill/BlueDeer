"""BlueDeer 数字生命系统。

让 11 名动物员工升级为与现实时间同步的数字生命体。
"""

from __future__ import annotations

from . import export_generator
from .badger import Badger
from .beaver import Beaver
from .butterfly import Butterfly
from .deer import Deer
from .digital_life_form import ActionState, DigitalLifeForm, LifeStage, SleepDepth
from .environment import Environment
from .evolution_system import EvolutionSystem, get_evolution_system
from .evolution_tracker import EvolutionSnapshot, EvolutionTracker
from .evolution_visualizer import EvolutionVisualizer
from .external_tasks import TASK_TYPES, ExternalTaskSystem, Task
from .fox import Fox
from .hare import Hare
from .hedgehog import Hedgehog
from .kite import Kite
from .lark import Lark
from .memory_archive import MemoryArchive
from .naming import NamingSystem
from .observer import Observer

# commit 40：新手引导 + 进化突变 + 对外分享
from .onboarding import OnboardingManager, get_onboarding_manager
from .raven import Raven
from .recruit_system import RecruitSystem, SpeciesState
from .share_manager import ShareManager, get_share_manager
from .squirrel import Squirrel
from .storyteller import Storyteller

__all__ = [
    "TASK_TYPES",
    "ActionState",
    "Badger",
    "Beaver",
    "Butterfly",
    "Deer",
    "DigitalLifeForm",
    "Environment",
    "EvolutionSnapshot",
    "EvolutionSystem",
    "EvolutionTracker",
    "EvolutionVisualizer",
    "ExternalTaskSystem",
    "Fox",
    "Hare",
    "Hedgehog",
    "Kite",
    "Lark",
    "LifeStage",
    "MemoryArchive",
    "NamingSystem",
    "Observer",
    "OnboardingManager",
    "Raven",
    "RecruitSystem",
    "ShareManager",
    "SleepDepth",
    "SpeciesState",
    "Squirrel",
    "Storyteller",
    "Task",
    "export_generator",
    "get_evolution_system",
    "get_onboarding_manager",
    "get_share_manager",
]
