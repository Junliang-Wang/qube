import datetime
import time
from typing import List, Union, Callable, Dict, Any, Set, Iterable, Iterator

import numpy
import numpy as np
from qcodes import Parameter, DelegateParameter, Measurement
from qcodes import validators as vals

from qube.postprocess.dataset import Axis

QcParamType = Union[Parameter, DelegateParameter]


def split_sweep_shape(shape: Iterable[int], dims):
    """"
    Method to calculate the number of repeated and unique configurations for a given sweep shape and swept dimensions.
    Shape: list of points for each dimension
    dims: list of swept dimensions
    Returns:
        n_left: repetitions for a given unique configuration before the next one
        n_mid: number of unique configurations
        n_right: repetitions of the first two sequences

        For example, if the unique configurations are values [v1,v2,v3] and the function returns (2, 3, 4),
        it means that the values should be applied in the following order: [v1, v1, v2, v2, v3, v3] * 4

    Examples:
        shape = [2,3,4,5], dims = [] -> (2*3*4*5, 1, 1)
        shape = [2,3,4,5], dims = [1] -> (1, 2, 3*4*5)
        shape = [2,3,4,5], dims = [2] -> (2, 3, 4*5)
        shape = [2,3,4,5], dims = [3] -> (2*3, 4, 5)
        shape = [2,3,4,5], dims = [1, 2] -> (1, 2*3, 4*5)
        shape = [2,3,4,5], dims = [1, 3] -> (1, 2*3*4, 5)
        shape = [2,3,4,5], dims = [2, 4] -> (2, 3*4*5, 1)
    """
    shape = tuple(shape)
    dims = set(dims)
    dsize = np.array(shape, dtype=int)
    if len(dims) == 0:
        n_left = np.prod(shape)
        n_mid = 1
        n_right = 1
    else:
        min_idx = min(dims) - 1  # to index
        max_idx = max(dims) - 1  # to index
        n_left = np.prod(dsize[:min_idx])
        n_mid = np.prod(dsize[min_idx:max_idx + 1])
        n_right = np.prod(dsize[max_idx + 1:])
    return n_left, n_mid, n_right


def is_qc_param(param: Any) -> bool:
    """
    Verify if the input argument is a qcodes parameter.
    """
    return isinstance(param, (Parameter, DelegateParameter))


def validate_qc_param(param: Any, custom_message: str = None):
    msg = 'Parameter must be a qcodes parameter' if not custom_message else str(custom_message)
    if not is_qc_param(param):
        raise TypeError(msg)


def get_param_sources(param):
    l = []
    while hasattr(param, 'source'):
        param = param.source
        l.append(param)
    return l


def validate_qc_param_values(param, values):
    sources = get_param_sources(param)
    all_params = [param] + sources
    [pi.validate(vi) for vi in values for pi in all_params]


class SweepParameter(object):

    def __init__(self, source: QcParamType, value_generator: Callable[[int], np.typing.ArrayLike], dim: int,
                 apply: bool = True, refresh: bool = False):
        """
        Convenient class for storing sweep information for a given qcodes parameter.
        source: qcodes parameter. It will be saved in .parameter
        value_generator: function to generate sweep values. values = value_generator(pts)
        dim: dimension that it will be swept
        apply: if it is False, the "change" boolean will be always False in .get_ordered_instructions
        refresh: if it is False, the "change" boolean in the .get_ordered_instructions will be only True when the value
            is different from the previous step.
        """
        self.parameter = source
        self.value_generator = value_generator
        self._dim = 0
        self._sweep_shape = np.array([], dtype=int)
        self._values = []
        self._n_from_split = [1, 1, 1]
        self.set_dim(dim)
        self.apply = apply
        self.refresh = refresh

    @property
    def name(self):
        return self.parameter.name

    @property
    def unit(self):
        return self.parameter.unit

    @property
    def values(self):
        return self.get_values()

    @property
    def dim(self):
        return self._dim

    @dim.setter
    def dim(self, dim):
        self.set_dim(dim)

    @property
    def sweep_shape(self):
        return self._sweep_shape

    @sweep_shape.setter
    def sweep_shape(self, shape: Iterable[int]):
        self.set_sweep_shape(shape)

    def set_dim(self, dim):
        dim = int(dim)
        if dim < 0:
            raise ValueError('dim cannot be < 0')
        self._dim = dim

    def _update_values(self):
        sweep_shape = self._sweep_shape
        dim_pts = sweep_shape[self._dim - 1]
        self._values = self.value_generator(dim_pts)
        self._n_from_split = split_sweep_shape(sweep_shape, dims=[self._dim])

    def get_values(self):
        self._update_values()
        return self._values

    def set_sweep_shape(self, sweep_shape: Iterable[int]):
        """
        Set number of points for each sweep dimension.
        sweep_shape: list of integer.
        Example:
            sweep_shape = [10, 20, 30] means 10, 20, 30 pts for dim 1, 2 and 3, respectively.
        """
        sweep_shape = tuple(sweep_shape)
        self._validate_sweep_shape(sweep_shape)
        sweep_shape = np.array(sweep_shape, dtype=int)
        self._sweep_shape = sweep_shape
        self._update_values()

    def get_ordered_instructions(self) -> Iterator[List]:
        """
        Returns a generator which yields a list ([qcodes parameter, value, change bool flag]) for each step of the sweep.
        The order starts from lower swept dimension (min dim is 1).
        These instructions take into account the flags of "apply" and "refresh".
        """
        self._update_values()
        total_pts = np.prod(self.sweep_shape)
        for idx in range(total_pts):
            value = self._get_ordered_instruction_value(idx)
            change = self._get_ordered_instruction_change_bool(idx)
            yield [self.parameter, value, change]

    def get_axis(self) -> Axis:
        qc_param = self.parameter
        ax = Axis(
            name=qc_param.name,
            unit=qc_param.unit,
            dim=self.dim,
            value=self.values,
        )
        return ax

    def _get_ordered_instruction_value_index(self, idx):
        n_left, n_mid, n_right = self._n_from_split
        return (idx % (n_left * n_mid)) // n_left

    def _get_ordered_instruction_value(self, idx) -> Any:
        n_left, n_mid, n_right = self._n_from_split
        values = self._values
        _idx = (idx % (n_left * n_mid)) // n_left
        return values[_idx]

    def _get_ordered_instruction_change_bool(self, idx) -> bool:
        if self.apply is False:
            return False
        if self.refresh is True:
            return True
        else:
            n_left, n_mid, n_right = self._n_from_split
            return idx % (n_left) == 0

    def _validate_sweep_shape(self, sweep_shape: Iterable[int]):
        """
        sweep_shape: list of points to sweep for each dim.
        Example:
            sweep_shape = [20,30] --> 20 pts for dim 1 and 30 pts for dim 2
        """
        sweep_shape = tuple(sweep_shape)
        max_dim = len(sweep_shape)
        if max_dim < self.dim:
            raise ValueError(f'Swept dim ({self.dim}) has no points assigned')

    def validate_values(self, values):
        [self.parameter.validate(vi) for vi in values]


