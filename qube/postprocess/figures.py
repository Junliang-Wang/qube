import os
import ipywidgets as widgets
from ipywidgets import HBox, VBox, Layout
from IPython.display import display
import matplotlib.pyplot as plt
import numpy as np

from qube.postprocess.axes import FigAxis, SliderStackAxis
from qube.postprocess.dataset import Dataset

save_options = {
    'folder': '',
    'extension': 'png',
    'kwargs': {'dpi': 100, 'bbox_inches': 'tight'},
}


class PlotBase(object):
    layout_button = Layout(width='100px')
    layout_title = Layout(width='400px')

    def __init__(self, datasets={}, save_options=save_options, figdim=1, init_keys=[], title_prefix='figure', *args,
                 **kwargs):
        self.widgets = {}
        self.figaxes = []
        self.x_widget = None
        self.y_widget = None
        self.z_widget = None
        self.fig = None
        self.ax = None
        self.saxes_text = None
        self.init_keys = init_keys

        self.title_prefix = title_prefix
        self.save_options = save_options
        if figdim in [1, 2]:
            self.figdim = figdim
        else:
            raise ValueError('figdim has to be 1 or 2')
        self.set_datasets(datasets)

        self.init_figure()
        self.init_widgets()

        self.display_widgets()

        self.dataset_changed()
        # self.callback_dataset_changed()

    @property
    def axes(self):
        return self.dataset.axes

    @property
    def dataset(self):
        return self.figaxes[0].get_dataset()

    @property
    def dataset_ndim(self):
        return self.dataset.value.ndim

    @property
    def saxes(self):
        init_idx = self.figdim + 1
        return self.figaxes[init_idx:]

    @property
    def nsaxes(self):
        ndim = self.dataset_ndim
        return ndim - self.figdim

    @property
    def x_dataset(self):
        out = None
        if hasattr(self.x_widget, 'dataset'):
            out = self.x_widget.dataset
        return out

    @property
    def y_dataset(self):
        out = None
        if hasattr(self.y_widget, 'dataset'):
            out = self.y_widget.dataset
        return out

    @property
    def z_dataset(self):
        out = None
        if hasattr(self.z_widget, 'dataset'):
            out = self.z_widget.dataset
        return out

    def set_datasets(self, datasets):
        self.clear_datasets()
        if hasattr(datasets, 'keys'):
            for key, ds in datasets.items():
                self.add_dataset(ds, key=key)
        else:
            for ds in datasets:
                self.add_dataset(ds)
        if len(self.figaxes) > 1:
            self.figaxes[0].set_datasets(self.datasets)

    def add_dataset(self, dataset, key=None):
        if isinstance(dataset, Dataset):
            if key is None:
                key = dataset.name
            if dataset.value.ndim >= self.figdim:
                self.datasets[key] = dataset

    def clear_datasets(self):
        self.datasets = {}

    """
    Methods related to widgets
    """

    def init_figure(self):
        self.fig, self.ax = plt.subplots(1)

    def init_widgets(self):
        self._create_fig_widgets()
        self._create_axes_widgets()
        self._set_callbacks()

    def _create_fig_widgets(self):
        self.widgets['plot'] = widgets.Button(description='plot', layout=self.layout_button)
        self.widgets['plot'].on_click(lambda b: self.plot())

        self.widgets['update'] = widgets.Button(description='update', layout=self.layout_button)
        self.widgets['update'].on_click(lambda b: self.update())

        self.widgets['save'] = widgets.Button(description='save', layout=self.layout_button)
        self.widgets['save'].on_click(lambda b: self.save())

        self.widgets['title'] = widgets.Text(value='', description='Title:', layout=self.layout_title)

        # self.widgets['test'] = widgets.Button(description='test_copy', layout=self.layout_button)
        # self.widgets['test'].on_click(lambda b: self._test_copy())

        self.widgets['box.fig'] = HBox([
            self.widgets['plot'],
            self.widgets['update'],
            self.widgets['save'],
            self.widgets['title'],
            # self.widgets['test'],
        ])

    def _create_axes_widgets(self):
        ds = FigAxis(self.datasets, name='dataset')
        self.figaxes.append(ds)

        ax1 = FigAxis(self.axes, name='x')
        self.x_widget = ax1
        self.figaxes.append(ax1)

        if self.figdim == 2:
            ax2 = FigAxis(self.axes, name='y')
            self.y_widget = ax2
            self.z_widget = ds
            self.figaxes.append(ax2)
        else:
            self.y_widget = ds
            self.z_widget = None

        box = []
        for fax in self.figaxes:
            box.append(fax.widgets['box'])
        self.widgets['box.figaxes'] = VBox(box)

    def _set_callbacks(self):
        self.figaxes[0].callback_dataset_changed = self.dataset_changed
        for i, ax in enumerate(self.figaxes[1:]):
            i += 1
            ax.callback_dataset_changed = self.get_set_valid_axes_func(idx=i)

    def set_keys(self, keys):
        df_keys = list(keys)
        all_keys = [None] * 3
        for i in range(3):
            if len(df_keys) >= i + 1:
                all_keys[i] = df_keys[i]
        if self.figdim == 2:
            ax_widgets = [self.z_widget, self.x_widget, self.y_widget]
        else:
            ax_widgets = [self.y_widget, self.x_widget, None]
        for wi, key in zip(ax_widgets, all_keys):
            if wi is not None and key is not None:
                wi.set_nearest_dataset(key)

    def display_widgets(self):
        display(self.widgets['box.fig'])
        display(self.widgets['box.figaxes'])

    def delete_widgets(self):
        for wi in self.widgets.values():
            try:
                wi.close()
            except:
                pass

        self.delete_figaxes()
        self.delete_saxes()

    def reset_saxes(self):
        self.delete_saxes()
        self.create_saxes()
        self.update_axes_widgets_container()

    def delete_figaxes(self):
        for fax in self.figaxes:
            fax.delete_widgets()

    def delete_saxes(self):
        for sax in self.saxes:
            sax.delete_widgets()
            self.figaxes.pop(self.figdim + 1)

    def create_saxes(self):
        for i in range(self.nsaxes):
            name = f'slider{i + 1}'
            sax = SliderStackAxis(self.axes, name=name)
            sax.callback_idx_changed = self.callback_slider_idx_changed
            idx = self.figdim + 1 + i
            sax.callback_dataset_changed = self.get_set_valid_axes_func(idx=idx)
            self.figaxes.append(sax)

    def update_axes_widgets_container(self):
        box = []
        for ax in self.figaxes:
            box.append(ax.widgets['box'])
        self.widgets['box.figaxes'].children = tuple(box)

    """
    Generic figure methods
    """

    def clear_figure(self):
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)

    def clear_ax(self):
        self.ax.clear()

    def clear_ax_lines(self):
        [self.ax.lines.pop(0) for _ in self.ax.lines]
        self.fig.canvas.draw_idle()

    def save(self):
        opts = self.save_options
        title = self.get_title()
        figpath = os.path.join(opts['folder'], f"{title}.{opts['extension']}")
        self.fig.savefig(figpath, **opts['kwargs'])

    def generate_title(self):
        prefix = self.title_prefix
        suffix = self.dataset.name
        figdim = f'{self.figdim}d'
        sax_suffix = self.generate_sax_title_suffix()
        title = f'{prefix}_{suffix}_{figdim}'
        if sax_suffix != '':
            title += f'_{sax_suffix}'
        return title

    def generate_sax_title_suffix(self):
        t = []
        for saxi in self.saxes:
            t.append(f'd{saxi.dim}i{saxi.cur_idx}')
        t = '_'.join(t)
        return t

    def generate_sax_info(self):
        t = []
        for saxi in self.saxes:
            t.append(f'{saxi.get_label()} = {saxi.cur_value:.4f}')
        t = '\n'.join(t)
        return t

    def get_title(self):
        return self.widgets['title'].value

    def set_title(self, value):
        self.widgets['title'].value = value

    def reset_title(self):
        self.widgets['title'].value = self.generate_title()

    def update_title(self):
        title = self.get_title()
        self.ax.set_title(title)

    def update_xy_labels(self):
        xlabel = self.x_widget.get_label()
        ylabel = self.y_widget.get_label()
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)

    def reset_xy_labels(self):
        self.x_widget.reset_label()
        self.y_widget.reset_label()

    def update_xy_lim(self):
        xlim = self.x_widget.get_lim()
        ylim = self.y_widget.get_lim()
        self.ax.set_xlim(xlim)
        self.ax.set_ylim(ylim)
        current_xlim = self.ax.get_xlim()
        current_ylim = self.ax.get_ylim()
        " Update widgets in case any previous lim was None "
        self.x_widget.set_lim(current_xlim)
        self.y_widget.set_lim(current_ylim)

    def reset_xy_lim(self):
        self.x_widget.reset_lim()
        self.y_widget.reset_lim()

    def update_saxes_text(self):
        use_stext = self.nsaxes >= 1
        if not use_stext:
            self.remove_saxes_text()
        else:
            info = self.generate_sax_info()
            if self.saxes_text is None:
                self.create_saxes_text()
            self.saxes_text.set_text(info)

    def remove_saxes_text(self):
        if hasattr(self.saxes_text, 'remove'):
            self.saxes_text.remove()
        self.saxes_text = None

    def create_saxes_text(self):
        xpos = 0.05
        ypos = 0.05 * self.nsaxes
        info = self.generate_sax_info()
        self.saxes_text = self.ax.text(xpos, ypos, info, transform=self.ax.transAxes,
                                       bbox=dict(facecolor='white', alpha=0.3))

    """
    Methods related to dataset and axes
    """

    def get_x_dataset(self):
        return self.x_dataset

    def get_y_dataset(self):
        return self.y_dataset

    def get_z_dataset(self):
        return self.z_dataset

    def set_dataset(self, key):
        for ds in self.datasets:
            if key in ds.name:
                self.dataset.set_dataset(key)
                break

    def dataset_changed(self):
        self.reset_saxes()
        self.figaxes[1].set_datasets(self.axes)
        self.figaxes[1].callback_dataset_changed()
        self.clear_figure()
        self.plot()
        self.callback_dataset_changed()

    def get_set_valid_axes_func(self, idx):
        def f():
            figaxes = self.get_figaxes()
            valid_axes = list(figaxes[idx].get_datasets().values())
            cur_axis = figaxes[idx].dataset
            valid_axes = find_valid_axes(self.dataset, cur_axis, valid_axes)
            next_idx = idx + 1
            if next_idx < len(figaxes):
                figaxes[next_idx].set_datasets(valid_axes)
                figaxes[next_idx].callback_dataset_changed()

        return f

    def set_valid_axes(self, idx=1):
        figaxes = self.get_figaxes()
        valid_axes = list(figaxes[idx].get_datasets().values())
        cur_axis = figaxes[idx].dataset
        valid_axes = find_valid_axes(self.dataset, cur_axis, valid_axes)
        next_idx = idx + 1
        if next_idx < len(figaxes):
            figaxes[next_idx].set_datasets(valid_axes)

    def get_figaxes(self):
        return self.figaxes

    def get_slice_idxs(self):
        idxs = [slice(None)] * self.dataset_ndim
        for saxi in self.saxes:
            dim = saxi.get_dataset().dim
            cidx = saxi.cur_idx
            idxs[dim] = cidx
        idxs = tuple(idxs)
        return idxs

    """
    Useful methods for child classes
    """

    def update(self):
        pass

    def plot(self):
        pass

    def callback_dataset_changed(self):
        pass

    def callback_slider_idx_changed(self):
        pass


