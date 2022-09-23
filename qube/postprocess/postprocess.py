import numpy as np
from scipy.signal import savgol_filter

from qube.postprocess.dataset import Axis

def create_name(name, suffix=None, prefix=None):
    elements = []
    if prefix:
        elements.append(str(prefix))
    elements.append(str(name))
    if suffix:
        elements.append(str(suffix))
    name = '_'.join(elements)
    return name


def duplicate_dataset(dataset, suffix=None, prefix=None, custom_name=None):
    new_ds = dataset.copy(shallow_copy=False)
    if custom_name:
        name = custom_name
    else:
        name = dataset.name
    new_ds.name = create_name(name, suffix, prefix)
    return new_ds


def remove_dim_in_axes(axes, dim=None):
    new_axes = []
    if dim is not None:
        for si in axes:
            ax = si.copy(shallow_copy=False)
            if si.dim != dim and si.dim > dim:
                ax.dim = si.dim - 1
                new_axes.append(ax)
            elif si.dim < dim:
                new_axes.append(ax)
    return new_axes


def histogram1d(dataset, bins=10, range=None, normed=None, weights=None, density=None):
    ds = dataset.copy()
    ds.name = f'{ds.name}_hist1d'
    hist, bins = np.histogram(
        ds.value,
        bins=bins,
        range=range,
        normed=normed,
        weights=weights,
        density=density,
    )
    bins = bins[:-1]  # remove 1 point for ax.plot

    axis = Axis(
        name=ds.name,
        value=bins,
        unit=ds.unit,
        dim=0,
    )
    ds.value = hist
    ds.unit = 'Counts'
    ds.axes = {axis.name: axis}
    return ds


def take(dataset, indices, axis=None):
    ds = dataset.copy()
    ds.name = f'{ds.name}_take'
    ds.value = np.take(ds.value, indices=indices, axis=axis)
    old_axes = ds.get_axes(counters=False)
    ds.clear_axes()
    if axis is not None:
        for si in old_axes:
            ax = si.copy(shallow_copy=False)
            if si.dim == axis:
                ax.value = np.take(ax.value, indices=indices)
                ds.add_axis(ax)
            elif si.dim < axis or si.dim > axis:
                ds.add_axis(ax)
    return ds


def mean(dataset, axis=None):
    ds = dataset.copy()
    ds.name = f'{ds.name}_mean'
    ds.value = np.mean(ds.value, axis=axis)
    old_axes = ds.get_axes(counters=False)
    ds.clear_axes()
    new_axes = remove_dim_in_axes(old_axes, axis)
    for ax in new_axes:
        ds.add_axis(ax)
    return ds


def nanmean(dataset, axis=None):
    ds = dataset.copy()
    ds.name = f'{ds.name}_nanmean'
    ds.value = np.nanmean(ds.value, axis=axis)
    old_axes = ds.get_axes(counters=False)
    ds.clear_axes()
    new_axes = remove_dim_in_axes(old_axes, axis)
    for ax in new_axes:
        ds.add_axis(ax)
    return ds


def subtract(dataset1, dataset2):
    ds1 = dataset1.copy()
    ds2 = dataset2
    ds1.value = ds1.value - ds2.value
    ds1.name = f'{ds1.name}-{ds2.name}'
    return ds1


def gradient(dataset, axis=None, edge_order=1):
    ds = dataset.copy()
    ds.name = f'{ds.name}_grad'
    ds.unit = f'd {ds.unit}'
    ds.value = np.gradient(ds.value, axis=axis, edge_order=edge_order)
    old_axes = ds.get_axes(counters=False)
    ds.clear_axes()
    if axis is not None:
        for si in old_axes:
            ax = si.copy(shallow_copy=False)
            ds.add_axis(ax)
    return ds

def smooth(dataset, window=5, order=3, axis=-1,**kwargs):
    ds = dataset.copy()
    ds.name = f'{ds.name}_smooth'
    ds.value = savgol_filter(ds.value, window_length=window, polyorder=order, axis=axis, **kwargs)
    old_axes = ds.get_axes(counters=False)
    ds.clear_axes()
    if axis is not None:
        for si in old_axes:
            ax = si.copy(shallow_copy=False)
            ds.add_axis(ax)
    return ds

