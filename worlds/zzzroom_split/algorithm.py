"""
Adapted from https://github.com/coin-or/prtpy/blob/13340c110fd448359d14a243e9604b7512474440/prtpy/partitioning/complete_greedy.py (MIT License)
"""
import time

import math
from typing import List, Tuple, TypeVar
from worlds.zzzroom_split.keyboard import get_key, init as init_keyboard

T = TypeVar('T')
BinsArray = Tuple[List[int], List[List[T]]]  # Here, each bins-array is a tuple: sums,lists. sums is an array of sums; lists is a list of lists of items.

def make_new_bins(numbins: int) -> BinsArray:
    sums = [0] * numbins
    lists = [[] for _ in range(numbins)]
    return sums, lists

def add_to_bin(bins:BinsArray, item: T, bin_index: int, data: dict)->BinsArray:
    sums, lists = bins
    value = data[item]
    sums[bin_index] += value
    lists[bin_index].append(item)
    return bins


def find_lower_bound(sums:list|tuple, sum_of_remaining_items:float, are_sums_in_ascending_order:bool=False)->float:
    # new_sums = np.array(current_sums)
    # new_sums[bin_index] += value_to_add
    # sorted_sums = sorted(new_sums)       # sorted by ascending sum
    sorted_sums = sums if are_sums_in_ascending_order else sorted(sums)
    # algorithm by Paul A. Robin https://or.stackexchange.com/a/8632/2576
    newsum = sum_of_remaining_items
    newsum += sorted_sums[0]
    for i in range(1, len(sorted_sums)):
        if newsum <= i * sorted_sums[i]:
            return -math.floor(newsum / i)
        newsum += sorted_sums[i]

    current_largest_sum = sorted_sums[-1]
    return (max(current_largest_sum, math.ceil((sum(sums) + sum_of_remaining_items) / len(sums)))) + (-math.floor(newsum / len(sorted_sums)))


def sort_by_sum(bins: BinsArray):
    sums, lists = bins
    numbins = len(bins[0])
    sorted_indices = sorted(range(numbins), key=lambda i: sums[i])
    sums[:] = list(map(sums.__getitem__, sorted_indices))
    lists[:] = list(map(lists.__getitem__, sorted_indices))


def copy_bins(bins: BinsArray)->BinsArray:
    sums, lists = bins
    return list(sums), list(map(list, lists))

def anytime(
    numbins: int, data: dict[T, int],
    time_limit: float = math.inf,
) -> tuple[list[float], list[list[T]]] |None:
    """
    Finds a partition in which the largest sum is minimal, using the Complete Greedy algorithm.

    :param time_limit: determines how much time (in seconds) the function should run before it stops. Default is infinity.
    """
    init_keyboard()
    print("type q whenever you wanna stop the search, will stop after 10 minutes or if it finds the best solution")
    print("Starting up....")
    items: List[T] = list(data.keys())
    numitems = len(items)
    start_time = time.perf_counter_ns()
    end_time = start_time + time_limit*1000000000
    next_check = start_time + 500000000

    sorted_items = sorted(items, key=data.__getitem__, reverse=True)
    sums_of_remaining_items = [sum(map(data.__getitem__, sorted_items[i:])) for i in range(numitems)] + [0]  # For Heuristic 3
    best_bins, best_objective_value = None, math.inf


    global_lower_bound = find_lower_bound([0] * numbins, sums_of_remaining_items[0], are_sums_in_ascending_order=True)
    # Create a stack whose elements are a partition and the current depth.
    # Initially, it contains a single tuple: an empty partition with depth 0.
    first_bins = make_new_bins(numbins)
    first_vertex = (first_bins, 0)
    stack: List[Tuple[BinsArray, int]] = [first_vertex]
    seen_states = set(tuple(first_bins[0]))
    # For logging and profiling:
    complete_partitions_checked = 0
    intermediate_partitions_checked = 1

    times_lower_bound_activated = 0
    times_seen_state_skipped = 0
    animation_frames = '|/-\\'
    animation_index = 0
    while len(stack) > 0:
        c = time.perf_counter_ns()
        if c > end_time:
            print("out of time")
            break
        if c > next_check:
            next_check = c + 500000000
            if 'q' == get_key():
                break
            # Even if no change, print a lil something to show we're still going
            print("\x1b[ABest difference of checks between rooms currently found :", best_objective_value, animation_frames[animation_index])
            animation_index = (animation_index + 1) % (len(animation_frames))

        current_bins, depth = stack.pop()
        current_sums = tuple(current_bins[0])

        # If we have reached the leaves of the DFS tree, check if we have an improvement:
        if depth == numitems:
            complete_partitions_checked += 1
            new_objective_value = max(current_sums) - min(current_sums)
            if new_objective_value < best_objective_value:
                best_bins, best_objective_value = current_bins, new_objective_value
                if new_objective_value <= global_lower_bound:
                    break
            continue
        next_item = sorted_items[depth]
        sum_of_remaining_items = sums_of_remaining_items[depth + 1]

        previous_bin_sum = None

        # We want to insert the next item to the bin with the *smallest* sum first.
        # But, since we use a stack, we have to insert it to the bin with the *largest* sum first,
        # so that it is pushed deeper into the stack.
        # Therefore, we proceed in reverse, by *descending* order of sum.
        for bin_index in reversed(range(numbins)):

            # Heuristic 1: "If there are two subsets with the same sum, the current number is assigned to only one."
            current_bin_sum = current_sums[bin_index]
            if current_bin_sum == previous_bin_sum:
                continue
            previous_bin_sum = current_bin_sum

            new_bins = add_to_bin(copy_bins(current_bins), next_item, bin_index, data)
            sort_by_sum(new_bins)
            new_sums = tuple(new_bins[0])

            # Lower-bound heuristic.
            lower_bound = find_lower_bound(new_sums, sum_of_remaining_items, are_sums_in_ascending_order=False)
            if lower_bound >= best_objective_value:
                times_lower_bound_activated += 1
                continue
            if new_sums in seen_states:
                times_seen_state_skipped += 1
                continue
            seen_states.add(new_sums)  # should be after if use_lower_bound

            new_vertex = (new_bins, depth + 1)
            stack.append(new_vertex)
            intermediate_partitions_checked += 1
    if best_bins is None:
        return None
    for i in range(numbins):
        best_bins[0][i] = math.floor(best_bins[0][i])
    return best_bins

