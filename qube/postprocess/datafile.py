import json
import os
from typing import List

import numpy as np

from qube.postprocess.dataset import Dataset, Axis, Static
from qube.utils.path import is_file, get_filename, get_folder, remove_extension, mkdir_if_not_exist, \
    find_unused_in_folder


class Datafile(object):
    def __init__(self, fullpath=None):
        self.datasets = []
        self.statics = {}
        self.fullpath = None
        if fullpath:
            self.set_fullpath(fullpath)
            self.load(fullpath)

    @property
    def filename(self):
        return get_filename(self.fullpath, ext=False)

    @filename.setter
    def filename(self, filename):
        if not is_file(filename):
            fname = filename + '.json'
        else:
            fname = filename
        self.set_fullpath(os.path.join(self.folder, fname))

    @property
    def folder(self):
        return get_folder(self.fullpath)

    @folder.setter
    def folder(self, folder):
        folder = get_folder(folder)
        self.set_fullpath(os.path.join(folder, self.filename))

    @property
    def ds_names(self):
        names = [ds.name for ds in self.datasets]
        return names

    def set_fullpath(self, fullpath):
        folder = get_folder(fullpath)
        if folder == '':
            folder = os.getcwd()
        filename = get_filename(fullpath, ext=False)
        self.fullpath = os.path.join(folder, filename + '.json')
        return self.fullpath

    def clear_datasets(self):
        self.datasets = []

    def add_dataset(self, dataset):
        if isinstance(dataset, Dataset):
            self.datasets.append(dataset)
        else:
            raise Exception(f'dataset must be an instance of {Dataset}')

    def add_datasets(self, *datasets):
        for ds in datasets:
            self.add_dataset(ds)

    def get_datasets_by_name(self, name, exact_match=False):
        datasets = []
        for dsi in self.datasets:
            ds_name = dsi.name
            if exact_match and ds_name == name:
                datasets.append(dsi)
            elif not exact_match and name in ds_name:
                datasets.append(dsi)
        return datasets

    def remove_datasets_by_name(self, name, exact_match=False):
        datasets = self.datasets
        new_datasets = []
        for dsi in datasets:
            remove = False
            ds_name = dsi.name
            if exact_match and ds_name == name:
                remove = True
            elif not exact_match and name in ds_name:
                remove = True
            if not remove:
                new_datasets.append(dsi)
        self.clear_datasets()
        self.add_datasets(*new_datasets)

    def get_dataset(self, name):
        datasets = self.get_datasets_by_name(name, exact_match=False)
        if len(datasets) == 0:
            raise KeyError(f'"{name}" dataset not found')
        else:
            return datasets[0]

    def remove_dataset(self, name):
        self.remove_datasets_by_name(name, exact_match=False)

    def clear_statics(self):
        self.statics = {}

    def add_statics(self, statics: List[Static], key: str):
        for st in statics:
            if not isinstance(st, Static):
                raise Exception(f'dataset must be an instance of {Static}')
        self.statics[key] = statics

    def get_statics_by_name(self, name, key=None, exact_match=False):
        statics = []
        keys = self.statics.keys() if key is None else [key]
        for key in keys:
            for dsi in self.statics[key]:
                ds_name = dsi.name
                if exact_match and ds_name == name:
                    statics.append(dsi)
                elif not exact_match and name in ds_name:
                    statics.append(dsi)
        return statics

    def remove_statics_by_name(self, name, key=None, exact_match=False):
        new_statics = []
        keys = self.statics.keys() if key is None else [key]
        for key in keys:
            for dsi in self.statics[key]:
                remove = False
                ds_name = dsi.name
                if exact_match and ds_name == name:
                    remove = True
                elif not exact_match and name in ds_name:
                    remove = True
                if not remove:
                    new_statics.append(dsi)
        self.clear_datasets()
        self.add_datasets(*new_statics)

    def get_static(self, name, key):
        statics = self.get_statics_by_name(name, key=key, exact_match=False)
        if len(statics) == 0:
            raise KeyError(f'"{name}" dataset not found')
        else:
            return statics[0]

    def remove_static(self, name, key):
        self.remove_statics_by_name(name, key=key, exact_match=False)

    def load(self, fullpath=None):
        if fullpath is None:
            fullpath = self.fullpath
        else:
            self.fullpath = self.set_fullpath(fullpath)
        info = self.load_json(fullpath)
        arrs = self.load_npz(fullpath)
        self.clear_datasets()

        datasets = []
        for ds_key, ds_info in info.items():
            dataset = Dataset(
                name=ds_info['name'],
                unit=ds_info['unit'],
                metadata=ds_info['metadata'],
                offset=ds_info['offset'],
                conversion_factor=ds_info['conversion_factor'],
                value=arrs[ds_key],
            )
            for ax_key, ax_info in ds_info.items():
                if 'ax' not in ax_key:
                    continue
                ax_info['value'] = arrs[f'{ds_key}_{ax_key}']
                axis = Axis(**ax_info)
                dataset.add_axis(axis)
            datasets.append(dataset)
        self.datasets = datasets
        return datasets

    def load_json(self, fullpath):
        fullpath = self.get_json_path(fullpath)
        with open(fullpath, 'r') as file:
            info = json.load(file)
        return info

    def load_npz(self, fullpath):
        fullpath = self.get_npz_path(fullpath)
        arrs = np.load(fullpath)
        return arrs

    def save(self, fullpath=None, overwrite=False, automkdir=True):
        if fullpath is None:
            fpath = self.fullpath
        else:
            fpath = self.set_fullpath(fullpath)
        if automkdir:
            mkdir_if_not_exist(fpath)
        fpath = find_unused_in_folder(fpath, overwrite)
        self.set_fullpath(fpath)
        self.save_json(self.fullpath)
        self.save_npz(self.fullpath)

    def save_json(self, fullpath):
        fullpath = self.get_json_path(fullpath)
        info = {}
        for i, dataset in enumerate(self.datasets):
            key = f'ds{i}'
            info[key] = dataset.get_dict()
        with open(fullpath, 'w') as file:
            json.dump(info, file)

    def save_npz(self, fullpath):
        fullpath = self.get_npz_path(fullpath)
        arrs = {}
        for i, dataset in enumerate(self.datasets):
            key_ds = f'ds{i}'
            arrs[key_ds] = dataset.raw_value
            ds_axes = dataset.get_axes(counters=False)
            for j, axis in enumerate(ds_axes):
                key_ax = f'{key_ds}_ax{j}'
                arrs[key_ax] = axis.raw_value
        np.savez(fullpath, **arrs)

    def get_json_path(self, fullpath):
        _f = remove_extension(fullpath)
        path = f'{_f}.json'
        return path

    def get_npz_path(self, fullpath):
        _f = remove_extension(fullpath)
        path = f'{_f}.npz'
        return path

    def __repr__(self):
        out = []
        out.append(f'{self.__class__.__name__}')
        out.append(f'fullpath: {self.fullpath}')
        out.append(f'statics: {len(self.statics)} elements (keys: {list(self.statics.keys())})')
        out.append(f'datasets: {len(self.datasets)} elements')
        for i, dataset in enumerate(self.datasets):
            out.append(f'[{i}] {str(dataset)}')
            ds_axes = dataset.get_axes(counters=True)
            out.append(f'\taxes: {len(ds_axes)} elements')
            for j, axis in enumerate(ds_axes):
                out.append(f'\t[{j}] {str(axis)}')
        out = '\n'.join(out)
        return out

    def __getitem__(self, item):
        if isinstance(item, int):
            return self.datasets[item]
        if isinstance(item, str):
            return self.get_dataset(item)

    def __iter__(self):
        self._iter_index = 0
        return self

    def __next__(self):
        try:
            result = self.datasets.__getitem__(self._iter_index)
        except (IndexError, KeyError):
            raise StopIteration
        self._iter_index += 1
        return result


def save_datasets(fullpath, *datasets, overwrite=False, automkdir=True):
    df = Datafile()
    for ds in datasets:
        df.add_dataset(ds)
    df.save(fullpath, overwrite=overwrite, automkdir=automkdir)


def load_datafile(fullpath):
    df = Datafile()
    df.load(fullpath)
    return df


def load_datasets(fullpath):
    df = load_datafile(fullpath)
    return df.datasets


if __name__ == '__main__':
    fullpath = os.path.join('tests', 'datafile_test.json')

    ds0 = Dataset('test', unit='V', value=np.arange(100))
    ds1 = Dataset('test2', unit='nm', value=np.arange(100).reshape((2, 50)))
    ax0 = Axis('ax0', value=np.arange(100) - 50, dim=0)
    ax1 = Axis('ax1', value=np.arange(100) - 100, dim=0)
    ds0.add_axis(ax0)
    ds0.add_axis(ax1)
    file = Datafile()
    file.add_dataset(ds0)
    file.add_dataset(ds1)
    # file.save(fullpath, overwrite=False)

    # f2 = Datafile()
    # f2.load(file.fullpath)
    # dsets = f2.datasets
    # print(dsets)
