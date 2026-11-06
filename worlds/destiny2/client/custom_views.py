from kivy.uix.gridlayout import GridLayout
from kivy.uix.boxlayout import BoxLayout



class DestinyGrid(GridLayout):
    def check_resize(self, _: int, _1: int) -> None:
        parent_width, parent_height = self.parent.size

        self_width_according_to_parent_height = parent_height * 12 / 11
        self_height_according_to_parent_width = parent_width * 11 / 12

        if self_width_according_to_parent_height > parent_width:
            self.size = parent_width, self_height_according_to_parent_width
        else:
            self.size = self_width_according_to_parent_height, parent_height


class DestinyText(BoxLayout):
    pass
