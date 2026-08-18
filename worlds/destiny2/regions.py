from __future__ import annotations

from typing import TYPE_CHECKING
from rule_builder.rules import Has
from BaseClasses import Entrance, Region

if TYPE_CHECKING:
    from .world import APQuestWorld

# A region is a container for locations ("checks"), which connects to other regions via "Entrance" objects.
# Many games will model their Regions after physical in-game places, but you can also have more abstract regions.
# For a location to be in logic, its containing region must be reachable.
# The Entrances connecting regions can have rules - more on that in rules.py.
# This makes regions especially useful for traversal logic ("Can the player reach this part of the map?")

# Every location must be inside a region, and you must have at least one region.
# This is why we create regions first, and then later we create the locations (in locations.py).

DESTINATIONS = ["EDZ", "Dreaming City", "Nessus", "Moon", "Cosmodrome", "Europa", "Throne World", "Pale Heart", "Neomuna"]
CAMPAIGNS = []
DUNGEONS = []
RAIDS = []

def create_region(world: APQuestWorld, region: str, orbit: Region) -> None:
    reg = Region(region, world.player, world.multiworld)
    world.multiworld.regions.append(reg)
    world.create_entrance(orbit, reg, Has(region + " Key"))

def create_and_connect_regions(world: APQuestWorld) -> None:
    # Creating a region is as simple as calling the constructor of the Region class.
    orbit = Region("Orbit", world.player, world.multiworld)
    world.multiworld.regions.append(orbit)
    for region in DESTINATIONS:
        create_region(world, region, orbit)


