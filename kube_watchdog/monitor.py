
import logging, operator
from dataclasses import dataclass
from datetime import date, datetime, timezone
import kubernetes_asyncio as kube
from typing import Mapping, List
from .kube_listener import KubernetesPodListMonitor
from .utilization_monitor import GpuUtilizationMonitor

log = logging.getLogger(__name__)

KUBERNETES_NAMESPACE = 'cvlab'

@dataclass
class PodInfoToPublish:
	""" Pod info to be exposed by the server """
	name: str
	user: str
	status: str
	date_created: datetime
	date_started: datetime
	num_gpu: int = 0 # number of GPUs used
		
	user_priority: int = 0 # priority specified by the user, the higher the more important, 0 is default
	user_ordinal: int = 0 # position in owner's queue: is it the 1st, 2nd ... most important job, expressed in number of GPUs
	global_ordinal: int = 0 # position in global queue expressed in number of GPUs

	utilization_mem: float = None # fraction of GPU memory allocated
	utilization_compute: float = None # fraction of GPU compute power used
	utilization_date: datetime = None

	def __init__(self, pod_obj, utilization_report={}):	
		labels = pod_obj.metadata.labels or {} # if null then use empty dict

		self.name = pod_obj.metadata.name
		self.user = labels.get('user', None)
		self.status = pod_obj.status.phase

		self.num_gpu = self.extract_num_gpu(pod_obj)
		
		self.user_priority = self.extract_priority(pod_obj)

		self.date_created = pod_obj.metadata.creation_timestamp
		self.date_started = self.extract_started_at(pod_obj) or self.date_created
		# log.debug(f'date started {self.date_started}')

		self.set_utilization_report(utilization_report)
	
	def set_utilization_report(self, utilization_report : dict):
		self.utilization_mem = utilization_report.get('memory', None)
		self.utilization_compute = utilization_report.get('compute', None)
		self.utilization_date = utilization_report.get('date', None)

	@staticmethod
	def extract_priority(pod_obj):
		labels = pod_obj.metadata.labels or {} # if null then use empty dict
		
		priority_label = labels.get('priority', 0)
		
		try:
			return int(priority_label)
		except ValueError:
			log.info(f'Non-numeric value for labels|priority: {priority_label} in pod {pod_obj.metadata.name}')
			return 0 # default
	
	@staticmethod
	def extract_num_gpu(pod_obj):
		num_gpu = 0
		for container in pod_obj.spec.containers:
			limits = container.resources.limits
			if limits is not None:
				num_gpu_in_container = limits.get('nvidia.com/gpu', 0)
				try:
					num_gpu += int(num_gpu_in_container)
				except ValueError:
					log.warning(f'Unexpected value for limits|nvidia.com/gpu: {num_gpu_in_container} in pod {pod_obj.metadata.name}')

		return num_gpu
					
	@staticmethod
	def extract_started_at(pod_obj):
		started_at = None
		for status in pod_obj.status.container_statuses or []:
			if status.state.running is not None:
				started_at = status.state.running.started_at # TODO get earlier date
		return started_at

	def __repr__(self):
		return f'pod({self.name}, user={self.user} with priority={self.user_priority}, {self.status}, {self.num_gpu} GPU)'


class PodStoredData:
	""" Pod info kept by the monitor """
	name: str
	parent: 'KubernetesPodListSupervisor'

	description_from_api: kube.client.V1Pod
	utilization_report: dict = {}
	data_pub: PodInfoToPublish
	# TODO note time of last change

	utilization_monitor: GpuUtilizationMonitor = None
	
	def __init__(self, parent : 'KubernetesPodListSupervisor', api_data : kube.client.V1Pod):
		self.parent = parent
		self.name = api_data.metadata.name
		self.update_description(api_data)
		

	def update_description(self, api_data : kube.client.V1Pod):
		self.description_from_api = api_data
		self.data_pub = PodInfoToPublish(api_data, self.utilization_report)

		is_running = self.data_pub.status == 'Running'
		is_measuring = self.utilization_monitor is not None

		# ensure we measure utilization
		if is_running and (not is_measuring):
			self.utilization_monitor = GpuUtilizationMonitor(
				pod_name = self.name,
				namespace = self.parent.namespace,
			)
			self.utilization_monitor.start(self.update_utilization)

		# stop utilization measurement if container stops
		if (not is_running) and is_measuring:
			self.utilization_monitor.stop()
			self.utilization_monitor = None

	def update_utilization(self, utilization_report : dict):
		new_info = utilization_report != self.utilization_report
		self.utilization_report = utilization_report
		self.data_pub.set_utilization_report(self.utilization_report)
		if new_info:
			self.parent.on_state_change()

	def on_remove(self):
		if self.utilization_monitor is not None:
			self.utilization_monitor.stop()


class KubernetesPodListSupervisor:
	pod_data_by_name : Mapping[str, PodStoredData]
	pod_info_list : List[PodInfoToPublish]

	def __init__(self, namespace=KUBERNETES_NAMESPACE):
		self.namespace = namespace

		self.pod_data_by_name = {}
		self.pod_info_list = []
	
		self.listeners = set()

	def get_pods(self) -> List[PodInfoToPublish]:
		return self.pod_info_list

	def add_listener(self, listener):
		self.listeners.add(listener)

	def remove_listener(self, listener):
		self.listeners.remove(listener)

	async def run(self):
		kube_listener = KubernetesPodListMonitor(namespace = self.namespace)
		await kube_listener.listen(callback=self.on_kubernetes_pod_event)

	def on_kubernetes_pod_event(self, ev_type, pod_name, pod_obj):
		if ev_type == 'MODIFIED' or ev_type == 'ADDED':
			self.on_pod_update(pod_name, pod_obj)

		elif ev_type == 'DELETED':
			self.on_pod_deleted(pod_name)

	def on_pod_deleted(self, pod_name):
		pod_data = self.pod_data_by_name.pop(pod_name, None)
		if pod_data is not None:
			pod_data.on_remove()

	def on_pod_update(self, pod_name, pod_obj):
		""" Pod is created or modified """

		try:
			# store the api data
			pod_data = self.pod_data_by_name.get(pod_name, None)
			if pod_data is None:
				self.pod_data_by_name[pod_name] = PodStoredData(self, pod_obj)
			else:
				pod_data.update_description(pod_obj)

			self.on_state_change()

		except Exception as e:
			log.exception(f'Error in pod info extraction, pod object:\n{pod_obj}')

	def on_state_change(self):
		self.pod_info_list = [pd.data_pub for pd in self.pod_data_by_name.values()]
		self.pod_info_list.sort(key=operator.attrgetter('name'))

		for listener in self.listeners:
			listener(self.pod_info_list)	