def fft(
    dataset,
    axis=-1, 
    as_period=False, # return "xdata" as period instead of frequency
    no_dc_offset=True, # take out point at 0 frequency
    only_positive=True, # get only positive frequencies
    **kwargs
):
    ds_amp = dataset.copy()
    ds_amp.name = f'{ds_amp.name}_fftamp'
    ds_amp.unit = f'{ds_amp.unit}'
    ds_pha = dataset.copy()
    ds_pha.name = f'{ds_pha.name}_fftpha'
    ds_pha.unit = f'rad'
    
    old_axes = dataset.get_axes(counters=False)
    ds_amp.clear_axes()
    ds_pha.clear_axes()
    
    if as_period:
        no_dc_offset = True
    
    if no_dc_offset:
        ind0 = 1
    else:
        ind0 = 0

    axs = []
    for old_axis in old_axes:
        ax = old_axis.copy(shallow_copy=False)
        if ax.dim == axis:
            
            
            N = len(ax.value)
            Nhalf = int(N/2)
            
            if only_positive:
                ind1 = Nhalf
            else:
                ind1 = N
            
            xdata_freq = np.fft.fftfreq(len(ax.value), np.abs(ax.value[1] - ax.value[0]))[ind0:ind1]
            if not as_period:
                ax.name = f'{ax.name}_fftfreq'
                ax.unit = f'1/{ax.unit}'
                ax.value = xdata_freq
                print(ax.unit)
            else:
                ax.name = f'{ax.name}_fftper'
                ax.unit = f'{ax.unit}'
                ax.value = 1.0 / xdata_freq

        axs.append(ax)        

        
    data2analyse = np.moveaxis(dataset.value, axis, 0)
    value_complex = np.fft.fft(data2analyse,axis=0,**kwargs)
    value_complex = value_complex[ind0:ind1,Ellipsis]
    value_complex = np.moveaxis(value_complex, 0, axis)
    
    ds_amp.value = np.abs(value_complex)
    ds_pha.value = np.angle(value_complex)
    
    for ax in axs:
        ds_amp.add_axis(ax)
        ds_pha.add_axis(ax)
        
    return ds_amp,ds_pha

def value_mask_by_range(dataset, init, final, value, unit=None):
    ds = dataset.copy()
    ds.name = f'{ds.name}_vmasked'
    if init <= final:
        f1 = np.greater_equal
        f2 = np.less_equal
    else:
        f1 = np.less_equal
        f2 = np.greater_equal
    idxs_1 = f1(ds.value, init)
    idxs_2 = f2(ds.value, final)
    idxs = np.logical_and(idxs_1, idxs_2)

    new_value = np.array(ds.value)
    new_value[idxs] = value
    ds.value = new_value
    ds.unit = unit
    return ds


def value_mask_by_bounds(dataset, bounds, values, unit=None):
    ds = dataset.copy()
    ds.name = f'{ds.name}_vmasked'

    " Verify length of bounds and values"
    bounds = np.array(bounds)
    values = np.array(values)
    valid_length = len(values) == len(bounds) + 1
    if not valid_length:
        raise ValueError('len(values) must be len(bounds) + 1)')

    " Verify that bounds increase or decrease "
    comparison = [left < right for left, right in zip(bounds[0:-1], bounds[1:])]
    comparison = np.array(comparison)
    reduced_comp = list(set(comparison))
    valid_slope = len(reduced_comp) == 1
    if not valid_slope:
        raise ValueError('bounds must increase or decrease')

    " Sort bounds and values to increase "
    if reduced_comp[0] is False:
        idxs_sorted = np.argsort(bounds)
        bounds = np.sort(bounds)
        values = values[idxs_sorted]

    " Apply mask "
    n_bulk = len(values) - 2
    new_values = np.zeros_like(ds.value)
    for i, vi in enumerate(values):
        if i == 0:
            idxs = np.less(ds.value, bounds[i])
        elif i < n_bulk:
            idxs_left = np.greater_equal(ds.value, bounds[i - 1])
            idxs_right = np.less_equal(ds.value, bounds[i])
            idxs = np.logical_and(idxs_left, idxs_right)
        else:
            idxs = np.greater(ds.value, bounds[i - 1])
        new_values[idxs] = vi

    ds.value = new_values
    ds.unit = unit
    return ds


def boolmask(dataset, value, key='=='):
    ds = dataset.copy()
    ds.name = f'{ds.name}_bmasked'
    if key == '==':
        ds.value = ds.value == value
    if key == '>=':
        ds.value = ds.value >= value
    if key == '<=':
        ds.value = ds.value <= value
    if key == '!=':
        ds.value = ds.value != value
    if key == '>':
        ds.value = ds.value > value
    if key == '<':
        ds.value = ds.value < value
    ds.unit = 'boolean'
    return ds


def probability(dataset, value, key='==', axis=None):
    ds = dataset.copy()
    ds.name = f'{ds.name}_prob'
    ds_bool = boolmask(ds, value, key=key)
    boolv = ds_bool.value

    ds.value = np.apply_along_axis(_prob, axis=axis, arr=boolv)
    ds.unit = '%'
    old_axes = ds.get_axes(counters=False)
    ds.clear_axes()
    new_axes = remove_dim_in_axes(old_axes, dim=axis)
    for ax in new_axes:
        ds.add_axis(ax)
    return ds


def _prob(arr):
    total_counts = arr.size
    nonzero_counts = np.count_nonzero(arr)
    if total_counts >= 0:
        prob = 1. * nonzero_counts / total_counts * 100.
    else:
        prob = 0
    return prob


if __name__ == '__main__':
    pass
    bonds = [-1, 0, 1, 2]
    values = [0, 1, 2, 3, 4]
