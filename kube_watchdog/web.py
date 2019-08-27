
import asyncio
import json
import dataclasses
import logging
import click
from datetime import datetime, date
from pathlib import Path
from aiohttp import web
from .kube_listener import KubernetesPodListSupervisor
from .fairness import pods_calculate_order

log = logging.getLogger(__name__)

def json_serialize_unknown(obj):
	if isinstance(obj, (datetime, date)):
		return obj.isoformat()
	
	raise TypeError(f'Object not serializable class={type(obj)} obj={obj}')

def build_json_response(pod_list):
	state_obj = [dataclasses.asdict(p) for p in pod_list]
	state_json = json.dumps(state_obj, default=json_serialize_unknown)
	return state_json


class WatchdogWebServer:

	WEB_STATIC_DIR = Path(__file__).parent / 'web_static'
	WEB_STATIC_INDEX = WEB_STATIC_DIR / 'index.html'

	def __init__(self, port=8000):
		self.port = port
		self.pod_hierarchy_json = '[]'

	def on_kube_state_change(self, event):
		self.pod_hierarchy = pods_calculate_order(self.monitor.get_pods())
		self.pod_hierarchy_json = build_json_response(self.pod_hierarchy)
		log.info('New state: ' + self.pod_hierarchy_json)

	async def web_index(self, request):
		return web.FileResponse(self.WEB_STATIC_INDEX)

	async def web_state(self, request):
		return web.Response(text=self.pod_hierarchy_json)

	async def run(self):
		# setup kubernetes
		self.monitor = KubernetesPodListSupervisor()
		self.monitor.add_listener(self.on_kube_state_change)

		# setup webserver
		self.application = web.Application()

		# routes = web.RouteTableDef()

		self.application.add_routes([
			web.get('/', self.web_index),
			web.get('/api/state', self.web_state),
			web.static('/js', self.WEB_STATIC_DIR / 'js', follow_symlinks=True),
		])

		runner = web.AppRunner(self.application)
		await runner.setup()
		site = web.TCPSite(runner, '0.0.0.0', self.port)
		
		# wait for both
		await asyncio.gather(
			self.monitor.listen(),
			site.start(),
		)

@click.command('server')
@click.option('--port', type=int, default=8000)
def main(port):
	"""
	Host the web interface.
	"""
	server = WatchdogWebServer(port=port)
	asyncio.run(server.run())
