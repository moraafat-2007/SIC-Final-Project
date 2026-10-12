def merge_sort(lst):
    if len(lst) <= 1:
        return lst

    mid_point = len(lst) // 2

    l_lst = merge_sort(lst[:mid_point])
    r_lst = merge_sort(lst[mid_point:])

    i = 0
    j = 0
    ordered_lst = []

    while i < len(l_lst) and j < len(r_lst):
        if l_lst[i] <= r_lst[j]:
            ordered_lst.append(l_lst[i])
            i += 1
        else:
            ordered_lst.append(r_lst[j])
            j += 1

    ordered_lst.extend(l_lst[i:])
    ordered_lst.extend(r_lst[j:])

    return ordered_lst


def binary_search(lst, target):
    low = 0
    high = len(lst) - 1

    while low <= high:
        mid_point = (low + high) // 2

        if lst[mid_point] == target:
            return mid_point
        elif lst[mid_point] < target:
            low = mid_point + 1
        else:
            high = mid_point - 1
    return None



# needs more work to be actually usefully, I am still thinking :)
def sequential_search(lst, target):

    wanted_lst = list(i for i in lst if i == target)

    return wanted_lst
