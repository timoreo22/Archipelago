from argparse import Namespace
from dataclasses import dataclass

import NetUtils
import Options
import Utils
from worlds.AutoWorld import World
import collections
from collections.abc import Mapping
import concurrent.futures
import logging
import os
import tempfile
import time
from typing import Any, Optional, List
import zipfile
import zlib

import worlds
from BaseClasses import Item, Location, LocationProgressType, MultiWorld, CollectionState, Spoiler
from Fill import FillError, balance_multiworld_progression, distribute_items_restrictive, flood_items, \
    parse_planned_blocks, distribute_planned_blocks, resolve_early_locations_for_planned
from NetUtils import convert_to_base_types
from Options import StartInventoryPool, PerGameCommonOptions, Range
from Utils import output_path, restricted_dumps, version_tuple
from settings import get_settings
from worlds import AutoWorld
from worlds.generic.Rules import exclusion_rules, locality_rules

from worlds.zzzroom_split import algorithm
from worlds.zzzroom_split.deepercopy import deepcopy

class RoomCountOption(Range):
    """
    How many Rooms to split this generation into
    Having more than 4 rooms can slow down the room splitting algorithm by a lot
    """

    display_name = "Room Count"

    range_start = 2
    range_end = 20
    default = 2

class TimeLimitOption(Range):
    """
    How much time in seconds to wait before considering the rooms to be split apart "enough"
    The algorithm for splitting rooms apart may run for a very long time for 3+ rooms and enough players, this adds a time cap to this generation
    Setting it to 0 will let it run forever
    No matter this setting, you can press q on the generation window at any moment to stop it at its current progress
    """

    display_name = "Time Limit"

    range_start = 0
    range_end = 100000
    default = 600

@dataclass
class RoomSplitOptions(PerGameCommonOptions):
    room_count: RoomCountOption
    time_limit: TimeLimitOption