class SequentialCallable(object):
    def __init__(self):
        self.funcs = []

    def add_func(self, func: Callable, args=None, kwargs=None):
        args = [] if args is None or not isinstance(args, list) else args
        kwargs = {} if kwargs is None or not isinstance(kwargs, dict) else kwargs
        self.funcs.append([func, args, kwargs])

    @staticmethod
    def _build_call_function(processes: List = None):
        if isinstance(processes, (list, tuple)):
            def _func():
                for p in processes:
                    f, args, kwargs = p
                    f(*args, **kwargs)
        else:
            _func = lambda: 0
        return _func

    def __call__(self):
        func = self._build_call_function(self.funcs)
        func()

    def reset(self):
        self.funcs = []


class Timer(object):
    def __init__(self):
        self.t_start = 0
        self.t_elapsed = 0
        self._values = []

    @property
    def last_value(self):
        return self.values[-1]

    @property
    def values(self):
        return self._values

    @property
    def mean(self):
        return np.mean(self.values)

    @property
    def sum(self):
        return np.sum(self.values)

    def start(self):
        self.t_start = time.time()

    def elapse(self):
        self.t_elapsed = time.time()
        self._values.append(self.t_elapsed - self.t_start)

    def reset(self):
        self.t_start = 0
        self.t_elapsed = 0
        self._values = []

    # Few aliases
    stop = elapse
    lap = elapse
    clear = reset
    total = sum


