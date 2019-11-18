
import asyncio
import json, yaml
import dataclasses
import logging
import click
from datetime import datetime, date
from pathlib import Path
from aiohttp import web
import jinja2
from .monitor import KubernetesPodListSupervisor
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

def expunge_nulls(d):
	if isinstance(d, dict):
		return {
			k: expunge_nulls(v)
			for (k, v) in d.items()
			if v is not None
		}
	elif isinstance(d, list):
		return [expunge_nulls(v) for v in d]
	else:
		return d


class WatchdogWebServer:

	WEB_STATIC_DIR = Path(__file__).parent / 'web_assets'
	WEB_STATIC_INDEX = WEB_STATIC_DIR / 'index.html'

	def __init__(self, port=8000):
		self.port = port
		self.pod_hierarchy_json = '[]'

		self.html_template_describe_pod = jinja2.Template(
			(self.WEB_STATIC_DIR / 'describe_pod.html').read_text()
		)

	def on_kube_state_change(self, event):
		self.pod_hierarchy = pods_calculate_order(self.monitor.get_pods())
		self.pod_hierarchy_json = build_json_response(self.pod_hierarchy)
		# log.info('New state: ' + self.pod_hierarchy_json)

	async def web_index(self, request):
		return web.FileResponse(self.WEB_STATIC_INDEX)

	async def web_state(self, request):
		return web.Response(
			text = self.pod_hierarchy_json,
			content_type = "application/json",
		)

	async def web_describe_pod(self, request):
		pod_name = request.match_info['pod_name']

		pod_data = self.monitor.pod_data_by_name.get(pod_name, None)

		if pod_data is None:
			raise web.HTTPNotFound(reason=f"No pod {pod_name}")

		pod_description = pod_data.description_from_api
		pod_utilization_report = pod_data.utilization_report

		html = self.html_template_describe_pod.render(
			pod_name = pod_name,
			nvidiasmi_date = pod_utilization_report.get('date', None),
			nvidiasmi_report = pod_utilization_report.get('report_txt', None) or pod_utilization_report.get('error', ''),
			pod_data_yaml = yaml.dump(expunge_nulls(pod_description.to_dict())),
			date_accessed = datetime.now(),
		)

		return web.Response(text=html, content_type="text/html")
	

	async def run(self):
		log.info('Server being constructed')

		# setup kubernetes
		self.monitor = KubernetesPodListSupervisor()
		self.monitor.add_listener(self.on_kube_state_change)

		# setup webserver
		self.application = web.Application()

		self.application.add_routes([
			web.get('/', self.web_index),
			web.get('/api/state', self.web_state),
			web.get('/describe/{pod_name}', self.web_describe_pod),
			web.static('/static', self.WEB_STATIC_DIR / 'static', follow_symlinks=True),
		])

		runner = web.AppRunner(self.application)
		await runner.setup()
		site = web.TCPSite(runner, '0.0.0.0', self.port)
		
		log.info('Server starting')

		# wait for both
		await asyncio.gather(
			self.monitor.run(),
			site.start(),
		)

@click.command('server')
@click.option('--port', type=int, default=8000)
def main(port):
	"""
	Host the web interface.
	"""
	server = WatchdogWebServer(port=port)
	asyncio.get_event_loop().run_until_complete(server.run())
