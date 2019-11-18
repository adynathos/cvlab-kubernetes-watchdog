import logging
import asyncio, functools
import kubernetes_asyncio as kube
import numpy as np
from datetime import datetime
from io import StringIO

log = logging.getLogger(__name__)

GPU_QUERY_MEASUREMENT_DURATION = 21
GPU_QUERY_MEASUREMENT_COOLDOWN = 90
GPU_QUERY_LOOP_INTERVAL = 3
GPU_QUERY_MEASUREMENT_TIMEOUT = 5 + 2*GPU_QUERY_MEASUREMENT_DURATION

GPU_QUERY_FIELDS = [
	'index',
	'utilization.gpu',
	# 'utilization.memory',
	'memory.used',
	'memory.total',
]

GPU_QUERY_CMD = [
	'/usr/bin/timeout', str(GPU_QUERY_MEASUREMENT_DURATION),
	'/usr/bin/nvidia-smi',
	'--format=csv',
  	f'--loop={GPU_QUERY_LOOP_INTERVAL}',
	f'--query-gpu={",".join(GPU_QUERY_FIELDS)}',
]

def process_row_percent(val):
	return float(val.split(maxsplit=1)[0]) * 0.01

def process_row_mem(val):
	return float(val.split(maxsplit=1)[0])


#
# There is a bizarre error when np.genfromtxt writes into the dict passed as the `covnerters` argument.
# Every time the function is called, it writes again, and wraps our functions in functools.partial.
# After enough iterations, the recursion depth is too big and causes an exception.
# Our defense is twofold:
# * pass encoding = 'utf8', the wrapper is made to pass `bytes` as argument to our converter
#	we don't want bytes, why would we want them
# * use a frozen dict to enforce np.genfromtxt can't write to it

class FrozenDict(dict):
	def __setitem__(self, key, value):
		raise RuntimeError(f'FrozenDict: Trying to set key {key} to {value}')

GPU_QUERY_PROCESSORS = FrozenDict(**{
	'index': int,
	'utilization.gpu': process_row_percent,
	'utilization.memory': process_row_percent,
	'memory.used': process_row_mem,
	'memory.total': process_row_mem,
})

@functools.lru_cache(1)
def get_api_ws():
	return kube.client.CoreV1Api(api_client=kube.stream.WsApiClient())


async def run_nvidiasmi_on_container(pod_name, namespace, api=None):
	# await kube.config.load_kube_config()
	api_ws = api or get_api_ws()

	cmd = GPU_QUERY_CMD
	
	response_future = api_ws.connect_get_namespaced_pod_exec(
		name = pod_name, 
		namespace = namespace,
		command = cmd,
		stderr = True,
		stdin = False,
		stdout = True,
		tty = False,
	)

	response = await asyncio.wait_for(response_future, timeout=GPU_QUERY_MEASUREMENT_TIMEOUT)

	return response


def process_nvidiasmi_report(report_txt):
	report_table = np.genfromtxt(
		StringIO(report_txt), 
		names = GPU_QUERY_FIELDS,
		converters = GPU_QUERY_PROCESSORS,
		deletechars = '', # prevent mangling of names
		delimiter = ',', 
		skip_header = 1, 
		autostrip = True,
		dtype = None, # prevent casting to float
		encoding = 'utf8', # prevent adding tobytes wrappers
	)
	
	mem_relative = report_table['memory.used'] / report_table['memory.total']
	gpu_util = report_table['utilization.gpu']
	
	mem_relative_avg = np.mean(mem_relative).round(2)
	gpu_util_avg = np.mean(gpu_util).round(2)
	
	return dict(
		report_table = report_table,
		memory = mem_relative_avg,
		compute = gpu_util_avg,
	)

async def measure_gpu_utilization(pod_name, namespace, api=None):
	result = dict(pod_name=pod_name)
	
	try:
		result['report_txt'] = await run_nvidiasmi_on_container(
			pod_name = pod_name,
			namespace = namespace,
			api = api,
		)
		report_parsed = process_nvidiasmi_report(result['report_txt'])
		result.update(report_parsed)
		log.info(f'nvidia-smi result success, pod {pod_name}')

	except asyncio.TimeoutError:
		result['error'] = f'timeout at {datetime.now().isoformat()}'
		log.warning(f'nvidia-smi timeout, pod {pod_name}')

	except Exception as e:
		result['error'] = str(e)
		log.exception(f'nvidia-smi monitor error, pod {pod_name}: {e}')	

	result['date'] = datetime.now()

	return result


class GpuUtilizationMonitor:
	"""
	Measures the GPU utilization of a container in a loop untill stopped.
	"""

	callback = None
	loop_task = None

	def __init__(self, pod_name, namespace):
		self.pod_name = pod_name
		self.namespace = namespace

	async def measurement_loop(self):
		log.info(f'GPU utilization monitor starting for {self.pod_name}')
		while True:
			report = await measure_gpu_utilization(pod_name = self.pod_name, namespace = self.namespace)
			try:
				if self.callback:
					self.callback(report)
			except Exception as e:
				log.exception(f'gpu utilization exception in callback, pod {self.pod_name}')
			log.info(f'nvidia-smi waiting, pod {self.pod_name}')
			await asyncio.sleep(GPU_QUERY_MEASUREMENT_COOLDOWN)

	def start(self, callback):
		self.stop()
		self.callback = callback
		self.loop_task = asyncio.get_event_loop().create_task(self.measurement_loop())

	def stop(self):
		if self.loop_task is not None:
			self.loop_task.cancel()
			self.loop_task = None
			log.info(f'utilization monitor stopped, pod {self.pod_name}')
		self.callback = None
		