class Sweeper(object):
    _timers = {key: Timer() for key in ['total', 'loop', 'apply', 'readout', 'save']}

    def __init__(self, name='Sweep'):
        """
        Class for performing multi-dimensional sweep measurements with qcodes parameters.

        The user can define:
            - any number of sweep instructions for each parameter.
                Ex: .sweep_linear(V1, 0, 1, dim=1)
            - sweep shape: points for each dimension.
                Ex: .set_sweep_shape([2,3,4])  # 2, 3 and 4 pts for dim 1, 2 and 3 (respectively)
            - custom method to apply a swept value (default: param(value).
                Ex: .set_apply_method(f) where f takes a dictionary as argument.
                See docstring of .set_apply_method
            - custom method to readout (default: param())
                Ex: .set_readout_method(f) where f takes a list of qcodes parameters.
                See docstring of .set_readout_method
            - pre-/post- processes which are executed before/after the sweep.
                Ex: .set_pre_process(*f) or .add_pre_process(f, args, kwargs)
            - pre-/post- readout which are executed before/after the readout at each sweep loop.
                Ex: .set_pre_readout(*f) or .add_pre_readout(f, args, kwargs)
            - pre-/post- process/readout waiting times (default is 0 for all cases)
                Ex: .pre_process_wait = 0
            - starting configuration: initial parameter values before executing the sweep
                Ex: .set_start_at({V1: v1, V2: v2, ...})
            - final configuration: parameter values after finishing the sweep
                Ex: .set_return_to({V1: v1, V2: v2, ...})
            - readouts: list of readout parameters for a given sweep.
                Ex: .set_readouts(ADC1, ADC2, ...)
            - record other parameter values: the class also saves "static" configurations at the beginning and the end
                of the sweeps, you can add other parameters that you want to be saved.
                By default, it will always save parameter that are swept and used in start_at and return_to.
                Ex: .set_tracked_parameters(*qcodes_param)
            - add a note that will be saved in the database
                Ex: .set_note('Loading map for 1e-')
            - custom callback function at each step (TODO)

        This class will handle:
            - generation of ordered instructions for each sweep loop
            - apply parameter values and measure the readouts at each step
            - save measured data and sweep information such as axes, dimensions, static configurations, etc

        Sweep execution order in .execute()
        1. Go to start_at
        2. Apply pre_process + wait
        3. Save initial static {param: value}
        4. Enter sweep loop
            4.1 Apply {param: value}
            4.2 Apply pre_readout + wait
            4.3 Readout + save
            4.4 Apply post_readout + wait
            4.5 Execute callback
            4.5 Go to next index and repeat from 4.1 until finish all steps
        5. Apply post_process + wait
        7. Go to return_to
        8. Save final static {param: value}

        Example 1:
            sw = Sweeper()
            sw.sweep_linear(V1, 0, 1, dim=1)
            sw.sweep_linear(V2, -1, -2, dim=1, refresh=True)  # parallel sweep with V1 and refresh at each step
            sw.sweep_log(V3, 0, 1e4, dim=2)  # log scale
            sw.sweep_step(V4, 0, 0.2, dim=3)  # start at 0 and step +0.2
            sw.sweep_values(V5, [0, 1, 3, -2], dim=4)  # custom sweep values
            sw.sweep_custom(V6, f, dim=5)  # custom value generator f(pts)
            sw.set_sweep_shape([10,20,30,40,50])  # first element corresponds to pts for dim=1
            run_id = sw.execute()

        Example 2:
            sw = Sweeper()
            sw.sweep_linear(V1, 0, 1, dim=1)
            sw.sweep_linear(V2, -1, -2, dim=1)
            run_id = sw.execute(
                sweep_shape=[10,20,30],
                pre_process = [lambda: print('start sweep', lambda: print('another message for pre process')],
                pre_process_wait = 1, # s
                post_process_wait = 1, # s
                readouts = [ADC1, ADC2],
                start_at = {V1: -0.5, V2: -1.0},
                return_to = {V1: 0, V2: 0},
                )

        Example 3:
            sw = Sweeper()
            sw.sweep_linear(V1, 0, 1, dim=1)
            sw.sweep_linear(V2, -1, -2, dim=1)
            # set configuration without execution
            sw.set_config(
                sweep_shape=[10,20,30],
                pre_process = [lambda: print('start sweep', lambda: print('another message for pre process')],
                pre_process_wait = 1, # s
                post_process_wait = 1, # s
                readouts = [ADC1, ADC2],
                start_at = {V1: -0.5, V2: -1.0},
                return_to = {V1: 0, V2: 0},
            )
            sw.get_instructions()  # list of [dim, qcodes parameter, values]
            sw.get_sweep_axes()   # list of Axis
            run_id = sw.execute()
        """
        self.name = name
        self.sweep_parameters = {}
        self.sweep_shape = []
        self.pre_process = SequentialCallable()
        self.post_process = SequentialCallable()
        self.pre_readout = SequentialCallable()
        self.post_readout = SequentialCallable()
        self._callback_methods = []
        self.pre_process_wait = 0  # s
        self.pre_readout_wait = 0  # s
        self.post_process_wait = 0  # s
        self.post_readout_wait = 0  # s
        self.apply_method = self.default_apply
        self.readout_method = self.default_readout
        self.readouts = []
        self.return_to = {}
        self.start_at = {}
        self.tracked_parameters = []
        self.statics = {}
        self.note = ''
        self.measurement = Measurement(name=self.name)
        self.last_sweep_info = {}
        self.show_progress_bar = True
        self.test_run = False

    """ Execution """

    def set_config(self,
                   instructions: List[List] = None,
                   sweep_shape: Iterable[int] = None,
                   readouts: List[QcParamType] = None,
                   measurement: Measurement = None,
                   start_at: Dict[QcParamType, Any] = None,
                   return_to: Dict[QcParamType, Any] = None,
                   apply_method: Callable[[Dict[QcParamType, Any]], None] = None,
                   readout_method: Callable[[List[QcParamType]], Dict[QcParamType, Any]] = None,
                   callback: List[Callable[[Dict], Any]] = None,
                   pre_process: List[Callable] = None,
                   post_process: List[Callable] = None,
                   pre_readout: List[Callable] = None,
                   post_readout: List[Callable] = None,
                   pre_process_wait: Union[int, float] = None,
                   post_process_wait: Union[int, float] = None,
                   pre_readout_wait: Union[int, float] = None,
                   post_readout_wait: Union[int, float] = None,
                   note: str = '',
                   show_progress_bar: bool = True,
                   ):
        """
        Save the configuration for .execute

        kwargs:
            instructions:
                List of sweep instructions as:
                - [dim, qcodes param, array of values] for sweeping a parameter
                - [dim, None, points] for repeating a given dimension
                If instructions are used, it will clear the previously set instructions.
                Note: it is recommended to use the generator methods such as .sweep_linear, .sweep_log, etc.
            sweep_shape:
                List of pts for each dim starting from 1.
                Ex: [10,2] which means 10 and 2 pts for dim1 and dim2.
                If it is None, it uses Sweeper.sweep_shape
                If instructions are used, this will be ignored.
            readouts:
                List of qcodes parameters for readout
                If it is None, it uses Sweeper.readouts
            measurement:
                Optional qcodes Measurement instance.
                If it is None, it creates a default Measurement instance.
            start_at:
                Dict for the initial configuration before entering the sweep loop. The keys are qcodes parameters.
                Ex: {v1: -0.2, v2: -0.1}
                If it is None, it won't move anything.
            return_to:
                Dict for the initial configuration after exiting the sweep loop. The keys are qcodes parameters.
                Ex: {v1: -0.2, v2: -0.1}
                If it is None, it won't move anything.
            apply_method:
                User-defined method to apply qcodes parameter's value. This method has only one argument for a
                dictionary where the keys are qcodes parameters.
                If it is None, it uses the method param(value) as in qcodes
            readout_method: Callable[[List[QcParamType]], Dict[QcParamType, Any]] = None
                User-defined method to get qcodes parameter's value. This method has only one argument for a
                list of qcodes parameters. It returns a dictionary of {param:value}.
                If it is None, it uses the method param() as in qcodes
            callback_method:
                Method that will be executed at the end of each sweep step.
                The only input argument is a dict as the template .get_callback_dict_template()
            pre_process:
                List of functions with no arguments.
                If you need to define custom arg and kwargs, use Sweeper.add_pre_process
            post_process:
                List of functions with no arguments.
                If you need to define custom arg and kwargs, use Sweeper.add_post_process
            pre_readout:
                List of functions with no arguments.
                If you need to define custom arg and kwargs, use Sweeper.add_pre_readout
            post_readout:
                List of functions with no arguments.
                If you need to define custom arg and kwargs, use Sweeper.add_post_readout
            pre_process_wait:
                Seconds to wait after execution of pre_process.
                It is None, wait=0
            post_process_wait:
                Seconds to wait after execution of post_process.
                It is None, wait=0
            pre_readout_wait:
                Seconds to wait after execution of pre_readout.
                It is None, wait=0
            post_readout_wait:
                Seconds to wait after execution of post_readout.
                It is None, wait=0
            note:
                Custom notes to add for the sweep.
            show_progress_bar:
                Show a simple jupyter notebook progress bar. Default is True.

        """
        if sweep_shape is not None: self.set_sweep_shape(sweep_shape)
        if instructions is not None: self.set_instructions(instructions)  # it overwrites sweep_shape
        if readouts is not None: self.set_readouts(*readouts)
        if measurement is not None: self.set_measurement(measurement)
        if return_to is not None: self.set_return_to(return_to)
        if start_at is not None: self.set_start_at(start_at)
        if apply_method is not None: self.set_apply_method(apply_method)
        if readout_method is not None: self.set_readout_method(readout_method)
        if callback is not None: self.set_callback(*callback)
        if pre_process is not None: self.set_pre_process(*pre_process)
        if post_process is not None: self.set_post_process(*post_process)
        if pre_readout is not None: self.set_pre_readout(*pre_readout)
        if pre_readout is not None: self.set_pre_readout(*pre_readout)
        if post_readout is not None: self.set_post_readout(*post_readout)
        if pre_process_wait is not None: self.pre_process_wait = pre_process_wait
        if post_process_wait is not None: self.post_process_wait = post_process_wait
        if pre_readout_wait is not None: self.pre_readout_wait = pre_readout_wait
        if post_readout_wait is not None: self.post_readout_wait = post_readout_wait
        if note is not None: self.set_note(note)
        self.show_progress_bar = show_progress_bar

    def execute(self, test_run=False, **kwargs) -> int:
        """
        Sweep execution with the following order:
        1. Go to start_at
        2. Apply pre_process + wait
        3. Save initial static {param: value}
        4. Enter sweep loop
            4.1 Apply {param: value}
            4.2 Apply pre_readout + wait
            4.3 Readout + save
            4.4 Apply post_readout + wait
            4.5 Execute callback
            4.5 Go to next index and repeat from 4.1 until finish all steps
        5. Apply post_process + wait
        7. Go to return_to
        8. Save final static {param: value}

        kwargs:
            test_run: if it is True, it will execute the sweep without changing any parameter nor readout.
            Rest of kwargs are the same as .set_config

        Returns:
            datasaver.run_id
        """
        self.set_config(**kwargs)
        self._validate_sweep_values()
        self._register_sweep_params_in_meas()
        self._register_readout_params_in_meas()
        self._register_sweep_info_params_in_meas()
        self._register_static_config_params('init')
        self._register_static_config_params('final')

        total_pts = self.get_total_sweep_points()
        if test_run:
            start_at, return_to, readouts = {}, {}, []
            ordered_instrs = [{}] * total_pts
        else:
            start_at, return_to, readouts = self.start_at, self.return_to, self.readouts
            ordered_instrs = self.get_ordered_instructions()

        # Reset timers
        timers = self._timers
        self._reset_timers()

        # Start timer for total execution time
        timers['total'].start()

        # Go to start_at config and apply pre_process
        self.apply_method(start_at)
        self.apply_pre_process()

        bar = ProgressBar(self.get_total_sweep_points())

        with self.measurement.run() as datasaver:
            # save sweep information
            self._save_sweep_info(datasaver)
            self._save_static_info(datasaver)

            # save static config before looping
            self._save_current_static_config(datasaver, label='init')

            for i, instr in enumerate(ordered_instrs):
                timers['loop'].start()

                # Apply parameter values in order
                timers['apply'].start()
                self.apply_method(instr)
                timers['apply'].elapse()

                # Perform readout
                self.apply_pre_readout()
                timers['readout'].start()
                results = self.readout_method(readouts)
                timers['readout'].elapse()

                # Save readout info (only for the first time)
                if i == 0:
                    [self._save_readout_info(datasaver, p, dim0_pts=np.array(v).size) for p, v in results.items()]
                data = [tuple([p, v]) for p, v in results.items()]

                # Save data to qcodes database
                timers['save'].start()
                datasaver.add_result(*data)
                timers['save'].elapse()

                self.apply_post_readout()
                timers['loop'].elapse()
                timers['total'].elapse()

                timings = {
                    'loop_mean': timers['loop'].mean,
                    'loop_i': timers['loop'].last_value,
                    'execution': timers['total'].last_value,
                    'expected_end': timers['loop'].mean * total_pts,
                }
                info = self._generate_callback_dict(i, results, timings)
                if self.show_progress_bar: bar(info)
                self.callback(info)

            # End of loop. Post process and go to return_to
            self.apply_post_process()
            self.apply_method(return_to)
            self._save_current_static_config(datasaver, label='final')
        timers['total'].elapse()

        return datasaver.run_id

    def reset(self):
        """
        Clear all the configuration for the sweep.
        """
        self.clear_instructions()
        self.clear_processes()
        self.clear_callbacks()
        self.apply_method = self.default_apply
        self.readout_method = self.default_readout
        self.readouts = []
        self.return_to = {}
        self.start_at = {}
        self.tracked_parameters = []
        self.statics = {}
        self.note = ''
        self.measurement = Measurement(name=self.name)
        self.last_sweep_info = {}
        self.show_progress_bar = True

    clear_all = reset  # alias for reset

    def clear_instructions(self):
        """
        Clear only sweep values and sweep shape.
        It keeps the config for pre/post process/readout, apply/readout method, start_at/return_to, etc.
        """
        self.sweep_parameters = {}
        self.sweep_shape = []

    def clear_processes(self):
        """
        Clear only configurations for processes.
        """
        self.pre_process = SequentialCallable()
        self.post_process = SequentialCallable()
        self.pre_readout = SequentialCallable()
        self.post_readout = SequentialCallable()
        self.pre_process_wait = 0  # s
        self.pre_readout_wait = 0  # s
        self.post_process_wait = 0  # s
        self.post_readout_wait = 0  # s

    def clear_callbacks(self):
        """
        Clear only callback methods
        """

    """ Config methods """

    def default_apply(self, instr: Dict[QcParamType, Any]):
        """
        instr is a dictionary {qc_param1: value1, qc_param2: value2, ...}
        This method will be executed at each sweep step before readout.
        """
        [param(value) for param, value in instr.items()]

    def default_readout(self, qc_params: List[QcParamType]) -> Dict[QcParamType, Any]:
        """
        qc_params: list of qcodes parameters
        This method will be executed at each sweep step for readout.

        :returns
        List of tuples of the form: [(instance_of_control1,value1), ...]
        This is compatible with datasaver
        """
        d = {param: param() for param in qc_params}
        return d

    def set_apply_method(self, f: Callable[[Dict[QcParamType, Any]], None]):
        """
        Custom apply method to set qcodes parameter values.
        f is a function which takes a dictionary ({qcodes_param: value}) as the only argument.
        """
        self.apply_method = f

    def set_readout_method(self, f: Callable[[List[QcParamType]], Dict[QcParamType, Any]]):
        """
        Custom readout method to get qcodes parameter values.
        f is a function which takes a list of qcodes parameters as the only argument.
        Returns:
            dictionary {qcodes_param: value}
        """
        self.readout_method = f

    def add_pre_process(self, f: Callable, args: List = None, kwargs: Dict = None):
        """
        Add method to be executed before starting the sweep.
        The execution will be: f(*args, **kwargs)
        """
        self.pre_process.add_func(f, args, kwargs)

    def add_post_process(self, f: Callable, args: List = None, kwargs: Dict = None):
        """
        Add method to be executed after finishing the sweep.
        The execution will be: f(*args, **kwargs)
        """
        self.post_process.add_func(f, args, kwargs)

    def add_pre_readout(self, f: Callable, args: List = None, kwargs: Dict = None):
        """
        Add method to be executed before each readout.
        The execution will be: f(*args, **kwargs)
        """
        self.pre_readout.add_func(f, args, kwargs)

    def add_post_readout(self, f: Callable, args: List = None, kwargs: Dict = None):
        """
        Add method to be executed after each readout.
        The execution will be: f(*args, **kwargs)
        """
        self.post_readout.add_func(f, args, kwargs)

    def add_callback(self, f: Callable[[Dict], Any]):
        """
        Add method to be executed at the end of each sweep step.
        The execution will be: f(callback_dict)
        """
        self._callback_methods.append(f)

    def set_pre_process(self, *f: Callable):
        """
        List of methods to be executed in order before starting the sweep.
        The execution will be: f1(), f2()...
        """
        for fi in f:
            self.add_pre_process(fi)

    def set_post_process(self, *f: Callable):
        """
        List of methods to be executed in order after finishing the sweep.
        The execution will be: f1(), f2()...
        """
        for fi in f:
            self.add_post_process(fi)

    def set_pre_readout(self, *f: Callable):
        """
        List of methods to be executed in order before each readout.
        The execution will be: f1(), f2()...
        """
        for fi in f:
            self.add_pre_readout(fi)

    def set_post_readout(self, *f: Callable):
        """
        List of methods to be executed in order after each readout.
        The execution will be: f1(), f2()...
        """
        for fi in f:
            self.add_post_readout(fi)

    def set_callback(self, *f: Callable[[Dict], Any]):
        """
        List of methods to be executed at the end of each sweep step.
        The execution will be: f1(), f2()...
        """
        for fi in f:
            self.add_callback(fi)

    def apply_pre_process(self):
        self.pre_process()
        self.wait(self.pre_process_wait)

    def apply_post_process(self):
        self.post_process()
        self.wait(self.post_process_wait)

    def apply_pre_readout(self):
        self.pre_readout()
        self.wait(self.pre_readout_wait)

    def apply_post_readout(self):
        self.post_readout()
        self.wait(self.post_readout_wait)

    def wait(self, s: Union[float, int]):
        if s < 0:
            raise ValueError('Waiting time should be >=0')
        time.sleep(s)

    def set_sweep_shape(self, sweep_shape: Iterable[int]):
        """
        Set number of points for each sweep dimension.
        sweep_shape: list of integer.
        Example:
            sweep_shape = [10, 20, 30] means 10, 20, 30 pts for dim 1, 2 and 3, respectively.
        """
        sweep_shape = tuple(sweep_shape)
        self._validate_sweep_shape(sweep_shape)
        self.sweep_shape = np.array(sweep_shape, dtype=int)
        self._update_sweep_params_shape()

    def set_instructions(self, instrs: List[List]):
        """
        Set sweep instructions with a list of:
        - [dim, qcodes parameter, values] for a swept parameter
        - [dim, None, points] for a repetition dim

        Example:
            [
            [1, V1, np.array([0, -0.2, -0.4, ..., -1.0])],
            [2, V2, np.array([-1, -0.5, 0])],
            [3, None, 30],
            ]
        """
        self.clear_instructions()
        max_dim = max([instr[0] for instr in instrs])
        sweep_shape = np.ones(max_dim, dtype=int)  # generate sweep_shape from instructions
        used_idxs = []
        for instr in instrs:
            dim, param, val = instr
            dim = int(dim)
            if param is None:
                pts = int(val)
            else:
                val = np.array(val)
                if val.ndim > 1:
                    raise ValueError('Sweep values must be an 1D array.')
                pts = int(val.size)
                self.sweep_values(param, val, dim=dim)
            idx = dim - 1
            if idx in used_idxs and sweep_shape[idx] != pts:
                raise ValueError('Inconsistency in sweep_shape. The number of points for each dim must be the same.')
            sweep_shape[idx] = pts
            used_idxs.append(idx)
            self.set_sweep_shape(tuple(sweep_shape))

    def add_readout(self, param: QcParamType):
        """
        Add a qcodes parameter to be readout at each sweep step.
        """
        validate_qc_param(param)
        self.readouts.append(param)

    def set_readouts(self, *params: QcParamType):
        """
        Set a list of qcodes parameters to be readout at each sweep step.
        """
        self.readouts = []
        for param in params:
            self.add_readout(param)

    def set_start_at(self, instr: Dict[QcParamType, Any]):
        """
        Set the parameter values at before starting the sweep.
        instr: dictionary {qcodes_param: value}
        """
        for param in instr.keys():
            validate_qc_param(param)
        self.start_at = instr

    def set_return_to(self, instr: Dict[QcParamType, Any]):
        """
        Set the parameter values at after finishing the sweep.
        instr: dictionary {qcodes_param: value}
        """
        for param in instr.keys():
            validate_qc_param(param)
        self.return_to = instr

    def set_tracked_parameters(self, *params: QcParamType):
        """
        Set extra qcodes parameters whose values will be saved at the start and the end of the sweep.
        """
        self.tracked_parameters = []
        for param in params:
            validate_qc_param(param)
            self.tracked_parameters.append(param)

    def get_tracked_parameters(self) -> Set[QcParamType]:
        """
        Get all qcodes parameters whose values will be saved at the start and the end of the sweep.
        It is composed by parameters that are tracked, swept, in start_at and in return_to.
        Returns:
            set of qcodes parameters
        """
        tparams = self.tracked_parameters
        iparams = list(self.start_at.keys())
        fparams = list(self.return_to.keys())
        sparams = list(self.sweep_parameters.keys())
        return set(tparams + iparams + fparams + sparams)

    def get_tracked_config(self) -> Dict[QcParamType, Any]:
        """
        Get all tracked parameters' value.
        Returns:
            dictionary {qcodes_param: value}
        """
        tparams = self.get_tracked_parameters()
        config = {}
        for param in tparams:
            config[param] = param()
        return config

    def set_note(self, s: str):
        """
        Set custom note that will be saved in the qcodes database.
        s: string
        """
        self.note = str(s)

    def set_measurement(self, measurement: Measurement):
        self.measurement = measurement

    def callback(self, d):
        [fi(d) for fi in self._callback_methods]

    """ Useful get methods """

    def get_instructions(self) -> List:
        """
        Return a list of sweep instructions as:
        - [dim, qcodes parameter, values] for a swept parameter
        - [dim, None, points] for a repetition dim

        Example:
            [
            [1, V1, np.array([0, -0.2, -0.4, ..., -1.0])],
            [2, V2, np.array([-1, -0.5, 0])],
            [3, None, 30],
            ]
        """
        d = self.get_sweep_params_by_dims()
        l = []
        for i, pts in enumerate(self.sweep_shape):
            dim = i + 1
            if dim not in d.keys():
                l.append([dim, None, pts])
            else:
                for p in d[dim]:
                    l.append([dim, p.parameter, p.values])
        return l

    def get_sweep_axes(self) -> List[Axis]:
        """
        Generate a list of Axis instances according to the sweep instructions.
        """
        self._update_sweep_params_shape()
        axes = [p.get_axis() for p in self.sweep_parameters.values()]
        return axes

    def get_ordered_instructions(self) -> Iterator[Dict[QcParamType, Any]]:
        """
        Returns a generator which yields a dictionary ({qcodes parameter: value}) for each step of the sweep.
        The order starts from lower swept dimension (min dim is 1).
        These instructions take into account the flags of "apply" and "refresh" for each swept parameter.
        Example 1: apply = True and refresh = False (default)
            .sweep_linear(V1, 0, 1, dim=1)
            .sweep_linear(V2, 1, 2, dim=2)
            .set_sweep_shape([3,3])
            Generated ordered instructions:
            {V1: 0, V2: 1}
            {V1: 0.5}  # do not need to refresh V2
            {V1: 1}
            {V1: 0, V2: 1.5}  # new V2 value
            {V1: 0.5}  # do not need to refresh V2
            {V1: 1}
            {V1: 0, V2: 2.0}  # new V2 value
            {V1: 0.5}  # do not need to refresh V2
            {V1: 1}
        Example 2: apply = True and refresh = True
            .sweep_linear(V1, 0, 1, dim=1, apply=True, refresh=True)
            .sweep_linear(V2, 1, 2, dim=2, apply=True, refresh=True)
            .set_sweep_shape([3,3])
            Generated ordered instructions:
            {V1: 0, V2: 1}
            {V1: 0.5, V2: 1}  # apply again V2 even though it is the same value as before
            {V1: 1, V2: 1}
            ...
            {V1: 1, V2: 2}
        Example 3: apply = False (refresh will be ignored)
            .sweep_linear(V1, 0, 1, dim=1, apply=False)
            .sweep_linear(V2, 1, 2, dim=2, apply=False)
            .set_sweep_shape([3,3])
            Generated ordered instructions:
            {}  # empty dictionary
            ...
            {}  # length of the generator is total number of points (3*3=9)
        """
        self._update_sweep_params_shape()
        only_reps = len(self.sweep_parameters) == 0
        if only_reps:
            for i in range(self.get_total_sweep_points()):
                yield {}
        else:
            instrs = []
            for sparam in self.sweep_parameters.values():
                instrs.append(sparam.get_ordered_instructions())
            for instr_i in zip(*instrs):
                d = {}
                for instr_i_pi in instr_i:
                    param, value, apply = instr_i_pi
                    if apply:
                        d[param] = value
                yield d

    def get_total_sweep_points(self):
        return np.prod(self.sweep_shape)

    def get_sweep_params_by_dims(self):
        d = {}
        for param in self.sweep_parameters.values():
            dim = param.dim
            if dim not in d.keys():
                d[dim] = []
            d[dim].append(param)
        return d

    def get_callback_dict_template(self):
        """
        Returns:
            Template dictionary for the user-defined callback_method, f(dict)
        """
        return {
            'total_pts': self.get_total_sweep_points(),
            'index': 0,
            'results': {rd: None for rd in self.readouts},
            'timings': {
                'loop_mean': 0,
                'loop_i': 0,
                'execution': 0,
                'expected_end': 0,
            },
            'sweeper': self,
        }

    def get_time_report(self):
        timers = self._timers
        timings = {}
        for key in ['loop', 'apply', 'readout', 'save']:
            timings[f'{key}_mean'] = timers[key].mean
            timings[f'{key}_laps'] = timers[key].values
        timings['execution'] = timers['total'].last_value
        return timings

    def show_time_report(self):
        timings = self.get_time_report()
        t = 'Last sweep timings:\n'
        seconds = timings[f'execution']
        t += f"Total time: {self._fmt_time(seconds)}\n"
        for key in ['loop', 'apply', 'readout', 'save']:
            mean = timings[f'{key}_mean']
            total = np.sum(timings[f'{key}_laps'])
            t += f"{key}: {self._fmt_time(mean)} (mean) | {self._fmt_time(total)} (total)\n"
        print(t)

    @staticmethod
    def _fmt_time(seconds):
        if seconds < 60:
            return f'{seconds:.2f}s'
        elif seconds < 60 * 60:
            return f'{seconds // 60}min {seconds % 60:.2f}s'
        else:
            hours = seconds // (60 * 60)
            rest = seconds % (60 * 60)
            mins = rest // 60
            s = rest % 60
            return f'{hours}h {mins}min {s:.2f}s'

    """ Sweep instruction methods """

    def sweep_custom(self, param: QcParamType, f: Callable[[int], np.typing.ArrayLike], dim: int, apply: bool = True,
                     refresh: bool = False) -> SweepParameter:
        """
        The most generic sweep method.
        param: qcodes parameter
        f: function to generate sweep values with a given number of pts. values = f(pts)
        dim: swept dimension
        apply: if it is False, it will be ignored in the sweep, but it will be saved in the database.
            Default is True.
        refresh: if it is False, it won't be applied again if the value is the same as in the previous sweep step.
            Default is False.
        """
        sparam = SweepParameter(param, value_generator=f, dim=dim, apply=apply, refresh=refresh)
        self.sweep_parameters[param] = sparam
        return sparam

    def sweep_values(self, param: QcParamType, values: Union[List, numpy.array], dim: int, apply: bool = True,
                     refresh: bool = False) -> SweepParameter:
        """
        Custom values to be swept
        param: qcodes parameter
        values: list or np.array of values
        dim: swept dimension
        apply: if it is False, it will be ignored in the sweep, but it will be saved in the database.
            Default is True.
        refresh: if it is False, it won't be applied again if the value is the same as in the previous sweep step.
            Default is False.
        """
        values = np.array(values)

        def f(pts):
            if values.size != pts:
                raise ValueError(
                    f'Sweep values of "{param}" has different size ({values.size}) than sweep points ({pts})')
            else:
                return values

        return self.sweep_custom(param=param, f=f, dim=dim, apply=apply, refresh=refresh)

    def sweep_linear(self, param: QcParamType, init: Any, final: Any, dim: int, apply: bool = True,
                     refresh: bool = False) -> SweepParameter:
        """
        Linearly spaced sweep values generated by numpy.linspace(init, final, pts)
        param: qcodes parameter
        init: initial value
        final: final value
        dim: swept dimension
        apply: if it is False, it will be ignored in the sweep, but it will be saved in the database.
            Default is True.
        refresh: if it is False, it won't be applied again if the value is the same as in the previous sweep step.
            Default is False.
        """

        def f(pts):
            values = np.linspace(init, final, pts)
            return values

        return self.sweep_custom(param=param, f=f, dim=dim, apply=apply, refresh=refresh)

    def sweep_log(self, param: QcParamType, init: Any, final: Any, dim: int, apply: bool = True,
                  refresh: bool = False) -> SweepParameter:
        """
        Log spaced sweep values generated by numpy.logspace(init, final, pts)
        param: qcodes parameter
        init: initial value
        final: final value
        dim: swept dimension
        apply: if it is False, it will be ignored in the sweep, but it will be saved in the database.
            Default is True.
        refresh: if it is False, it won't be applied again if the value is the same as in the previous sweep step.
            Default is False.
        """

        def f(pts):
            values = np.logspace(init, final, pts)
            return values

        return self.sweep_custom(param=param, f=f, dim=dim, apply=apply, refresh=refresh)

    def sweep_step(self, param: QcParamType, init: Any, step_size: Any, dim: int, apply: bool = True,
                   refresh: bool = False) -> SweepParameter:
        """
        Sweep values with a fixed step_size.
        param: qcodes parameter
        init: initial value
        step_size: value between each swept value
        dim: swept dimension
        apply: if it is False, it will be ignored in the sweep, but it will be saved in the database.
            Default is True.
        refresh: if it is False, it won't be applied again if the value is the same as in the previous sweep step.
            Default is False.
        """

        def f(pts):
            final = init + pts * step_size
            values = np.linspace(init, final, pts, endpoint=False)
            return values

        return self.sweep_custom(param=param, f=f, dim=dim, apply=apply, refresh=refresh)

    """ Private methods """

    def _reset_timers(self):
        for timers in self._timers.values():
            timers.reset()

    def _generate_callback_dict(self, index, results, timings):
        d = self.get_callback_dict_template()
        d.update({
            'index': index,
            'results': results,
            'timings': timings,
        })
        return d

    def _validate_sweep_shape(self, sweep_shape: Iterable[int]):
        for pts in sweep_shape:
            if not isinstance(pts, (int, np.integer)):
                raise TypeError(f'Points to sweep ({pts}) must be an integer')
            if pts <= 0:
                raise ValueError(f'Points to sweep ({pts}) must be > 0')

    def _update_sweep_params_shape(self):
        for param in self.sweep_parameters.values():
            param.set_sweep_shape(self.sweep_shape)

    def _validate_sweep_values(self):
        for qc_param, sw_param in self.sweep_parameters.items():
            values = sw_param.values
            validate_qc_param_values(qc_param, values)

    def _register_sweep_params_in_meas(self):
        meas = self.measurement
        for param in self.sweep_parameters.keys():
            meas.register_parameter(param, paramtype='array')

    def _register_readout_params_in_meas(self):
        meas = self.measurement
        for param in self.readouts:
            meas.register_parameter(param, setpoints=tuple())

    def _register_sweep_info_params_in_meas(self):
        meas = self.measurement
        val_pos_int = vals.Lists(vals.Ints(min_value=1))
        d = {  # name: [validator, paramtype]
            'sweep_shape': [val_pos_int, 'numeric'],
            'sweep_dims': [vals.Numbers(), 'numeric'],
            'sweep_axes_names': [vals.Strings(), 'text'],
            'sweep_axes_full_names': [vals.Strings(), 'text'],
            'sweep_axes_isbools': [vals.Strings(), 'numeric'],
            'sweep_readouts_names': [vals.Strings(), 'text'],
            'sweep_readouts_full_names': [vals.Strings(), 'text'],
            'sweep_readouts_dim0s': [vals.Numbers(), 'numeric'],
            'sweep_note': [vals.Strings(), 'text'],
            'static_labels': [vals.Strings(), 'text'],
            'static_names': [vals.Strings(), 'text'],
            'static_units': [vals.Strings(), 'text'],
            'static_isbools': [vals.Strings(), 'numeric'],
        }
        for key, (val, typ) in d.items():
            meas.register_parameter(
                Parameter(name=key, set_cmd=None, get_cmd=None, vals=val),
                paramtype=typ
            )

    def _register_static_config_params(self, label):
        d = {
            f'static_values_{label}': [vals.Numbers(), 'numeric'],
        }
        for key, (val, typ) in d.items():
            self.measurement.register_parameter(
                Parameter(name=key, set_cmd=None, get_cmd=None, vals=val), paramtype=typ)

    def _save_sweep_info(self, datasaver):
        self._save_axes_info(datasaver)
        self._save_axes_values(datasaver)
        for pts in self.sweep_shape:
            datasaver.add_result(('sweep_shape', pts))
        datasaver.add_result(('sweep_note', str(self.note)))

    def _save_static_info(self, datasaver):
        tparams = self.get_tracked_parameters()
        for param in tparams:
            isbool = int(isinstance(param(), bool))
            datasaver.add_result(
                ('static_names', param.name),
                ('static_units', param.unit),
                ('static_isbools', isbool),
            )

    def _save_axes_info(self, datasaver):
        for qc_param, sw_param in self.sweep_parameters.items():
            isbool = int(isinstance(sw_param.values[0], bool))
            datasaver.add_result(
                ('sweep_axes_names', qc_param.name),
                ('sweep_axes_full_names', qc_param.full_name),
                ('sweep_axes_isbools', isbool),
                ('sweep_dims', sw_param.dim),
            )

    def _save_axes_values(self, datasaver):
        for dim, param_list in self.get_sweep_params_by_dims().items():
            values = []
            qc_params = []
            for p in param_list:
                v = p.values
                if isinstance(v[0], bool):
                    v = np.array(v, dtype=int)
                values.append(v)
                qc_params.append(p.parameter)
            for val in zip(*values):
                param_values = [tuple([p, val[i]]) for i, p in enumerate(qc_params)]
                datasaver.add_result(*param_values)

    def _save_readout_info(self, datasaver, param, dim0_pts):
        datasaver.add_result(
            ('sweep_readouts_names', param.name),
            ('sweep_readouts_full_names', param.full_name),
            ('sweep_readouts_dim0s', dim0_pts),
        )

    def _save_current_static_config(self, datasaver, label):
        config = self.get_tracked_config()
        self._save_static_config(datasaver, config, label)

    def _save_static_config(self, datasaver, config, label):
        self.statics[label] = config
        datasaver.add_result(('static_labels', label))
        for param, value in config.items():
            isbool = int(isinstance(value, bool))
            if isbool == 1:
                value = int(value)
            datasaver.add_result(
                (f'static_values_{label}', value),
            )


class ProgressBar(object):
    def __init__(self, total_pts):
        self.total_pts = int(total_pts)

    def update(self, callback_dict: dict):
        timings = callback_dict['timings']
        meas_time = datetime.timedelta(seconds=timings['expected_end'])
        i = callback_dict['index']
        start_idx = 3
        if i == start_idx:
            from tqdm.notebook import tqdm as progress_bar
            print(f'The measurement will take {meas_time}')
            self.bar = progress_bar(total=self.total_pts)
            self.bar.update(start_idx + 1)
        elif i > start_idx:
            self.bar.update(1)

    def __call__(self, callback_dict: dict):
        self.update(callback_dict)

# def sweep_progress_bar(sweep_callback, progress_bar):
#     timings = sweep_callback['timings']
#     meas_time = datetime.timedelta(seconds=timings['expected_end'])
#
#     # Estimation of measurement duration
#     print(f'The measurement will take {meas_time}')
#
#     # Display progress bar
#     bar = progress_bar(total=sweep_callback['total_pts'])
#     bar.update(1)
