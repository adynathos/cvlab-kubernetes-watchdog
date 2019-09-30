from dataclasses import dataclass
from datetime import date, datetime, timezone
import logging
import kubernetes_asyncio as kube
from typing import List
from ssl import SSLError

log = logging.getLogger(__name__)

@dataclass
class PodInfo:
	name: str
	user: str
	status: str
	date_created: datetime
	date_started: datetime
	num_gpu: int # number of GPUs used
		
	user_priority: int # priority specified by the user, the higher the more important, 0 is default
	user_ordinal: int # position in owner's queue: is it the 1st, 2nd ... most important job, expressed in number of GPUs
	global_ordinal: int # position in global queue expressed in number of GPUs

	def __init__(self, pod_obj):	
		labels = pod_obj.metadata.labels or {} # if null then use empty dict

		self.name = pod_obj.metadata.name
		self.user = labels.get('user', None)
		self.status = pod_obj.status.phase

		self.num_gpu = self.extract_num_gpu(pod_obj)
		
		self.user_priority = self.extract_priority(pod_obj)
		self.user_ordinal = 0
		self.global_ordinal = 0
		
		self.date_created = pod_obj.metadata.creation_timestamp
		self.date_started = self.extract_started_at(pod_obj) or self.date_created
		# log.debug(f'date started {self.date_started}')
		
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


class KubernetesPodListSupervisor:

	POD_EVENTS = {'ADDED', 'MODIFIED', 'DELETED'}

	def __init__(self):
		self.pod_data_from_api = {}
		self.pod_info_processed = {}
		
		self.pod_info_list = []
	
		self.listeners = set()

	def get_pods(self) -> List[PodInfo]:
		return self.pod_info_list

	def add_listener(self, listener):
		self.listeners.add(listener)

	def remove_listener(self, listener):
		self.listeners.remove(listener)

	async def listen(self):
		
		await kube.config.load_kube_config()
		
		api = kube.client.CoreV1Api()

		while True:
			try:
				log.info('Kubernetes stream listener starting')
				w = kube.watch.Watch()
				async for event in w.stream(api.list_namespaced_pod, namespace='cvlab'):
					self.process_event(event)

				log.warning('Kubernetes watch has run out of events, restarting in 5s ...')
			except Exception as e:
				log.exception('Exception in Kubernetes stream listener, restarting in 5s ...')
			
			await asyncio.sleep(5)


	def process_event(self, event):
		try:
			ev_type = event.get('type', None) 
			pod_obj = event.get('object', None)

			if ev_type in self.POD_EVENTS:
				pod_name = pod_obj.metadata.name

				log.debug(f"Event: {ev_type} {pod_name}")

				if ev_type == 'MODIFIED' or ev_type == 'ADDED':
					self.pod_data_from_api[pod_name] = pod_obj

					try:
						self.pod_info_processed[pod_name] = PodInfo(pod_obj)
					except Exception as e:
						log.exception(f'Error in pod info extraction, pod object:\n{pod_obj}')
						return

				elif ev_type == 'DELETED':
					del self.pod_data_from_api[pod_name]
					del self.pod_info_processed[pod_name]

				self.pod_info_list = list(self.pod_info_processed.values())
		
				for listener in self.listeners:
					listener(event)

			else:
				log.error(f'Unusual event type from kubectl: {event}')

		except Exception as e:
			log.exception(f'PodListSupervisor: error while processing event')
	