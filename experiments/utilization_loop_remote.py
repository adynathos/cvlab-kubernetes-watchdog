
import asyncio
import logging
import click
from datetime import datetime, date
from pathlib import Path
from aiohttp import web

logging.basicConfig(level=logging.DEBUG, format='{asctime} | {name} {levelname} | {message}', style='{')
log = logging.getLogger('root.testsrv')

class WatchdogWebServer:

	def __init__(self, port=8000):
		self.port = port

	async def web_index(self, request):
		return web.Response(body="[utilization report submission test server]")

	async def web_submit_report(self, request):

		body = await request.text()

		data = dict(
			method = request.method,
			query_string = request.query_string,
			body = body,
		)

		log.debug(data)

		return web.json_response(data)

	async def run(self):
		log.info('Server being constructed')

		# setup webserver
		self.application = web.Application()

		self.application.add_routes([
			web.get('/', self.web_index),
			web.post('/report', self.web_submit_report),
		])

		runner = web.AppRunner(self.application)
		await runner.setup()
		site = web.TCPSite(runner, '0.0.0.0', self.port)
		
		log.info('Server starting')

		# wait for both
		await asyncio.gather(
			site.start(), # this is non-blocking
			asyncio.sleep(300), 
		)

@click.command('server')
@click.option('--port', type=int, default=8000)
def main(port):
	"""
	Host the web interface.
	"""
	server = WatchdogWebServer(port=port)
	asyncio.get_event_loop().run_until_complete(server.run())

if __name__ == '__main__':
	main()

