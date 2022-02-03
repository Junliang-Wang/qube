import ipywidgets as widgets
from ipywidgets import HBox, VBox, Layout
from IPython.display import display


class BaseAxis(object):
    layout_ds = Layout(width='200px')
    layout_label = Layout(width='200px')

    def __init__(self, datasets, name='axis', parent=None, *args, **kwargs):
        self.widgets = {}
        self._disabled = False
        self.datasets = {}
        self.name = name
        self.parent = parent
        self.clear_datasets()
        self.set_datasets(datasets)
        self.init_widgets()
        self.callback_dataset_changed = lambda: 0

    @property
    def disabled(self):
        return self._disabled

    @disabled.setter
    def disabled(self, b):
        self._disabled = b
        for wi in self.widgets.values():
            wi.disabled = b

    @property
    def dataset(self):
        key = self.widgets['dataset'].value
        return self.datasets[key]

    def init_widgets(self):
        self._create_dataset_widget()
        self._create_label_widget()

    def _create_dataset_widget(self):
        widget = widgets.Dropdown(
            options=self.datasets.keys(),
            description=self.name,
            disabled=False,
            layout=self.layout_ds, )
        widget.observe(lambda b: self.dataset_changed(), names='value')
        self.widgets['dataset'] = widget

    def _create_label_widget(self):
        widget = widgets.Text(value='', description='label', layout=self.layout_label)
        self.widgets['label'] = widget
        self.reset_label()

    def update_dataset_options(self):
        if 'dataset' in self.widgets.keys():
            cur_key = self.widgets['dataset'].value
            keys = list(self.datasets.keys())
            self.widgets['dataset'].options = keys
            if cur_key not in keys:
                self.set_dataset(keys[0])

    def clear_datasets(self):
        self.datasets = {}

    def get_datasets(self):
        return self.datasets

    def set_datasets(self, datasets):
        empty = len(datasets) == 0
        if empty:
            raise ValueError('Empty datasets')

        self.clear_datasets()
        if hasattr(datasets, 'keys'):
            for key, ds in datasets.items():
                self.add_dataset(ds, key=key)
        else:
            for ds in datasets:
                self.add_dataset(ds)
        self.update_dataset_options()

    def add_dataset(self, dataset, key=None):
        if key is None:
            key = dataset.name
        self.datasets[key] = dataset

    def get_dataset(self):
        return self.dataset

    def set_dataset(self, key):
        if key in self.datasets.keys():
            self.widgets['dataset'].value = key

    def set_nearest_dataset(self, key):
        key = self.search_nearest_key(key)
        self.set_dataset(key)

    def get_label(self):
        return self.widgets['label'].value

    def set_label(self, value):
        self.widgets['label'].value = value

    def reset_label(self):
        self.widgets['label'].value = self.get_dataset().label

    def delete_widgets(self):
        for wi in self.widgets.values():
            try:
                wi.close()
            except:
                pass

    def dataset_changed(self):
        self.reset_label()
        self.callback_dataset_changed()

    # def callback_dataset_changed(self):
    #     """
    #     User-defined method when dataset is changed
    #     """
    #     pass

    def search_nearest_key(self, key):
        opts = list(self.datasets.keys())
        ls = None
        if isinstance(key, str):
            for opt in opts:
                if key in opt:
                    ls = opt
                    break
        if ls is None:
            return opts[0]
        return ls


