from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Item, ItemClassification
from Options import OptionError
from itertools import batched

if TYPE_CHECKING:
    from .world import DestinyWorld

# Every item must have a unique integer ID associated with it.
# We will have a lookup from item name to ID here that, in world.py, we will import and bind to the world class.
# Even if an item doesn't exist on specific options, it must be present in this lookup.
ITEM_NAME_TO_ID = {
    "Key": 1,
    "Nothing": 2
}

# Items should have a defined default classification.
# In our case, we will make a dictionary from item name to classification.
DEFAULT_ITEM_CLASSIFICATIONS = {
    "Key": ItemClassification.progression,
    "Nothing": ItemClassification.filler
}


# Each Item instance must correctly report the "game" it belongs to.
# To make this simple, it is common practice to subclass the basic Item class and override the "game" field.
class DestinyItem(Item):
    game = "Destiny2"


# Ontop of our regular itempool, our world must be able to create arbitrary amounts of filler as requested by core.
# To do this, it must define a function called world.get_filler_item_name(), which we will define in world.py later.
# For now, let's make a function that returns the name of a random filler item here in items.py.
def get_random_filler_item_name(world: DestinyWorld) -> str:
    # Destiny has an option called "trap_chance".
    # This is the percentage chance that each filler item is a Math Trap instead of a Confetti Cannon.
    # For this purpose, we need to use a random generator.

    # IMPORTANT: Whenever you need to use a random generator, you must use world.random.
    # This ensures that generating with the same generator seed twice yields the same output.
    # DO NOT use a bare random object from Python's built-in random module.
#    if world.random.randint(0, 99) < world.options.trap_chance:
#        return "Math Trap"
    return "Nothing"


def create_item_with_correct_classification(world: DestinyWorld, name: str) -> DestinyItem:
    # Our world class must have a create_item() function that can create any of our items by name at any time.
    # So, we make this helper function that creates the item by name with the correct classification.
    # Note: This function's content could just be the contents of world.create_item in world.py directly,
    # but it seemed nicer to have it in its own function over here in items.py.
    classification = DEFAULT_ITEM_CLASSIFICATIONS[name]

    return DestinyItem(name, classification, ITEM_NAME_TO_ID[name], world.player)


# With those two helper functions defined, let's now get to actually creating and submitting our itempool.
def create_all_items(world: DestinyWorld) -> None:
    itempool: list[Item] = [
        world.create_item("Key")
    ]
    # copy ?
    items = world.options.items.value
    if len(items) < 4:
        raise OptionError('Not enough vault items !')
    world.random.shuffle(items)
    # -- Count items in reference to locations
    locs = len(world.multiworld.get_unfilled_locations(world.player)) - len(itempool)
    if locs <= 0:
        raise OptionError('Not enough locations !')
    # -- Split items into bundles (how many?)
    ct_per_pack = len(items) // locs
    # Split into packs and add any leftover items into that one
    packs = list(batched(items, ct_per_pack))
    if len(packs[-1]) != len(packs[0]):
        idx = 0
        for item in packs.pop():
            # asserted that idx is in packs
            packs[idx].append(item)
            idx += 1

    # -- Assign the progressive lines (how long ?)
    # - Have a avg score diff, it aims for the average score diff on each step, and have a min score diff, if nothing can be found that increases score by that much, it stops ~~and an estimate on how many prog packs to make per category~~
    # - For each category ; For each nonprog pack, calc their score in that category; then pick the one nearest to give an increase of (target score / prog packs)
    # -- If it ends up being over the limit end there (Find a weaker combo ???)
    # -- If it ends up being lower than the limit, add more packs (Find a better combo ???)

    # Two easy categories, "Boss damage" and "Adds clear", the background holds the numbers, so amount of packs per encounter may change more
    # "Support Pack" at fixed spots in logic, only containing buffs ?

    # TODO set theses as options, or calculate from enabled activities
    # 1k = about 8 divisions ? i hope ?
    avg_score_diff = 1000
    # used to avoid leaving accidental strong combos behind, whilst providing a useful
    min_score_diff = 100
    categories = ["BossDPS", "AddsClear"]
    # TODO the "boss" pathway may steal items wanted by the "adds clear" pathway, how to fix ?
    # Each pack has a score dependant on other factors (melee, etc), it picks the lowest score to try to improve for every round (if none above min, try with another score ?)

    for c in categories:
        # Crit / Body / Sword
        current_scores = [0,0,0,0]
        loadout = []
        current_cat = 0
        # TODO Assign a score to each pack, then filtered by removing the ones lower than the min score diff
        scores: list[int] = list(filter(lambda y : y - current_scores[current_cat] >= min_score_diff, [len(x) for x in packs]))
        index_max = max(range(len(scores)), key=scores.__getitem__)
        # if score diff is smaller than min, abandon
        if scores[index_max] - current_scores[current_cat] < min_score_diff:
            break


    world.multiworld.itempool += itempool

