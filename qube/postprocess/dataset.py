import numpy as np
from copy import copy, deepcopy

default_unit = 'a.u.'


class Data(object):
    """
    This class stores any kind of information from experimental data

    ...

    Parameters
    ----------
    name : str
        name of the dataset
    value : not defined
        stored value
    unit : str, optional
        unit of the value (default is None)
    metadata : dict, optional
        extra information (default is {})
    label_fmt : method, optional
        formatting label with label_fmt(name, unit) (default is None)
        If it is None, label_fmt = lambda name, unit: f'{name} ({unit})'

    Attributes
    ----------
    name : str
        name of the dataset
    value : not defined
        stored value
    unit : str
        unit of the value (default is None)
    metadata : dict
        extra information (default is {})
    label_fmt : method
        formatting label with label_fmt(name, unit) (default is None)
        If it is None, label_fmt = lambda name, unit: f'{name} ({unit})'
    """

    def __init__(self, name, value, unit=None, metadata={}, label_fmt=None, *args,
                 **kwargs):
        self._unit = default_unit
        self.name = str(name)
        self._value = value
        self.unit = unit
        if label_fmt is None:
            label_fmt = lambda name, unit: f'{name} ({unit})'
        self.label_fmt = label_fmt
        self.metadata = metadata

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = v

    @property
    def label(self):
        return self.label_fmt(self.name, self.unit)

    @property
    def unit(self):
        return self._unit

    @unit.setter
    def unit(self, value):
        if value is None or value == '':
            self._unit = default_unit
        else:
            self._unit = str(value)

    def copy(self, shallow_copy=False):
        if shallow_copy:
            c = copy(self)
        else:
            c = deepcopy(self)
        return c

    def get_dict(self):
        d = {}
        params = ['name', 'unit', 'metadata']
        for p in params:
            if hasattr(self, p):
                d[p] = getattr(self, p)
        return d

    def __repr__(self):
        cname = self.__class__.__name__
        out = f'{cname} - {str(self)}'
        return out

    def __str__(self):
        return f'name: {self.name} - unit: {self.unit} - value: {self.value}'


class ArrayData(Data):
    """
    This class stores array data
    """

    def __init__(self, name, value, offset=None, conversion_factor=None, **kwargs):
        super().__init__(name, value, **kwargs)
        self.offset = None
        self.conversion_factor = None
        self.set_offset(offset)
        self.set_conversion_factor(conversion_factor)

    @property
    def value(self):
        v = np.array(self._value)
        if self.conversion_factor is not None:
            v = v * self.conversion_factor
        if self.offset is not None:
            v = v + self.offset
        return v

    @value.setter
    def value(self, v):
        self._value = v

    @property
    def raw_value(self):
        return self._value

    @property
    def ndim(self):
        return self.value.ndim

    def set_offset(self, offset):
        if offset is not None:
            offset = float(offset)
        self.offset = offset

    def set_conversion_factor(self, factor):
        if factor is not None:
            factor = float(factor)
        self.conversion_factor = factor

    def get_dict(self):
        d = super().get_dict()
        extra_params = ['offset', 'conversion_factor']
        for p in extra_params:
            if hasattr(self, p):
                d[p] = getattr(self, p)
        return d