class FigAxis(BaseAxis):
    layout_ds = Layout(width='200px')
    layout_label = Layout(width='200px')
    layout_lim = Layout(width='200px')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def init_widgets(self):
        super().init_widgets()
        self._create_lim_widgets()
        self._arrange_widgets()

    def _create_lim_widgets(self):
        self.widgets['min'] = widgets.Text(value='', description='min', layout=self.layout_lim)
        self.widgets['max'] = widgets.Text(value='', description='max', layout=self.layout_lim)
        self.reset_lim()

    def _arrange_widgets(self):
        box = HBox([
            self.widgets['dataset'],
            self.widgets['label'],
            self.widgets['min'],
            self.widgets['max'],
        ])
        self.widgets['box'] = box

    def display(self):
        display(self.widgets['box'])

    def get_lim(self):
        limits = [None, None]
        vmin = self.widgets['min'].value
        vmax = self.widgets['max'].value
        try:
            limits[0] = float(vmin)
        except:
            pass
        try:
            limits[1] = float(vmax)
        except:
            pass
        return limits

    def set_lim(self, lim):
        vmin, vmax = lim
        self.widgets['min'].value = str(vmin)
        self.widgets['max'].value = str(vmax)

    def reset_lim(self):
        self.set_lim(('', ''))


class SliderAxis(BaseAxis):
    layout_ds = Layout(width='200px')
    layout_label = Layout(width='200px')
    layout_button = Layout(width='50px')
    layout_idx = Layout(width='60px')
    layout_slider = Layout(width='200px')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def last_idx(self):
        return int(self.dataset.value.size) - 1

    @property
    def cur_idx(self):
        if self.widgets['all'].value is True:
            idx = slice(None)
        else:
            idx = self.widgets['idx'].value
        return idx

    @cur_idx.setter
    def cur_idx(self, value):
        if value < 0:
            value = 0
        if value > self.last_idx:
            value = self.last_idx
        self.widgets['idx'].value = value

    @property
    def cur_value(self):
        return self.get_dataset().value[self.cur_idx]

    @property
    def dim(self):
        return self.dataset.dim

    def init_widgets(self):
        super().init_widgets()
        self._create_slider_widgets()
        self._arrange_widgets()

    def _create_slider_widgets(self):
        self.widgets['left'] = widgets.Button(icon='arrow-left', layout=self.layout_button, )
        self.widgets['left'].on_click(lambda b: self.set_cur_idx(self.cur_idx - 1))
        self.widgets['right'] = widgets.Button(icon='arrow-right', layout=self.layout_button, )
        self.widgets['right'].on_click(lambda b: self.set_cur_idx(self.cur_idx + 1))

        self.widgets['idx'] = widgets.BoundedIntText(
            value=0,
            min=0,
            max=self.last_idx,
            step=1,
            description='',
            layout=self.layout_idx, )
        self.widgets['idx'].observe(lambda b: self.callback_idx_changed(), names='value')

        self.widgets['slider'] = widgets.IntSlider(
            value=0,
            min=0,
            max=self.last_idx,
            step=1,
            description='',
            layout=self.layout_slider,
        )

        self.widgets['link'] = widgets.link((self.widgets['idx'], 'value'), (self.widgets['slider'], 'value'))
        self.widgets['all'] = widgets.Checkbox(
            value=False,
            description='all?',
            # layout=self.layout_button,
        )

    def _arrange_widgets(self):
        box = HBox([
            self.widgets['dataset'],
            self.widgets['label'],
            self.widgets['left'],
            self.widgets['right'],
            self.widgets['idx'],
            self.widgets['slider'],
            self.widgets['all'],
        ])
        self.widgets['box'] = box

    def display_widgets(self):
        display(self.widgets['box'])

    def dataset_changed(self):
        super().dataset_changed()
        self.widgets['idx'].max = self.last_idx
        self.widgets['slider'].max = self.last_idx
        self.callback_dataset_changed()

    def set_cur_idx(self, value):
        self.cur_idx = value

    def callback_idx_changed(self):
        """
        User-defined method when current index is changed
        """
        pass


