from __future__ import annotations

# isort: off
from kvui import GameManager, MDNavigationItemBase

# isort: on
from typing import TYPE_CHECKING, Any

from kivy._clock import ClockEvent
from kivy.clock import Clock
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.layout import Layout
from kivymd.uix.recycleview import MDRecycleView

from .custom_views import (
    DestinyGrid,
    DestinyText,
)

if TYPE_CHECKING:
    from .destiny_client import DestinyContext


class DestinyManager(GameManager):
    base_title = "Destiny for AP version"
    ctx: DestinyContext

    lower_game_grid: GridLayout
    game_view_tab: MDNavigationItemBase


    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def switch_to_tab(self, desired_tab: MDNavigationItemBase) -> None:
        if self.screens.current_tab == desired_tab:
            return
        self.screens.current_tab.active = False
        self.screens.switch_screens(desired_tab)
        desired_tab.active = True

    def switch_to_game_tab(self) -> None:
        self.switch_to_tab(self.game_view_tab)

    def switch_to_regular_tab(self) -> None:
        self.switch_to_tab(self.tabs.children[-1])

    def render(self) -> None:
        pass


    def build(self) -> Layout:
        container = super().build()

        self.lower_game_grid = DestinyGrid()

        self.game_view_tab = self.add_client_tab("Destiny 2", self.lower_game_grid)


        #game_container.add_widget(self.lower_game_grid)

        #game_container.bind(size=self.lower_game_grid.check_resize)

        text = DestinyText()
        #volume_slider = volume_slider_container.ids["volume_slider"]
        #volume_slider.value = self.sound_manager.volume_percentage
        #volume_slider.bind(value=lambda _, new_volume: self.sound_manager.set_volume_percentage(new_volume))

        self.lower_game_grid.add_widget(text)

        #Clock.schedule_interval(lambda dt: self.confetti_view.redraw_confetti(dt), 1 / 60)

        return container