class Static(ArrayData):
    """
    This class stores a single array data.
    TODO: it does not need to be a array
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self):
        return f'name: {self.name} - unit: {self.unit} - value: {self.value}'


class Axis(ArrayData):
    """
    This class stores axis values for datasets.

    ...

    Parameters
    ----------
    name : str
        name of the dataset
    value : not defined
        stored value
    dim : int
        dim for the Variable.value
        For example, for a dataset of (100, 2) and a coordinate x of 100 pts, dim = 0
    unit : str, optional
        unit of the value (default is None)
    offset : not defined, optional
        offset to be added to value (default is 0)
    metadata : dict, optional
        extra information (default is {})
    label_fmt : method, optional
        formatting label with label_fmt(name, unit) (default is None)
        If it is None, label_fmt = lambda name, unit: f'{name} ({unit})'

    Attributes
    ----------
    name : str
        name of the dataset
    value : not defined
        stored value
    dim : int
        dim for the Variable.value
        For example, for a dataset of (100, 2) and a coordinate x of 100 pts, dim = 0
    unit : str
        unit of the value (default is None)
    offset : not defined
        offset to be added to value (default is 0)
    metadata : dict
        extra information (default is {})
    label_fmt : method
        formatting label with label_fmt(name, unit) (default is None)
        If it is None, label_fmt = lambda name, unit: f'{name} ({unit})'

    """

    def __init__(self, name, value, dim=None, **kwargs):
        super().__init__(name, value, **kwargs)
        self._dim = None
        self.dim = dim

    @property
    def dim(self):
        return self._dim

    @dim.setter
    def dim(self, value):
        if isinstance(value, int) and value >= 0:
            self._dim = value
        elif value is None:
            self._dim = value
        else:
            raise ValueError(f'dim must be an integer > 0 or None')

    @property
    def counter(self):
        return np.arange(len(self.value), dtype=int)

    def __str__(self):
        return f'name: {self.name} - unit: {self.unit} - shape: {self.value.shape} - dim: {self.dim}'

    def get_dict(self):
        d = super().get_dict()
        d['dim'] = self.dim
        return d


class Dataset(ArrayData):
    def __init__(self, name, value, axes=[], **kwargs):
        super().__init__(name, value, **kwargs)
        self._axes = []
        self.axes = axes

    @property
    def axes(self):
        return self.get_axes(counters=True)

    @axes.setter
    def axes(self, axes):
        self.clear_axes()
        if isinstance(axes, dict):
            axes = axes.values()
        for axis in axes:
            self.add_axis(axis)

    @property
    def counter_axes(self):
        ndim = self.value.ndim
        axes = []
        for dim in range(ndim):
            name = f'counter_dim{dim}'
            value = np.arange(self.value.shape[dim], dtype=int)
            cax = Axis(name=name, value=value, dim=dim, unit=None, offset=0, instrument=None, metadata={})
            axes.append(cax)
        return axes

    def add_axis(self, axis):
        if isinstance(axis, Axis):
            if self.is_valid_axis(axis):
                self._axes.append(axis)
        else:
            raise ValueError(f'axis has to be an instance of {Axis}')

    def add_axes(self, *axis):
        for ax in axis:
            self.add_axis(ax)

    def is_valid_axis(self, axis):
        b = False
        if axis.value.size in self.value.shape and axis.dim <= self.value.ndim - 1:
            if axis.value.size == self.value.shape[axis.dim]:
                b = True
        return b

    def get_axes(self, counters=True):
        s = []
        for si in self._axes:
            s.append(si)
        if counters:
            s.extend(self.counter_axes)
        return s

    def clear_axes(self):
        self._axes = []

    def get_dict(self):
        d = super().get_dict()
        axes = self.get_axes(counters=False)
        for i, axis in enumerate(axes):
            key = f'ax{i}'
            d[key] = axis.get_dict()
        return d

    def get_axes_by_name(self, name, exact_match=True):
        axes = []
        for dsi in self.axes:
            ds_name = dsi.name
            if exact_match and ds_name == name:
                axes.append(dsi)
            elif not exact_match and name in ds_name:
                axes.append(dsi)
        return axes

    def remove_axes_by_name(self, name, exact_match=True):
        axes = self.get_axes(counters=False)
        new_axes = []
        for ax in axes:
            remove = False
            ax_name = ax.name
            if exact_match and ax_name == name:
                remove = True
            elif not exact_match and name in ax_name:
                remove = True
            if not remove:
                new_axes.append(ax)
        self.clear_axes()
        self.add_axes(*new_axes)

    def get_axis(self, name):
        axes = self.get_axes_by_name(name, exact_match=True)
        if len(axes) == 0:
            raise KeyError(f'"{name}" axis not found')
        else:
            return axes[0]

    def remove_axis(self, name):
        self.remove_axes_by_name(name, exact_match=True)

    def __str__(self):
        return f'name: {self.name} - unit: {self.unit} - shape: {self.value.shape}'

    def __repr__(self):
        out = []
        out.append(str(self))
        out.append(f'axes: {len(self.axes)} elements')
        for i, axis in enumerate(self.axes):
            out.append(f'\t[{i}] {str(axis)}')
        out = '\n'.join(out)
        return out


class Sequence(Data):
    """
    """

    def __init__(self, name, slots, **kwargs):
        super().__init__(name, slots, **kwargs)

    @property
    def slots(self):
        return self.value

    def get_instructions(self):
        instructions = [slot.name for slot in self.slots.values()]
        return instructions

    def get_values(self):
        values = [slot.value for slot in self.slots.values()]
        return values

    def get_raw_values(self):
        values = [slot.raw_value for slot in self.slots.values()]
        return values

    def __repr__(self):
        out = []
        out.append('{')
        for index, slot in self.value.items():
            out.append(f'{index}: {slot.__repr__()}')
        out.append('}')
        out = '\n'.join(out)
        return out

    def __getitem__(self, item):
        if isinstance(item, (int, slice)):
            slots = list(self.value.values())
            return slots[item]
        elif item in self.value.keys():
            return self.value[item]
        else:
            raise ValueError('Index is not valid')

    def __setitem__(self, item, value):
        self.value[item] = value

    def __delitem__(self, item):
        del self.value[item]

    def __str__(self):
        return f'name: {self.name} - unit: {self.unit} - value: {self.value}'


class SequenceSlot(ArrayData):
    """
    """

    def __init__(self, name, value, index, static=None, **kwargs):
        super().__init__(name, value, offset=0, conversion_factor=1, **kwargs)
        self._index = None
        self.index = index
        self.static = static
        if static:
            self.offset = self.get_offset_from_static()

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, value):
        if isinstance(value, int) and value >= 0:
            self._index = value
        elif value is None:
            self._index = value
        else:
            raise ValueError(f'index must be an integer > 0 or None')

    def get_offset_from_static(self):
        if hasattr(self.static, 'value'):
            offset = self.static.value
        else:
            offset = 0
        return float(offset)

    def is_static(self):
        try:
            length = len(self.value)
            if length == 1:
                static = True
        except:
            static = False
        return static

    def __str__(self):
        return f'name: {self.name} - unit: {self.unit} - value: {self.value}'


class Segment(Data):
    """
    This class stores experimental parameters.

    """

    def __init__(self, name, value, **kwargs):
        super().__init__(name, value, **kwargs)

    def __str__(self):
        return f'name: {self.name} - value: {self.value}'


if __name__ == '__main__':
    ds = Dataset('ds', value=[0, 1])
    s1 = Axis('ax1', value=[1, 2], dim=0)
    s2 = Axis('ax2', value=[2, 3], dim=0)
    ds.add_axis(s1)
    ds.add_axis(s2)