class RoomSplitWorld(World):
    game = "Room Splitter"
    hidden = False
    item_name_to_id = {}
    location_name_to_id = {}
    options_dataclass = RoomSplitOptions
    options: RoomSplitOptions
    room_count: int = 2
    time_limit: float = 600
    pid: int = 0

    def generate_early(self):
        # Injects into the class, last yaml loaded will count
        self.__class__.room_count = self.options.room_count.value
        self.__class__.time_limit = self.options.time_limit.value
        self.__class__.pid = self.player

    @classmethod
    def stage_create_items(cls, multiworld: MultiWorld) -> None:
        # Avoid doing a gen if ut is there
        is_ut = getattr(multiworld, "generation_is_fake", False)
        if is_ut:
            return
        from faulthandler import enable
        enable()
        logger = logging.getLogger()

        # Nuke all itemlink "players"
        itemlinks = list(multiworld.groups.keys())
        def delete_player(player):
            del multiworld.game[player]
            del multiworld.player_types[player]
            del multiworld.player_name[player]
            del multiworld.worlds[player]
            del multiworld.regions.region_cache[player]
            del multiworld.regions.entrance_cache[player]
            del multiworld.regions.location_cache[player]

        for link in itemlinks:
            delete_player(link)
        multiworld.groups = {}

        # Delete traces of the room splitter
        delete_player(cls.pid)

        numroom = cls.room_count
        logger.info("Splitting room into %d", numroom)
        data = {player: len(locations) for player, locations in multiworld.regions.location_cache.items()}
        if cls.time_limit == 0:
            import math
            cls.time_limit = math.inf
        out = algorithm.anytime(numroom, data, cls.time_limit)
        if out is None:
            logger.error("Error, search stopped too soon !!")
            raise InterruptedError
        sums = out[0]
        logger.info("Max difference of checks between rooms : " + str(max(sums) - min(sums)))
        # TODO make this modifiable ?
        args = Namespace(skip_prog_balancing=False, skip_output=False, spoiler_only=False, spoiler=1)
        gen_number = 1

        # Fixes deep copy crashing with lingo, maybe make it configurable ?
        from sys import setrecursionlimit
        setrecursionlimit(20000)

        for playerset in out[1]:
            logger.info("Preparing gen %d", gen_number)
            playerset = sorted(playerset)
            count = len(playerset)
            playerset = set(playerset)

            # Deep copy of multiword, making sure only the players that need to be there are
            new_mw = MultiWorld(count)
            memo = {id(multiworld) : new_mw}

            new_mw.debug_types = multiworld.debug_types
            new_mw.is_race = multiworld.is_race
            new_mw.plando_options = multiworld.plando_options

            new_mw.player_name = {k:v for k,v in deepcopy(multiworld.player_name, memo).items() if k in playerset}

            # These methods don't play well if the player ids aren't sequential, patching them here
            # Dear lord what the fuck is this
            new_mw.__dict__["player_ids"] = tuple(new_mw.player_name.keys())
            def has_beaten_game(self, state: CollectionState, player: Optional[int] = None) -> bool:
                if player:
                    return self.completion_condition[player](state)
                else:
                    return all((self.has_beaten_game(state, p) for p in self.player_ids))
            new_mw.__dict__["has_beaten_game"] = has_beaten_game.__get__(new_mw, MultiWorld)

            new_mw.player_types = {k:v for k,v in deepcopy(multiworld.player_types, memo).items() if k in playerset}
            new_mw.set_seed(multiworld.seed)

            new_mw.game = {k:v for k,v in deepcopy(multiworld.game, memo).items() if k in playerset}
            new_mw.early_items = {k:v for k,v in deepcopy(multiworld.early_items, memo).items() if k in playerset}
            new_mw.local_early_items = {k:v for k,v in deepcopy(multiworld.local_early_items, memo).items() if k in playerset}
            new_mw.completion_condition = {k:v for k,v in deepcopy(multiworld.completion_condition, memo).items() if k in playerset}
            new_mw.itempool = [item for item in deepcopy(multiworld.itempool, memo) if item.player in playerset]
            new_mw.precollected_items = {k:v for k,v in deepcopy(multiworld.precollected_items, memo).items() if k in playerset}

            def fix_world(world,  mw):
                world.multiworld = mw
                return world

            new_mw.worlds = {k : fix_world(v, new_mw) for k,v in deepcopy(multiworld.worlds, memo).items() if k in playerset}

            new_mw.regions.entrance_cache = {k : v for k,v in deepcopy(multiworld.regions.entrance_cache, memo).items() if k in playerset}
            new_mw.regions.location_cache = {k : v for k,v in deepcopy(multiworld.regions.location_cache, memo).items() if k in playerset}
            new_mw.regions.region_cache = {k : v for k,v in deepcopy(multiworld.regions.region_cache, memo).items() if k in playerset}
            new_mw.indirect_connections = deepcopy(multiworld.indirect_connections, memo)

            new_mw.state = deepcopy(multiworld.state, memo)

            # Rebuild the itemlinks
            new_mw.set_item_links()

            from worlds.AutoWorld import World
            # Adding in the fake players !!
            padding = []
            for x in range(1, len(new_mw.player_ids) + len(new_mw.groups) + 1):
                if x not in new_mw.player_ids and x not in new_mw.groups:
                    padding.append(x)
                    new_mw.game[x] = "Archipelago"
                    new_mw.early_items[x] = {}
                    new_mw.local_early_items[x] = {}
                    new_mw.completion_condition[x] = lambda x: True
                    new_mw.precollected_items[x] = []
                    new_mw.player_name[x] = "Padding" + str(x)
                    new_mw.player_types[x] = NetUtils.SlotType.spectator

                    new_mw.regions.add_group(x)
                    world = World(multiworld, x)
                    world.game = "Archipelago"
                    world.options = World.options_dataclass(**{option_key: option.from_any(option.default)
                                                             for option_key, option in
                                                             World.options_dataclass.type_hints.items()})
                    world.options.accessibility = Options.ItemsAccessibility(Options.ItemsAccessibility.option_items)
                    new_mw.worlds[x] = world


            new_mw.__dict__["player_ids"] = tuple(sorted(new_mw.player_ids + tuple(padding)))

            logger.info("Starting generation %d", gen_number)
            del memo
            resume_multiworld(args,new_mw, gen_number)
            gen_number += 1

        logger.info("All rooms have been successfully generated !!")
        import atexit
        # Remove the "press enter to continue"
        atexit.unregister(input)
        from sys import exit
        exit(0)

