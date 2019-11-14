
import logging
import asyncio
import kubernetes_asyncio as kube
from typing import Callable

log = logging.getLogger(__name__)

class KubernetesPodListMonitor:

	POD_EVENTS = {'ADDED', 'MODIFIED', 'DELETED'}

	def __init__(self, namespace):
		self.namespace = namespace

	async def listen(self, callback : Callable[[str, str, kube.client.V1Pod], None]):
		"""
		callback(event_name, pod_name, pod_obj)
		"""
		self.callback = callback

		await kube.config.load_kube_config()
		api = kube.client.CoreV1Api()

		while True:
			try:
				log.info('Kubernetes stream listener starting')
				w = kube.watch.Watch()
				async for event in w.stream(api.list_namespaced_pod, namespace=self.namespace):
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

				self.callback(ev_type, pod_name, pod_obj)

			else:
				log.error(f'Unusual event type from kubectl: {event}')

		except Exception as e:
			log.exception(f'PodListSupervisor: error while processing event')