class Plot1D(PlotBase):
    def __init__(self, *args, **kwargs):
        kwargs['figdim'] = 1
        super().__init__(*args, **kwargs)

    def plot(self):
        self.reset_xy_lim()
        self.reset_xy_labels()
        self.reset_title()
        self.remove_saxes_text()
        self.update()

    def update(self):
        self.clear_ax()
        self.update_line_plot()
        self.update_xy_labels()
        self.update_xy_lim()
        self.update_title()
        self.update_saxes_text()

    def update_line_plot(self):
        xv = np.array(self.x_dataset.value)
        yv = np.array(self.y_dataset.value)
        idxs = self.get_slice_idxs()
        yv = yv[idxs]
        self.ax.plot(xv, yv)

    def callback_slider_idx_changed(self):
        self.plot()


class Plot2D(PlotBase):
    def __init__(self, *args, **kwargs):
        kwargs['figdim'] = 2
        super().__init__(*args, **kwargs)

    @property
    def ax_pcolor(self):
        if len(self.ax.collections) >= 1:
            pcolor = self.ax.collections[0]
        else:
            pcolor = None
        return pcolor

    @property
    def ax_cbar(self):
        if hasattr(self.ax_pcolor, 'colorbar'):
            cbar = self.ax_pcolor.colorbar
        else:
            cbar = None
        return cbar

    def plot(self):
        try:
            self.reset_xy_lim()
            self.reset_z_lim()
            self.reset_xy_labels()
            self.reset_z_label()
            self.reset_title()
            self.remove_saxes_text()
            self.clear_figure()
            if self.ax_pcolor is None:
                self.create_pcolor()
            self.update()
        except:
            pass

    def update(self):
        self.update_pcolor()
        self.update_xy_labels()
        self.update_xy_lim()
        self.update_z_lim()
        self.update_z_label()
        self.update_title()
        self.update_saxes_text()

    def create_pcolor(self):
        xv, yv, zv = self.get_pcolor_xyz_values()
        self.ax.pcolormesh(xv, yv, zv, shading='auto')
        fmt = lambda x, y: xyz_format_coord(x, y, xarr=xv, yarr=yv, zarr=zv, prec=4, show_indexes=False)
        self.ax.format_coord = fmt

    def update_pcolor(self):
        xv, yv, zv = self.get_pcolor_xyz_values()
        zv = zv.ravel()
        self.ax_pcolor.set_array(zv)
        self.fig.canvas.draw_idle()

    def reset_z_lim(self):
        self.z_widget.reset_lim()

    def update_z_lim(self):
        if self.ax_cbar is None:
            self.fig.colorbar(self.ax_pcolor, ax=self.ax, extend='both')
        zlim = self.z_widget.get_lim()
        self.ax_pcolor.set_clim(zlim)
        current_zlim = self.ax_pcolor.get_clim()
        " Update widgets in case any previous lim was None "
        self.z_widget.set_lim(current_zlim)

    def update_z_label(self):
        label = self.z_widget.get_label()
        self.ax_cbar.set_label(label)

    def reset_z_label(self):
        self.z_widget.reset_label()

    def get_pcolor_xyz_values(self):
        xv = np.array(self.x_dataset.value)
        yv = np.array(self.y_dataset.value)
        zv = np.array(self.z_dataset.value)

        idxs = self.get_slice_idxs()
        zv = zv[idxs]
        zv_dims = np.where(np.array(idxs) == slice(None))[0]
        xdim = self.x_dataset.dim
        ydim = self.y_dataset.dim
        if xdim == zv_dims[0] and ydim == zv_dims[1]:
            zv = zv.T
        return xv, yv, zv

    def callback_slider_idx_changed(self):
        self.update_pcolor()
        self.reset_title()
        self.update_title()
        self.update_saxes_text()