class SliderStackAxis(BaseAxis):
    layout_ds = Layout(width='200px')
    layout_label = Layout(width='200px')
    layout_button = Layout(width='50px')
    layout_idx = Layout(width='100px')
    layout_slider = Layout(width='200px')
    layout_play = Layout(width='200px')
    play_speed = 500

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def last_idx(self):
        return int(self.dataset.value.size) - 1

    @property
    def cur_idx(self):
        idx = self.widgets['idx'].value
        return idx

    @cur_idx.setter
    def cur_idx(self, value):
        if value < 0:
            value = 0
        if value > self.last_idx:
            value = self.last_idx
        self.widgets['idx'].value = value

    @property
    def cur_value(self):
        return self.get_dataset().value[self.cur_idx]

    @property
    def dim(self):
        if hasattr(self.dataset, 'dim'):
            d = self.dataset.dim
        else:
            d = None
        return d

    def init_widgets(self):
        super().init_widgets()
        self._create_slider_widgets()
        self._arrange_widgets()

    def _create_slider_widgets(self):
        self.widgets['left'] = widgets.Button(icon='arrow-left', layout=self.layout_button, )
        self.widgets['left'].on_click(lambda b: self.set_cur_idx(self.cur_idx - 1))
        self.widgets['right'] = widgets.Button(icon='arrow-right', layout=self.layout_button, )
        self.widgets['right'].on_click(lambda b: self.set_cur_idx(self.cur_idx + 1))

        self.widgets['idx'] = widgets.Dropdown(
            options=self._idx_options(),
            value=0,
            min=0,
            max=self.last_idx,
            description='',
            disabled=False,
            layout=self.layout_idx,
        )
        self.widgets['idx'].observe(lambda b: self.callback_idx_changed(), names='value')

        self.widgets['slider'] = widgets.IntSlider(
            value=0,
            min=0,
            max=self.last_idx,
            step=1,
            description='',
            layout=self.layout_slider,
        )

        self.widgets['play'] = widgets.Play(
            value=0,
            min=0,
            max=self.last_idx,
            step=1,
            interval=self.play_speed,
            description="Press play",
            disabled=False,
            layout=self.layout_play,
        )
        # self.widgets['link'] = widgets.link((self.widgets['idx'], 'value'), (self.widgets['slider'], 'value'))
        self.widgets['link'] = widgets.link(
            (self.widgets['idx'], 'value'),
            (self.widgets['slider'], 'value'),
            # (self.widgets['play'], 'value'),
        )
        widgets.link(
            # (self.widgets['idx'], 'value'),
            (self.widgets['slider'], 'value'),
            (self.widgets['play'], 'value'),
        )

        # self.widgets['type_single'] = HBox([
        #     self.widgets['idx'],
        #     self.widgets['left'],
        #     self.widgets['right'],
        #     self.widgets['play'],
        #     self.widgets['slider'],
        # ])

        # stack_movie = HBox([
        #     self.widgets['play'],
        # # ])
        #
        # self.widgets['stacked'] = widgets.Stacked([stack_single, stack_movie])
        # self.widgets['type'] = widgets.Dropdown(
        #     options=['single', 'movie'],
        # )
        # widgets.link((self.widgets['type'], 'index'), (self.widgets['stacked'], 'selected_index'))

        # widgets.jslink((play, 'value'), (slider, 'value'))
        # widgets.HBox([play, slider])

        # self.widgets['all'] = widgets.Checkbox(
        #     value=False,
        #     description='all?',
        #     # layout=self.layout_button,
        # )

    def _arrange_widgets(self):
        box = HBox([
            self.widgets['dataset'],
            self.widgets['label'],
            # self.widgets['type_single']
            # self.widgets['type'],
            self.widgets['idx'],
            self.widgets['left'],
            self.widgets['right'],
            self.widgets['play'],
            self.widgets['slider'],
            # self.widgets['all'],
        ])
        self.widgets['box'] = box

    def display_widgets(self):
        display(self.widgets['box'])

    def dataset_changed(self):
        super().dataset_changed()
        self.widgets['idx'].max = self.last_idx
        self.widgets['idx'].options = self._idx_options()
        self.widgets['slider'].max = self.last_idx
        self.callback_dataset_changed()

    def set_cur_idx(self, value):
        self.cur_idx = value

    def callback_idx_changed(self):
        """
        User-defined method when current index is changed
        """
        pass

    def _idx_options(self):
        opts = [(f'{idx}: {value}', idx) for idx, value in enumerate(self.dataset.value)]
        return opts