def resume_multiworld(args, multiworld: MultiWorld, gen_number):
    # Time won't be fully correct, eh
    baked_server_options = get_settings().server_options.as_dict()
    start = time.perf_counter()
    logger = logging.getLogger()

    # --- From then onwards, normal code, copied from Main.py, has some extra patches for hole support ---

    logger.info('Calculating Access Rules.')
    AutoWorld.call_all(multiworld, "set_rules")

    for player in multiworld.player_ids:
        exclusion_rules(multiworld, player, multiworld.worlds[player].options.exclude_locations.value)
        multiworld.worlds[player].options.priority_locations.value -= multiworld.worlds[player].options.exclude_locations.value
        world_excluded_locations = set()
        for location_name in multiworld.worlds[player].options.priority_locations.value:
            try:
                location = multiworld.get_location(location_name, player)
            except KeyError:
                continue

            if location.progress_type != LocationProgressType.EXCLUDED:
                location.progress_type = LocationProgressType.PRIORITY
            else:
                logger.warning(f"Unable to prioritize location \"{location_name}\" in player {player}'s world because the world excluded it.")
                world_excluded_locations.add(location_name)
        multiworld.worlds[player].options.priority_locations.value -= world_excluded_locations

    # Set local and non-local item rules.
    # This function is called so late because worlds might otherwise overwrite item_rules which are how locality works
    if multiworld.players > 1:
        locality_rules(multiworld)

    multiworld.plando_item_blocks = parse_planned_blocks(multiworld)

    AutoWorld.call_all(multiworld, "connect_entrances")
    AutoWorld.call_all(multiworld, "generate_basic")

    # remove starting inventory from pool items.
    # Because some worlds don't actually create items during create_items this has to be as late as possible.
    fallback_inventory = StartInventoryPool({})
    depletion_pool: dict[int, dict[str, int]] = {
        player: getattr(multiworld.worlds[player].options, "start_inventory_from_pool", fallback_inventory).value.copy()
        for player in multiworld.player_ids
    }
    target_per_player = {
        player: sum(target_items.values()) for player, target_items in depletion_pool.items() if target_items
    }

    if target_per_player:
        new_itempool: list[Item] = []

        # Make new itempool with start_inventory_from_pool items removed
        for item in multiworld.itempool:
            if depletion_pool[item.player].get(item.name, 0):
                depletion_pool[item.player][item.name] -= 1
            else:
                new_itempool.append(item)

        # Create filler in place of the removed items, warn if any items couldn't be found in the multiworld itempool
        for player, target in target_per_player.items():
            unfound_items = {item: count for item, count in depletion_pool[player].items() if count}

            if unfound_items:
                player_name = multiworld.get_player_name(player)
                logger.warning(f"{player_name} tried to remove items from their pool that don't exist: {unfound_items}")

            needed_items = target_per_player[player] - sum(unfound_items.values())
            new_itempool += [multiworld.worlds[player].create_filler() for _ in range(needed_items)]

        assert len(multiworld.itempool) == len(new_itempool), "Item Pool amounts should not change."
        multiworld.itempool[:] = new_itempool

    multiworld.link_items()

    if any(world.options.item_links for world in multiworld.worlds.values()):
        multiworld._all_state = None

    logger.info("Running Item Plando.")
    resolve_early_locations_for_planned(multiworld)
    distribute_planned_blocks(multiworld, [x for player in multiworld.plando_item_blocks
                                           for x in multiworld.plando_item_blocks[player]])

    logger.info('Running Pre Main Fill.')

    AutoWorld.call_all(multiworld, "pre_fill")

    logger.info(f'Filling the multiworld with {len(multiworld.itempool)} items.')

    if multiworld.algorithm == 'flood':
        flood_items(multiworld)  # different algo, biased towards early game progress items
    elif multiworld.algorithm == 'balanced':
        distribute_items_restrictive(multiworld, get_settings().generator.panic_method)

    AutoWorld.call_all(multiworld, 'post_fill')

    if multiworld.players > 1 and not args.skip_prog_balancing:
        balance_multiworld_progression(multiworld)
    else:
        logger.info("Progression balancing skipped.")

    AutoWorld.call_all(multiworld, "finalize_multiworld")
    AutoWorld.call_all(multiworld, "pre_output")
    if args.skip_output:
        logger.info('Done. Skipped output/spoiler generation. Total Time: %s', time.perf_counter() - start)
        return multiworld
    # we're about to output using multithreading, so we're removing the global random state to prevent accidental use
    multiworld.random.passthrough = False

    logger.info(f'Beginning output...')
    outfilebase = 'AP_' + multiworld.seed_name

    if args.spoiler_only:
        if args.spoiler > 1:
            logger.info('Calculating playthrough.')
            multiworld.spoiler.create_playthrough(create_paths=args.spoiler > 2)

        multiworld.spoiler.to_file(output_path('%s_Spoiler.txt' % outfilebase))
        logger.info('Done. Skipped multidata modification. Total time: %s', time.perf_counter() - start)
        return multiworld

    output = tempfile.TemporaryDirectory()
    with output as temp_dir:
        output_players = [player for player in multiworld.player_ids if AutoWorld.World.generate_output.__code__
                          is not multiworld.worlds[player].generate_output.__code__]
        with concurrent.futures.ThreadPoolExecutor(len(output_players) + 2) as pool:
            check_accessibility_task = pool.submit(multiworld.fulfills_accessibility)

            output_file_futures = [pool.submit(AutoWorld.call_stage, multiworld, "generate_output", temp_dir)]
            for player in output_players:
                # skip starting a thread for methods that say "pass".
                output_file_futures.append(
                    pool.submit(AutoWorld.call_single, multiworld, "generate_output", player, temp_dir))

            # collect ER hint info
            er_hint_data: dict[int, dict[int, str]] = {}
            AutoWorld.call_all(multiworld, 'extend_hint_information', er_hint_data)

            def write_multidata():
                import NetUtils
                from NetUtils import HintStatus
                client_versions: dict[int, tuple[int, int, int]] = {}
                games: dict[int, str] = {}
                slot_data: dict[int, Mapping[str, Any]] = {}
                minimum_versions: NetUtils.MinimumVersions = {
                    "server": AutoWorld.World.required_server_version, "clients": client_versions
                }
                slot_info: dict[int, NetUtils.NetworkSlot] = {}
                names = {p: name for p, name in sorted(multiworld.player_name.items())}
                for slot in multiworld.player_ids:
                    player_world: AutoWorld.World = multiworld.worlds[slot]
                    minimum_versions["server"] = max(minimum_versions["server"], player_world.required_server_version)
                    client_versions[slot] = player_world.required_client_version
                    games[slot] = multiworld.game[slot]
                    slot_info[slot] = NetUtils.NetworkSlot(names[slot], multiworld.game[slot],
                                                           multiworld.player_types[slot])
                for slot, group in multiworld.groups.items():
                    games[slot] = multiworld.game[slot]
                    slot_info[slot] = NetUtils.NetworkSlot(group["name"], multiworld.game[slot], multiworld.player_types[slot],
                                                           group_members=sorted(group["players"]))

                precollected_items = {player: [item.code for item in world_precollected if type(item.code) == int]
                                      for player, world_precollected in multiworld.precollected_items.items()}
                precollected_hints: dict[int, set[NetUtils.Hint]] = {
                    player: set() for player in range(1, len(games) + 1)
                }

                for slot in multiworld.player_ids:
                    slot_data[slot] = multiworld.worlds[slot].fill_slot_data()

                def precollect_hint(location: Location, auto_status: HintStatus):
                    entrance = er_hint_data.get(location.player, {}).get(location.address, "")
                    hint = NetUtils.Hint(location.item.player, location.player, location.address,
                                         location.item.code, False, entrance, location.item.flags, auto_status)
                    if location.player not in precollected_hints:
                        logger.info("Hint deleted due to being for an invalid player")
                        return # ????
                    precollected_hints[location.player].add(hint)
                    if location.item.player not in multiworld.groups:
                        precollected_hints[location.item.player].add(hint)
                    else:
                        for player in multiworld.groups[location.item.player]["players"]:
                            precollected_hints[player].add(hint)

                # PATCH : include all players in the locations
                locations_data: dict[int, dict[int, tuple[int, int, int]]] = {player: {} for player in games.keys()}
                for location in multiworld.get_filled_locations():
                    if type(location.address) == int:
                        assert location.item.code is not None, "item code None should be event, " \
                                                               "location.address should then also be None. Location: " \
                                                               f" {location}, Item: {location.item}"
                        assert location.address not in locations_data[location.player], (
                            f"Locations with duplicate address. {location} and "
                            f"{locations_data[location.player][location.address]}")
                        locations_data[location.player][location.address] = \
                            location.item.code, location.item.player, location.item.flags
                        auto_status = HintStatus.HINT_AVOID if location.item.trap else HintStatus.HINT_PRIORITY
                        if location.name in multiworld.worlds[location.player].options.start_location_hints:
                            if not location.item.trap:  # Unspecified status for location hints, except traps
                                auto_status = HintStatus.HINT_UNSPECIFIED
                            precollect_hint(location, auto_status)
                        elif location.item.name in multiworld.worlds[location.item.player].options.start_hints:
                            precollect_hint(location, auto_status)
                        elif any([location.item.name in multiworld.worlds[player].options.start_hints
                                  for player in multiworld.groups.get(location.item.player, {}).get("players", [])]):
                            precollect_hint(location, auto_status)

                # embedded data package
                data_package = {
                    game_world.game: worlds.network_data_package["games"][game_world.game]
                    for game_world in multiworld.worlds.values()
                }
                data_package["Archipelago"] = worlds.network_data_package["games"]["Archipelago"]

                checks_in_area: dict[int, dict[str, int | list[int]]] = {}

                # get spheres -> filter address==None -> skip empty
                spheres: list[dict[int, set[int]]] = []
                for sphere in multiworld.get_sendable_spheres():
                    current_sphere: dict[int, set[int]] = collections.defaultdict(set)
                    for sphere_location in sphere:
                        current_sphere[sphere_location.player].add(sphere_location.address)

                    if current_sphere:
                        spheres.append(dict(current_sphere))

                multidata: NetUtils.MultiData = {
                    "slot_data": slot_data,
                    "slot_info": slot_info,
                    "connect_names": {name: (0, player) for player, name in multiworld.player_name.items()},
                    "locations": locations_data,
                    "checks_in_area": checks_in_area,
                    "server_options": baked_server_options,
                    "er_hint_data": er_hint_data,
                    "precollected_items": precollected_items,
                    "precollected_hints": precollected_hints,
                    "version": (version_tuple.major, version_tuple.minor, version_tuple.build),
                    "tags": ["AP"],
                    "minimum_versions": minimum_versions,
                    "seed_name": multiworld.seed_name,
                    "spheres": spheres,
                    "datapackage": data_package,
                    "race_mode": int(multiworld.is_race),
                }
                # TODO: change to `"version": version_tuple` after getting better serialization
                AutoWorld.call_all(multiworld, "modify_multidata", multidata)

                for key in ("slot_data", "er_hint_data"):
                    multidata[key] = convert_to_base_types(multidata[key])

                serialized_multidata = zlib.compress(restricted_dumps(multidata), 9)

                with open(os.path.join(temp_dir, f'{outfilebase}.archipelago'), 'wb') as f:
                    f.write(bytes([3]))  # version of format
                    f.write(serialized_multidata)

            output_file_futures.append(pool.submit(write_multidata))
            if not check_accessibility_task.result():
                if not multiworld.can_beat_game():
                    raise FillError("Game appears as unbeatable. Aborting.", multiworld=multiworld)
                else:
                    logger.warning("Location Accessibility requirements not fulfilled.")

            # retrieve exceptions via .result() if they occurred.
            for i, future in enumerate(concurrent.futures.as_completed(output_file_futures), start=1):
                if i % 10 == 0 or i == len(output_file_futures):
                    logger.info(f'Generating output files ({i}/{len(output_file_futures)}).')
                future.result()

        if args.spoiler > 1:
            logger.info('Calculating playthrough.')
            multiworld.spoiler.create_playthrough(create_paths=args.spoiler > 2)

        if args.spoiler:
            def to_file(self, filename: str) -> None:
                from itertools import chain
                from worlds import AutoWorld
                from Options import Visibility

                def write_option(option_key: str, option_obj: Options.AssembleOptions) -> None:
                    res = getattr(self.multiworld.worlds[player].options, option_key)
                    if res.visibility & Visibility.spoiler:
                        display_name = getattr(option_obj, "display_name", option_key)
                        outfile.write(f"{display_name + ':':33}{res.current_option_name}\n")

                with open(filename, 'w', encoding="utf-8-sig") as outfile:
                    outfile.write(
                        'Archipelago Version %s  -  Seed: %s\n\n' % (
                            Utils.__version__, self.multiworld.seed))
                    outfile.write('Filling Algorithm:               %s\n' % self.multiworld.algorithm)
                    outfile.write('Players:                         %d\n' % self.multiworld.players)
                    if self.multiworld.players > 1:
                        loc_count = len([loc for loc in self.multiworld.get_locations() if not loc.is_event])
                        outfile.write('Total Location Count:            %d\n' % loc_count)
                    outfile.write(f'Plando Options:                  {self.multiworld.plando_options}\n')
                    AutoWorld.call_stage(self.multiworld, "write_spoiler_header", outfile)

                    for player in self.multiworld.player_ids:
                        if self.multiworld.players > 1:
                            outfile.write('\nPlayer %d: %s\n' % (player, self.multiworld.get_player_name(player)))
                        outfile.write('Game:                            %s\n' % self.multiworld.game[player])

                        loc_count = len([loc for loc in self.multiworld.get_locations(player) if not loc.is_event])
                        outfile.write('Location Count:                  %d\n' % loc_count)

                        for f_option, option in self.multiworld.worlds[player].options_dataclass.type_hints.items():
                            write_option(f_option, option)

                        AutoWorld.call_single(self.multiworld, "write_spoiler_header", player, outfile)

                    if self.entrances:
                        outfile.write('\n\nEntrances:\n\n')
                        outfile.write('\n'.join(['%s%s %s %s' % (f'{self.multiworld.get_player_name(entry["player"])}: '
                                                                 if self.multiworld.players > 1 else '',
                                                                 entry['entrance'],
                                                                 '<=>' if entry['direction'] == 'both' else
                                                                 '<=' if entry['direction'] == 'exit' else '=>',
                                                                 entry['exit']) for entry in self.entrances.values()]))

                    AutoWorld.call_all(self.multiworld, "write_spoiler", outfile)

                    precollected_items = [f"{item.name} ({self.multiworld.get_player_name(item.player)})"
                                          if self.multiworld.players > 1
                                          else item.name
                                          for item in chain.from_iterable(self.multiworld.precollected_items.values())]
                    if precollected_items:
                        outfile.write("\n\nStarting Items:\n\n")
                        outfile.write("\n".join([item for item in precollected_items]))

                    locations = [(str(location), str(location.item) if location.item is not None else "Nothing")
                                 for location in self.multiworld.get_locations() if location.show_in_spoiler]
                    outfile.write('\n\nLocations:\n\n')
                    outfile.write('\n'.join(
                        ['%s: %s' % (location, item) for location, item in locations]))

                    outfile.write('\n\nPlaythrough:\n\n')
                    outfile.write('\n'.join(['%s: {\n%s\n}' % (sphere_nr, '\n'.join(
                        [f"  {location}: {item}" for (location, item) in sphere.items()] if isinstance(sphere,
                                                                                                       dict) else
                        [f"  {item}" for item in sphere])) for (sphere_nr, sphere) in self.playthrough.items()]))
                    if self.unreachables:
                        outfile.write('\n\nUnreachable Progression Items:\n\n')
                        outfile.write(
                            '\n'.join(['%s: %s' % (unreachable.item, unreachable)
                                       for unreachable in sorted(self.unreachables)]))

                    if self.paths:
                        outfile.write('\n\nPaths:\n\n')
                        path_listings: List[str] = []
                        for location, path in sorted(self.paths.items()):
                            path_lines: List[str] = []
                            for region, exit in path:
                                if exit is not None:
                                    path_lines.append("{} -> {}".format(region, exit))
                                else:
                                    path_lines.append(region)
                            path_listings.append("{}\n        {}".format(location, "\n   =>   ".join(path_lines)))

                        outfile.write('\n'.join(path_listings))
                    AutoWorld.call_all(self.multiworld, "write_spoiler_end", outfile)
            multiworld.spoiler.to_file = to_file.__get__(multiworld.spoiler, Spoiler)
            multiworld.spoiler.to_file(os.path.join(temp_dir, '%s_Spoiler.txt' % outfilebase))

        zipfilename = output_path(f"AP_{multiworld.seed_name}_{gen_number}.zip")
        logger.info(f"Creating final archive at {zipfilename}")
        with zipfile.ZipFile(zipfilename, mode="w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9) as zf:
            for file in os.scandir(temp_dir):
                zf.write(file.path, arcname=file.name)

    logger.info('Done. Enjoy. Total Time: %s', time.perf_counter() - start)
    return multiworld



