from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import ItemClassification, Location

from . import items

if TYPE_CHECKING:
    from .world import DestinyWorld

# Every location must have a unique integer ID associated with it.
# We will have a lookup from location name to ID here that, in world.py, we will import and bind to the world class.
# Even if a location doesn't exist on specific options, it must be present in this lookup.
LOCATION_NAME_TO_ID = {
	"Kill 1 Enemy Using a Kinetic Weapon": 1,
	"Kill 2 Enemies Using a Kinetic Weapon": 2,
	"Kill 3 Enemies Using a Kinetic Weapon": 3,
	"Kill 4 Enemies Using a Kinetic Weapon": 4,
	"Kill 5 Enemies Using a Kinetic Weapon": 5,
	"Kill 6 Enemies Using a Kinetic Weapon": 6,
	"Kill 7 Enemies Using a Kinetic Weapon": 7,
	"Kill 8 Enemies Using a Kinetic Weapon": 8,
	"Kill 9 Enemies Using a Kinetic Weapon": 9,
	"Kill 10 Enemies Using a Kinetic Weapon": 10,
	"Victory": 11
}


# Each Location instance must correctly report the "game" it belongs to.
# To make this simple, it is common practice to subclass the basic Location class and override the "game" field.
class DestinyLocation(Location):
    game = "Destiny2"


# Let's make one more helper method before we begin actually creating locations.
# Later on in the code, we'll want specific subsections of LOCATION_NAME_TO_ID.
# To reduce the chance of copy-paste errors writing something like {"Chest": LOCATION_NAME_TO_ID["Chest"]},
# let's make a helper method that takes a list of location names and returns them as a dict with their IDs.
# Note: There is a minor typing quirk here. Some functions want location addresses to be an "int | None",
# so while our function here only ever returns dict[str, int], we annotate it as dict[str, int | None].
def get_location_names_with_ids(location_names: list[str]) -> dict[str, int | None]:
    return {location_name: LOCATION_NAME_TO_ID[location_name] for location_name in location_names}


def create_all_locations(world: DestinyWorld) -> None:
    create_regular_locations(world)


def create_regular_locations(world: DestinyWorld) -> None:
    # Finally, we need to put the Locations ("checks") into their regions.
    # Once again, before we do anything, we can grab our regions we created by using world.get_region()
    orbit = world.get_region("Orbit")
    orbit.add_locations(LOCATION_NAME_TO_ID, DestinyLocation)