def find_valid_axes(dataset, cur_axis, axes):
    ds_shape = np.array(dataset.value.shape)
    cur_size = cur_axis.value.size
    valid_sizes = list(ds_shape)
    valid_dims = list(range(dataset.value.ndim))
    cur_dim = None

    if cur_axis.dim <= dataset.value.ndim - 1:
        if cur_size == ds_shape[cur_axis.dim]:
            cur_dim = cur_axis.dim
    else:
        if cur_size in ds_shape:
            matches = np.where(ds_shape == cur_size)[0]
            n = matches.size
            if n == 1:
                cur_dim = matches[0]

    if cur_dim is not None:
        valid_sizes.pop(cur_dim)
        valid_dims.remove(cur_dim)

    valid_axes = []
    for si in axes:
        if si.dim in valid_dims and si.value.size in valid_sizes:
            valid_axes.append(si)
    return valid_axes


# def format_coord(x, y):
#     xarr = X[0,:]
#     yarr = Y[:,0]
#     if ((x > xarr.min()) & (x <= xarr.max()) &
#         (y > yarr.min()) & (y <= yarr.max())):
#         col = np.searchsorted(xarr, x)-1
#         row = np.searchsorted(yarr, y)-1
#         z = Z[row, col]
#         return f'x={x:1.4f}, y={y:1.4f}, z={z:1.4f}   [{row},{col}]'
#     else:
#         return f'x={x:1.4f}, y={y:1.4f}'
#
# ax.format_coord = format_coord

def find_nearest_index(array, value):
    array = np.asarray(array)
    idx = (np.abs(array - value)).argmin()
    return idx


def find_nearest_value(array, value):
    idx = find_nearest_index(array, value)
    return array[idx]


def xyz_format_coord(x, y, xarr, yarr, zarr, prec=4, show_indexes=False):
    t = f'x={x:1.{prec}f}, y={y:1.{prec}f}, '
    if ((x > xarr.min()) & (x <= xarr.max()) &
            (y > yarr.min()) & (y <= yarr.max())):
        col = find_nearest_index(xarr, x)
        row = find_nearest_index(yarr, y)
        z = zarr[row, col]
        t += f'z={z:1.{prec}f}'
    if show_indexes:
        t += f'\t [{row},{col}]'
    return t
