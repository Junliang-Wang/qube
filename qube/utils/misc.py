import functools
from copy import deepcopy

import numpy as np


def join_list(slist, separator=''):
    slist = list(slist)
    result = separator.join(['{}'.format(element) for element in slist])
    return result


def b2str(item):
    if hasattr(item, 'items'):
        new = bytes_to_string_dict(item)
    else:
        new = bytes_to_string(item)
    return new


def bytes_to_string(blist):
    if loopable(blist):
        new = list(blist)
        new = deepcopy(new)
        for index, value in enumerate(new):
            new[index] = _b2str(value)
    else:
        new = _b2str(blist)
    return new


def bytes_to_string_dict(dict_):
    ndict = {}
    for key, value in dict_.items():
        value = bytes_to_string(value)
        ndict[key] = value
    return ndict


def _b2str(var):
    if isinstance(var, bytes):
        var = var.decode('utf-8')
    return var


def str_to_type(config_dict):
    """Config parser stores all values in str type. If one wants to import information from a config file, one needs to convert the values to the right type. This function converts str to type."""
    type_list = [str, int, float, np.ndarray, list, dict]
    for value in config_dict.values():
        try:
            value = type_list[str(type_list).index(value)]
        except:
            print('TypeError: str_to_type cannot interpret type "{}" .'.format(value))
    return config_dict


def dict_to_list(dictionary):
    """Converts a dictionary of subdictionaries into a list of subdictionaries."""
    dictlist = []
    for key, value in dictionary.items():
        temp = key, value
        dictlist.append(temp)
    return dictlist


def flatten_list(nested_list):
    """
    Flatten an arbitrarily nested list, without recursion (to avoid
    stack overflows). Returns a new list, the original list is unchanged.

    Example:
        >> list(flatten_list([1, 2, 3, [4], [], [[[[[[[[[5]]]]]]]]]]))
        [1, 2, 3, 4, 5]
        >> list(flatten_list([[1, 2], 3]))
        [1, 2, 3]

    Args:
        nested_list (list)

    Returns:
        flatten list
    """
    nested_list = list(nested_list)
    nested_list = deepcopy(nested_list)

    while nested_list:
        sublist = nested_list.pop(0)
        if isinstance(sublist, list):
            nested_list = sublist + nested_list
        elif isinstance(sublist, tuple):
            nested_list = list(sublist) + nested_list
        else:
            yield sublist


def loopable(var):
    """
    Check if a variable belongs to (list, tuple, set, numpy.ndarray) 
    - 'loopable' in the simplest way
    - I don't call it iterable because it would include other objects

    Example:
        [2] --> True
        2 --> False

    Args:
        var (any type): arbitrary variable

    Returns:
        boolean 
    """
    types = (list, tuple, set, np.ndarray)
    return isinstance(var, types)


def squeeze_list(nested_list):
    """
    Squeeze any list, tuple or set = get rid of the extra layers
    Note: it does not squeeze each element, only the input list
    If the input is not a list, tuple or set, it returns a deepcopy of the input

    Example:
        [[2]] --> 2
        [2] --> 2
        2 --> 2
        [[3,4],[2]] --> [[3,4],[2]]
        [[ [[3,4]], [2] ]] --> [ [[3,4]], [2] ]

    Args:
        nested_list (arbitrary type): target variable to squeeze

    Returns:
        squeezed list or the same input
    """
    if loopable(nested_list):
        nlist = list(nested_list)
        nlist = deepcopy(nlist)
        length = len(nlist)
        while length == 1:
            nlist = nlist.pop(0)
            if isinstance(nlist, list):
                length = len(nlist)
            elif isinstance(nlist, (tuple, set)):
                length = len(nlist)
                nlist = list(nlist)
            else:
                length = 0
        return nlist
    else:
        nlist = deepcopy(nested_list)
        return nlist


def deep_squeeze(nested_list):
    """
    Squeeze the input at all levels using recursive technique.
    Returns a new list

    Example:
        [[2]] --> 2
        [[3,4],[2]] --> [[3,4],[2]]
        [[ [[3,4]], [2] ]] --> [ [3,4], 2 ]
        [ [[3,4, (2)]], [[2,[3,4]]] --> [ [3,4,2], [2,[3,4] ]

    Args:
        nested_list (arbitrary)

    Returns:
        A new list squeezed if possible, else a deepcopy of the input
    """

    def recursive_squeeze(item):
        item = squeeze_list(item)
        if loopable(item):
            for i, it in enumerate(item):
                it = squeeze_list(it)
                it = recursive_squeeze(it)
                item[i] = it
        return item

    new_list = recursive_squeeze(nested_list)
    return new_list


def string_to_list(string, delimiter=',', remove=[' ']):
    clean = str(string)
    for remove_i in remove:
        clean = clean.replace(remove_i, '')
    split = clean.split(delimiter)
    last = split[-1]
    if not last:
        split.pop(-1)
    return split


def lower_keys(dict_):
    ndict = {}
    for key, value in dict_.items():
        value = bytes_to_string(value)
        ndict[key.lower()] = value
    return ndict


def repr_args(dict_):
    args = [f'{key}={value}' for key, value in dict_.items()]
    args = join_list(args, ',')
    return args


"""
For nested get/set/hasattrs
From: https://stackoverflow.com/questions/31174295/getattr-and-setattr-on-nested-objects/31174427?noredirect=1#comment86638618_31174427
"""


def rsetattr(obj, attr, val):
    pre, _, post = attr.rpartition('.')
    return setattr(rgetattr(obj, pre) if pre else obj, post, val)


def rgetattr(obj, attr, *args):
    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    return functools.reduce(_getattr, [obj] + attr.split('.'))


def rhasattr(obj, attr, *args):
    try:
        rgetattr(obj, attr, *args)
        return True
    except:
        return False


if __name__ == '__main__':
    pass
